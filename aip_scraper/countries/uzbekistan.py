"""Uzbekistan - Uzaeronavigation AIS (https://uzaeronavigation.com/ais/).

The AIS page opens every AIP section as a PDF through FileView('/media/file/...'),
labelled "ENR 3.1 ATS routes/RNAV", "ENR 4.3 Name-code designators ...", etc.
Aerodromes are split into one PDF per AD 2 item ("(12) Runway physical
characteristics" -> /media/file/7uttt_12_13_....pdf). File names keep the old UT..
codes; the text uses the current UZ.. location indicators (AD 2.1 "UZTT TASHKENT ...").
"""
import html
import re
from datetime import datetime

from ..common import LAT, LATLON, LON, clean, fetch_text, lat_of, latlon_of, lon_of, normalize_coords, pdf_text
from ..features import Collection
from ..parsers import parse_aerodrome, parse_routes, parse_waypoints, point_key

BASE = "https://uzaeronavigation.com"
PAGE = BASE + "/ais/"
SOURCE = "AIP Uzbekistan (Uzaeronavigation)"
CYRILLIC = str.maketrans("АВЕКМНОРСТХх", "ABEKMHOPCTXx")
REMARKS = re.compile(r"\b(?:FIR|TMA)\s+\S+|STATE BOUNDARY|UZBEKISTAN|\d{2} [A-Z]{3} \d{2}")
NAVAID = re.compile(r"^\s*(.+?)\s+(LOM|NDB|[CD]?VOR DME|VOR|DME)\s+([A-Z]{1,3})\s+(\d+(?:\.\d+)?)\s*(kHz|MHz)\s+\S+\s+"
                    r"(\d{6}(?:\.\d+)?[NS])\s+(\d{7}(?:\.\d+)?[EW])", re.M)


def documents():
    """[(url, label)] in page order."""
    return [(BASE + u, clean(html.unescape(re.sub(r"<[^>]+>", " ", t))))
            for u, t in re.findall(r"FileView\('([^']+)'\)\"[^>]*>(.*?)</a>", fetch_text(PAGE), re.S)]


def parse_navaids(text):
    """"DJIZAK DVOR DME     JZK      112.2 MHz       HO     401516.7N 0675439.3E"."""
    return [{"ident": m[3], "type": m[2].replace(" ", "/"), "name": m[1].strip(), "frequency": float(m[4]),
             "frequency_unit": m[5].upper(), "raw_frequency": f"{m[4]} {m[5]}",
             "lat": lat_of(LAT.search(m[6])), "lon": lon_of(LON.search(m[7])), "raw_coord": f"{m[6]} {m[7]}"}
            for m in NAVAID.finditer(text)]


