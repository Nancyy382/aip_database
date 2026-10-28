"""Minimal AIXM 5.1 reader for the six layers we publish.

Reads an AIXMBasicMessage (BASELINE time slices) and returns plain records in the
same shape the PDF/HTML parsers produce, so features.Collection can turn them into
viewer features. Positions in AIXM are "lat lon" (EPSG:4326 axis order).
"""
import re
import xml.etree.ElementTree as ET

NS = {"aixm": "http://www.aixm.aero/schema/5.1", "gml": "http://www.opengis.net/gml/3.2",
      "xlink": "http://www.w3.org/1999/xlink", "message": "http://www.aixm.aero/schema/5.1/message"}
A = "{http://www.aixm.aero/schema/5.1}"
G = "{http://www.opengis.net/gml/3.2}"
HREF = "{http://www.w3.org/1999/xlink}href"


def _uuid(href):
    return re.sub(r"^(urn:uuid:|#uuid\.|#)", "", href or "")


def _text(ts, path):
    el = ts.find(path, NS)
    return el.text.strip() if el is not None and el.text and el.text.strip() else None


def _num(ts, path):
    v = _text(ts, path)
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _pos(ts, path):
    el = ts.find(path + "//gml:pos", NS)
    if el is None or not el.text:
        return None
    lat, lon = map(float, el.text.split()[:2])
    return lat, lon


def _ref(ts, path):
    el = ts.find(path, NS)
    return _uuid(el.get(HREF)) if el is not None else None


def load(xml_bytes):
    """{feature type: {uuid: time slice element}} for every BASELINE time slice."""
    if isinstance(xml_bytes, str):
        xml_bytes = xml_bytes.encode("utf-8")
    xml_bytes = xml_bytes.replace(b"/schema/5.1.1", b"/schema/5.1")
    root = ET.fromstring(xml_bytes)
    out = {}
    for member in root:
        for feat in member:
            ident = feat.find("gml:identifier", NS)
            uid = ident.text.strip() if ident is not None else _uuid(feat.get(f"{G}id"))
            ts = feat.find("aixm:timeSlice/*", NS)
            if ts is None or _text(ts, "aixm:interpretation") not in (None, "BASELINE", "SNAPSHOT"):
                continue
            out.setdefault(feat.tag.replace(A, ""), {})[uid] = ts
    return out


def airports(db):
    """[{uuid, icao, name, lat, lon, elevation_ft, runways: [...]}] with runways/thresholds attached."""
    thr = {}
    for ts in db.get("RunwayCentrelinePoint", {}).values():
        if _text(ts, "aixm:role") in ("THR", "DISTHR"):
            rd = _ref(ts, "aixm:onRunway")
            if _text(ts, "aixm:role") == "THR" or rd not in thr:
                thr[rd] = _pos(ts, "aixm:location")
    directions = {}
    for uid, ts in db.get("RunwayDirection", {}).items():
        directions.setdefault(_ref(ts, "aixm:usedRunway"), []).append({
            "designator": _text(ts, "aixm:designator"),
            "bearing": _num(ts, "aixm:trueBearing"), "raw_bearing": _text(ts, "aixm:trueBearing"),
            "lat": (thr.get(uid) or (None, None))[0], "lon": (thr.get(uid) or (None, None))[1],
            "raw_coord": " ".join(map(str, thr[uid])) if thr.get(uid) else None})
    runways = {}
    for uid, ts in db.get("Runway", {}).items():
        if _text(ts, "aixm:type") not in (None, "RWY"):
            continue
        ends = sorted(directions.get(uid, []), key=lambda e: e["designator"] or "")
        length, width = _num(ts, "aixm:nominalLength"), _num(ts, "aixm:nominalWidth")
        runways.setdefault(_ref(ts, "aixm:associatedAirportHeliport"), []).append({
            "pair": "-".join(e["designator"] for e in ends) or (_text(ts, "aixm:designator") or "").replace("RWY ", "").replace("/", "-"),
            "length": length, "width": width,
            "raw_dims": f"{length:g} x {width:g}" if length and width else None,
            "surface": _text(ts, ".//aixm:composition"), "ends": ends})
    out = []
    for uid, ts in db.get("AirportHeliport", {}).items():
        p = _pos(ts, "aixm:ARP")
        if not p:
            continue
        elev = _num(ts, "aixm:fieldElevation")
        uom = (ts.find("aixm:fieldElevation", NS).get("uom") if ts.find("aixm:fieldElevation", NS) is not None else None)
        icao = _text(ts, "aixm:locationIndicatorICAO") or _text(ts, "aixm:designator")
        out.append({"uuid": uid, "icao": icao, "name": _text(ts, "aixm:name"), "raw_name": _text(ts, "aixm:name"),
                    "lat": p[0], "lon": p[1], "raw_coord": f"{p[0]} {p[1]}",
                    "elevation_ft": round(elev * 3.28084) if elev is not None and uom == "M" else (round(elev) if elev is not None else None),
                    "raw_elevation": f"{_text(ts, 'aixm:fieldElevation')} {uom}" if elev is not None else None,
                    "runways": runways.get(uid, [])})
    return out


