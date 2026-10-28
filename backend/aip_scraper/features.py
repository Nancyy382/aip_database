"""Build features in the shape served by the eAIP viewer (https://aip.ishu.foo/api/features).

Each country file is a GeoJSON FeatureCollection; every feature carries
naturalKey/parentKey/featureType/publicationId/... and a `fields` map where each
field records its value plus where it came from:

    {"value", "unit", "source", "section", "effective_date", "retrieved_at",
     "source_url", "parser_version", "raw_text"}

The file also carries `publications`, `featureTypes` and `issues`, mirroring the
viewer's /api/publications, /api/feature-types and /api/issues endpoints.
"""
import hashlib
import math
import re
import json
import os
from datetime import datetime, timezone

PARSER_VERSION = "1.0"
FEATURE_TYPES = ("aerodrome", "navaid", "route", "runway", "runwayDirection", "waypoint")


def now():
    return datetime.now(timezone.utc).isoformat()


class Collection:
    def __init__(self, source, effective_date, amendment_id, source_url=None):
        self.source = source
        self.effective_date = effective_date
        self.amendment_id = amendment_id
        self.publication_id = f"{effective_date}-current"
        self.source_url = source_url
        self.features = {}
        self.issues = []
        self.documents = 0

    def field(self, value, section, source_url, raw=None, unit=None, retrieved_at=None):
        return {"value": value, "unit": unit, "source": self.source, "section": section,
                "effective_date": self.effective_date, "retrieved_at": retrieved_at or now(),
                "source_url": source_url, "parser_version": PARSER_VERSION,
                "raw_text": "" if raw is None else str(raw)}

    def add(self, feature_type, key, geometry, fields, parent=None):
        """fields: {name: field dict}; fields whose value is None are dropped."""
        fields = {k: v for k, v in fields.items() if v is not None and v["value"] is not None}
        if key in self.features:
            self.issue("warning", "RULE_DUPLICATE_KEY", key, next(iter(fields.values()), {}).get("section", ""),
                       f"Duplicate {feature_type} {key}; kept the first occurrence")
            return
        digest = hashlib.sha256(json.dumps({"g": geometry, "f": {k: v["value"] for k, v in fields.items()}},
                                           sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.features[key] = {
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "naturalKey": key,
                "parentKey": parent,
                "featureType": feature_type,
                "publicationId": self.publication_id,
                "effectiveFrom": self.effective_date,
                "effectiveTo": None,
                "sourceClass": "AIP",
                "temporality": "permanent",
                "contentHash": digest,
                "fields": fields,
            },
        }

    def issue(self, severity, rule, key, section, message, raw=""):
        self.issues.append({"publicationId": self.publication_id, "severity": severity, "ruleId": rule,
                            "featureKey": key, "section": section, "message": message, "rawSnippet": raw})

    def has(self, key):
        return key in self.features

    # --- record -> feature helpers (records come from parsers.py) ----------

    def add_waypoint(self, w, section, url, routes=None):
        F = lambda v, raw=None, unit=None: self.field(v, section, url, raw, unit)
        self.add("waypoint", f"WPT/{w['ident']}", point(w["lat"], w["lon"]), {
            "designator": F(w["ident"], w["ident"]),
            "coordinates": F([w["lon"], w["lat"]], w.get("raw_coord")),
            "atsRoutes": F(routes or w.get("usage"), routes or w.get("usage")),
        })

    def add_navaid(self, n, section, url, parent=None):
        F = lambda v, raw=None, unit=None: self.field(v, section, url, raw, unit)
        key = f"NAV/{parent}/{n['ident']}" if parent else f"NAV/{n['ident']}"
        if self.has(key) and n.get("type"):
            key = f"{key}/{n['type'].split('/')[0]}"
        self.add("navaid", key, point(n["lat"], n["lon"]), {
            "designator": F(n["ident"], n["ident"]),
            "stationName": F(n.get("name"), n.get("name")),
            "navaidType": F(n.get("type"), n.get("type")),
            "frequency": F(n.get("frequency"), n.get("raw_frequency"), n.get("frequency_unit")),
            "frequencyUnit": F(n.get("frequency_unit"), n.get("frequency_unit")),
            "frequencyRaw": F(n.get("raw_frequency"), n.get("raw_frequency")),
            "associatedAirport": F(parent, parent),
            "coordinates": F([n["lon"], n["lat"]], n.get("raw_coord")),
        }, parent=parent)

    def add_route(self, r, section, url, point_key, nav_spec=None):
        F = lambda v, raw=None, unit=None: self.field(v, section, url, raw, unit)
        seq = [point_key(p) for p in r["points"]]
        self.add("route", f"RTE/{r['designator']}", line([(p["lat"], p["lon"]) for p in r["points"]]), {
            "designator": F(r["designator"].split("#")[0], r["designator"]),
            "routeClass": F(r.get("route_class") or section, section),
            "waypointSequence": F(seq, " -> ".join(k for k in seq if k)),
            "navigationSpecification": F(nav_spec, nav_spec),
        })
        return seq

    def add_waypoints_from_routes(self, routes, section, url, point_key):
        """For AIPs without an ENR 4.4 list: named route points become waypoints."""
        used = {}
        for r in routes:
            for p in r["points"]:
                k = point_key(p)
                if k and k.startswith("WPT/") and re.fullmatch(r"WPT/[A-Z]{5}", k):
                    used.setdefault(k, (p, []))[1].append(r["designator"].split("#")[0])
        for k, (p, desigs) in used.items():
            if not self.has(k):
                self.add_waypoint({"ident": k[4:], "lat": p["lat"], "lon": p["lon"],
                                   "raw_coord": p.get("raw_coord")}, section, url,
                                  routes=", ".join(sorted(set(desigs))))

    def add_aerodrome(self, a, section_prefix, url):
        icao = a["icao"]
        S = lambda sec, v, raw=None, unit=None: self.field(v, f"{icao} {sec}", url, raw, unit)
        self.add("aerodrome", icao, point(a["lat"], a["lon"]), {
            "airportName": S("AD 2.1", a.get("name"), a.get("raw_name")),
            "arpCoordinates": S("AD 2.2", [a["lon"], a["lat"]], a.get("raw_coord")),
            "elevation": S("AD 2.2", a.get("elevation_ft"), a.get("raw_elevation"), "FT"),
            **{k: S(sec, v, v) for k, (sec, v) in (a.get("extra") or {}).items()},
        })
        for rw in a.get("runways", []):
            rkey = f"{icao}/RWY/{rw['pair']}"
            ends_xy = [(e["lat"], e["lon"]) for e in rw["ends"] if e.get("lat") is not None]
            # both thresholds far from the ARP but consistent with each other (their distance
            # matches the runway): the ARP is the suspect, keep the thresholds
            consistent = (len(ends_xy) == 2 and all(_km(t, (a["lat"], a["lon"])) > 15 for t in ends_xy)
                          and 0.3 < _km(*ends_xy) * 1000 / (rw.get("length") or _km(*ends_xy) * 1000) < 1.3
                          and _km(*ends_xy) < 6)
            if consistent:
                self.issue("warning", "RULE_ARP_IMPLAUSIBLE", icao, f"{icao} AD 2.2",
                           f"ARP is {_km(ends_xy[0], (a['lat'], a['lon'])):.0f} km from runway {rw['pair']}, whose "
                           f"thresholds agree with each other; one of them is wrong in the source", a.get("raw_coord") or "")
            for e in rw["ends"]:
                # a lone threshold far from the ARP is a typo in the source (e.g. "E" for "W")
                if not consistent and e.get("lat") is not None and _km((e["lat"], e["lon"]), (a["lat"], a["lon"])) > 15:
                    self.issue("warning", "RULE_THRESHOLD_IMPLAUSIBLE", f"{icao}/RWY/{e['designator']}", f"{icao} AD 2.12",
                               f"THR {e['designator']} is {_km((e['lat'], e['lon']), (a['lat'], a['lon'])):.0f} km from the ARP; "
                               f"coordinate dropped", e.get("raw_coord") or "")
                    e.update(lat=None, lon=None)
            thr = [(e["lat"], e["lon"]) for e in rw["ends"] if e.get("lat") is not None]
            if len(thr) == 2 and re.match(r"\d{2}", rw["ends"][0]["designator"]):
                # THR 1 -> THR 2 must point along runway 1's heading (RWY 15 ~ 150°)
                expected = int(rw["ends"][0]["designator"][:2]) * 10
                actual = _bearing(thr[0], thr[1])
                if abs((actual - expected + 180) % 360 - 180) > 90:
                    self.issue("warning", "RULE_THRESHOLD_ORDER", rkey, f"{icao} AD 2.12",
                               f"Thresholds of {rw['pair']} run {actual:.0f}° but RWY "
                               f"{rw['ends'][0]['designator']} implies ~{expected}°; the source may list them swapped")
            common = {
                "length": S("AD 2.12", rw.get("length"), rw.get("raw_dims"), "M"),
                "width": S("AD 2.12", rw.get("width"), rw.get("raw_dims"), "M"),
                "surface": S("AD 2.12", rw.get("surface"), rw.get("surface")),
            }
            if rw.get("strength"):
                common["strength"] = S("AD 2.12", rw["strength"], rw["strength"])
            if len(thr) < 2:
                self.issue("warning", "RULE_RUNWAY_GEOMETRY", rkey, f"{icao} AD 2.12",
                           f"Runway {rw['pair']} at {icao}: threshold coordinates not captured")
            self.add("runway", rkey, line(thr) if len(thr) == 2 else None,
                     {"pairDesignator": S("AD 2.12", rw["pair"], rw["pair"]), **common}, parent=icao)
            for e in rw["ends"]:
                self.add("runwayDirection", f"{icao}/RWY/{e['designator']}",
                         point(e["lat"], e["lon"]) if e.get("lat") is not None else None, {
                             "designator": S("AD 2.12", e["designator"], e["designator"]),
                             "trueBearing": S("AD 2.12", e.get("bearing"), e.get("raw_bearing"), "DEG"),
                             "magneticBearing": S("AD 2.12", e.get("mag_bearing"), e.get("raw_bearing"), "DEG"),
                             **common,
                             "thresholdCoordinates": S("AD 2.12", [e["lon"], e["lat"]] if e.get("lat") is not None else None,
                                                       e.get("raw_coord")),
                         }, parent=rkey)

    # --- output -------------------------------------------------------------

    def check_routes(self):
        # route tables sometimes name a navaid by its station ("USHUAIA") instead of its ident
        stations = {}
        for f in self.features.values():
            p = f["properties"]
            name = p["fields"].get("stationName", {}).get("value")
            if p["featureType"] == "navaid" and name and not p["parentKey"]:
                for word in {name, name.split(" ")[-1], re.split(r"\s+(?:D?VOR|NDB|DME|TACAN)", name)[0]}:
                    stations.setdefault(word.upper(), p["naturalKey"])
        for f in self.features.values():
            p = f["properties"]
            if p["featureType"] != "route":
                continue
            seq = p["fields"]["waypointSequence"]
            seq["value"] = [k if not k or self.has(k) else stations.get(k.split("/")[-1], k) for k in seq["value"]]
            for k in seq["value"]:
                if k and not self.has(k):
                    self.issue("warning", "RULE_UNRESOLVED_WAYPOINT", p["naturalKey"],
                               p["fields"]["waypointSequence"]["section"],
                               f"Route {p['fields']['designator']['value']} references '{k.split('/')[-1]}' "
                               f"absent from national index", k.split("/")[-1])

    def write(self, path, meta=None):
        self.check_routes()
        feats = sorted(self.features.values(),
                       key=lambda f: (f["properties"]["featureType"], f["properties"]["naturalKey"]))
        counts = {}
        for f in feats:
            counts[f["properties"]["featureType"]] = counts.get(f["properties"]["featureType"], 0) + 1
        data = {
            "type": "FeatureCollection",
            "features": feats,
            "featureTypes": [{"featureType": t, "count": counts[t]} for t in sorted(counts)],
            "publications": [{
                "cycleId": self.publication_id,
                "effectiveDate": self.effective_date,
                "amendmentId": self.amendment_id,
                "sourceKind": "LIVE",
                "ingestedAt": now(),
                "status": "promoted",
                "stats": {"total_documents": self.documents, "parsed_features": len(feats),
                          "issue_count": len(self.issues),
                          "error_count": sum(i["severity"] == "error" for i in self.issues),
                          "warning_count": sum(i["severity"] == "warning" for i in self.issues)},
                "sourceUrl": self.source_url,
                "notes": None,
            }],
            "issues": self.issues,
            **({"meta": meta} if meta else {}),
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        return counts


def _bearing(a, b):
    """Initial great-circle bearing (degrees) from (lat, lon) a to b."""
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return math.degrees(math.atan2(y, x)) % 360


def _km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def point(lat, lon):
    return {"type": "Point", "coordinates": [lon, lat]}


def line(coords):
    """coords: [(lat, lon), ...]"""
    return {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coords]}