def parse_runways(text):
    """AD 2.12: each end is "08L ... 411520.95N 0691525.79E" (RWY end); the THR coordinates are
    two lines above it and the true bearing ("081,69°") one line above; "4000 x 60" sits between the ends."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if "RUNWAY PHYSICAL" in l.upper()), 0)
    stop = next((i for i, l in enumerate(lines[start:], start) if re.match(r"\s*(?:RWY\s+)?Slope\b", l)), len(lines))
    ends = []
    for i in range(start, stop):
        d = re.match(r"\s*(\d{2}[LRC]?)(?:\s{2,}|\s*$)", lines[i])
        if not d:
            continue
        above = "\n".join(lines[i - 2:i])  # THR coordinates two lines up, bearing one line up
        # Karshi 34 prints its THR on the designator line itself
        thr = LATLON.search(above) or LATLON.search(lines[i])
        brg = re.search(r"(\d{3})[,.](\d+)\s*°", above)
        ends.append({"designator": d.group(1), "line": i,
                     "lat": latlon_of(thr)[0] if thr else None, "lon": latlon_of(thr)[1] if thr else None,
                     "raw_coord": thr.group(0) if thr else None,
                     "true_bearing": float(f"{brg.group(1)}.{brg.group(2)}") if brg else None})
    runways = []
    for a, b in zip(ends[::2], ends[1::2]):
        dims = re.search(r"(\d{3,4})\s*[xх×]\s*(\d{2,3})", "\n".join(lines[a["line"]:b["line"] + 1]))
        sfc = re.search(r"(Asphalt-Concrete|Asphalt|Concrete|Grass|Gravel)", "\n".join(lines[a["line"] - 1:b["line"] + 1]), re.I)
        runways.append({"pair": f"{a['designator']}-{b['designator']}",
                        "length": float(dims.group(1)) if dims else None, "width": float(dims.group(2)) if dims else None,
                        "raw_dims": dims.group(0) if dims else None,
                        "surface": {"ASPHALT-CONCRETE": "ASPH", "ASPHALT": "ASPH", "CONCRETE": "CONC"}.get(
                            sfc.group(1).upper(), sfc.group(1).upper()) if sfc else None,
                        "ends": [{k: v for k, v in e.items() if k != "line"} for e in (a, b)]})
    return runways


def scrape(log):
    docs = documents()
    find = lambda prefix: next(u for u, t in docs if t.startswith(prefix))
    amdt = max((re.match(r"AIRAC AMDT (\d{2})/(\d{2})", t).groups()[::-1], t) for u, t in docs
               if re.match(r"AIRAC AMDT \d{2}/\d{2} eff date", t))[1]
    eff = re.search(r"eff date (\d{2} \w{3} \d{2})", amdt).group(1)
    col = Collection(SOURCE, datetime.strptime(eff, "%d %b %y").date().isoformat(), amdt.split(" eff")[0], PAGE)

    url = find("ENR 4.3")  # name-code designators (ENR 4.4 in the ICAO numbering)
    col.documents += 1
    waypoints = parse_waypoints(pdf_text(url))
    for w in waypoints:
        col.add_waypoint(w, "ENR 4.3", url)
    url = find("ENR 4.1")
    col.documents += 1
    navaids = parse_navaids(pdf_text(url))
    for n in navaids:
        col.add_navaid(n, "ENR 4.1", url)

    # points without a name (it sits above a designator moved to its own line) are found by position
    by_pos = {(round(w["lat"], 3), round(w["lon"], 3)): w["ident"] for w in waypoints}
    by_pos.update({(round(n["lat"], 3), round(n["lon"], 3)): f"{n['name']} ({n['ident']})" for n in navaids})
    url = find("ENR 3.1")
    col.documents += 1
    # a designator printed on a point's coordinate line ("Q523   405855.1N 0713338.0E") opens a new route
    text = re.sub(r"(?m)^(\s?)([A-Z]{1,2}\d{1,3})(\s{3,})(?=\d{6})",
                  lambda m: m[1] + m[2] + "\n" + " " * (len(m[1]) + len(m[2])) + m[3], pdf_text(url))
    for r in parse_routes(text):
        for p in r["points"]:  # "AMDAR STATE BOUNDARY FIR OAKX/UZSD" -> "AMDAR"
            p["name"] = clean(REMARKS.sub(" ", p["name"] or "")) or by_pos.get((round(p["lat"], 3), round(p["lon"], 3)), "")
        col.add_route(r, "ENR 3.1", url, lambda p: point_key(p["name"]),
                      nav_spec="RNAV" if re.match(r"[LMNPQTYZ]\d", r["designator"]) else None)

    # AD 2: items (1)-(3) hold name, ARP and elevation; item (12) the runways
    ads = {}
    for u, t in docs:
        m = re.search(r"/\d+_?(ut[a-z]{2})(?=[_\d])", u)
        if m and re.match(r"\((1|2|3|12)\)", t):
            ads.setdefault(m.group(1).upper(), {}).setdefault(t[1:t.index(")")], u)
    log(f"  AD 2: {len(ads)} aerodromes")
    for code, items in sorted(ads.items()):
        col.documents += 1
        # Cyrillic look-alikes: "UZSК" (Karshi), ARP longitude "Е0603836.86" (Urgench)
        head = normalize_coords("\n".join(pdf_text(u) for u in dict.fromkeys(
            items[k] for k in ("1", "2", "3") if k in items)).translate(CYRILLIC))
        name = re.search(r"^\s*(U[TZ][A-Z]{2})\s+(\S.*?)\s*$", head, re.M)  # "UZFF FERGANA/International"
        icao = name.group(1) if name else code
        a = parse_aerodrome(head, icao=icao)
        if not a:
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
            continue
        a["icao"] = icao
        if name:
            a["name"] = a["raw_name"] = name.group(2)
        elev = re.search(r"Elevation\S*\s+\+?\d+\s*m\s*/\s*(\d+)'", head)
        if elev and a.get("elevation_ft") is None:
            a["elevation_ft"], a["raw_elevation"] = int(elev.group(1)), elev.group(0)
        url = items.get("12")
        a["runways"] = parse_runways(normalize_coords(pdf_text(url).translate(CYRILLIC))) if url else []
        col.add_aerodrome(a, "AD 2", url or items.get("2") or items.get("1"))
    return col