def navaids(db):
    """[{uuid, ident, type, name, frequency, frequency_unit, lat, lon}] (frequency from VOR/NDB/DME/TACAN)."""
    freq = {}
    for kind, path in (("VOR", "aixm:frequency"), ("NDB", "aixm:frequency"), ("DME", "aixm:ghostFrequency"),
                       ("Localizer", "aixm:frequency"), ("Glidepath", "aixm:frequency")):
        for uid, ts in db.get(kind, {}).items():
            el = ts.find(path, NS)
            if el is not None and el.text:
                freq[uid] = (float(el.text), (el.get("uom") or "").upper())
            elif kind == "DME" and _text(ts, "aixm:channel"):
                freq.setdefault(uid, (None, "CH " + _text(ts, "aixm:channel")))
    out = []
    for uid, ts in db.get("Navaid", {}).items():
        p = _pos(ts, "aixm:location")
        if not p:
            continue
        comps = [_ref(c, "aixm:theNavaidEquipment") for c in ts.findall(".//aixm:NavaidComponent", NS)]
        f = next((freq[c] for c in comps if c in freq and freq[c][0] is not None), None)
        out.append({"uuid": uid, "ident": _text(ts, "aixm:designator"), "type": (_text(ts, "aixm:type") or "").replace("_", "/"),
                    "name": _text(ts, "aixm:name"), "frequency": f[0] if f else None,
                    "frequency_unit": ("MHZ" if f and f[1] in ("MHZ", "MHz") else "KHZ" if f and f[1] in ("KHZ", "kHz") else None),
                    "raw_frequency": f"{f[0]:g} {f[1]}" if f else None,
                    "lat": p[0], "lon": p[1], "raw_coord": f"{p[0]} {p[1]}"})
    return out


def designated_points(db):
    out = []
    for uid, ts in db.get("DesignatedPoint", {}).items():
        p = _pos(ts, "aixm:location")
        ident = _text(ts, "aixm:designator")
        if p and ident:
            out.append({"uuid": uid, "ident": ident, "type": _text(ts, "aixm:type"),
                        "lat": p[0], "lon": p[1], "raw_coord": f"{p[0]} {p[1]}"})
    return out


def routes(db, points_by_uuid):
    """[{designator, points: [{name, key, lat, lon}]}] by chaining each route's segments."""
    names = {}
    for uid, ts in db.get("Route", {}).items():
        names[uid] = "".join(x for x in (_text(ts, "aixm:designatorPrefix"), _text(ts, "aixm:designatorSecondLetter"),
                                         _text(ts, "aixm:designatorNumber"), _text(ts, "aixm:multipleIdentifier")) if x) \
            or _text(ts, "aixm:name")
    segs = {}
    for ts in db.get("RouteSegment", {}).values():
        ends = []
        for side in ("aixm:start", "aixm:end"):
            ref = next((_ref(ts, f"{side}//aixm:{c}") for c in ("pointChoice_fixDesignatedPoint", "pointChoice_navaidSystem")
                        if _ref(ts, f"{side}//aixm:{c}")), None)
            ends.append(ref)
        if all(ends):
            segs.setdefault(_ref(ts, "aixm:routeFormed"), []).append(tuple(ends))
    out = []
    for ruid, pairs in segs.items():
        nxt = dict(pairs)
        starts = [a for a, _ in pairs if a not in {b for _, b in pairs}] or [pairs[0][0]]
        for start in starts:  # a route can consist of separate chains
            chain, cur, seen = [start], start, {start}
            while cur in nxt and nxt[cur] not in seen:
                cur = nxt[cur]
                chain.append(cur)
                seen.add(cur)
            pts = [points_by_uuid[u] for u in chain if u in points_by_uuid]
            if len(pts) >= 2:
                out.append({"designator": names.get(ruid) or ruid[:8],
                            "points": [{"name": p["ident"], "key": p["key"], "lat": p["lat"], "lon": p["lon"],
                                        "raw_coord": p["raw_coord"]} for p in pts]})
    return out
