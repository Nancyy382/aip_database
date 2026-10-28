"""Dutch Caribbean - DC-ANSP AIM (https://aim.dc-ansp.org/publications/digital-aip/).

DC-ANSP publishes the whole AIP dataset as AIXM 5.1 (one BASELINE file per AIRAC
amendment, e.g. "2608_06 AUG 26_..._AeroDb AIRAC AMDT 02-26.xml"). It covers six
aerodromes (Aruba, Bonaire, Curaçao, Sint Maarten, Saba, Sint Eustatius); each
country file gets its own aerodrome(s) and the points/navaids nearest to it, plus
every route that touches one of those points.
"""
import math
import re
from datetime import date, datetime

from .. import aixm
from ..common import fetch, fetch_text
from ..features import Collection

PAGE = "https://aim.dc-ansp.org/publications/digital-aip/"
SOURCE = "AIP Dutch Caribbean (DC-ANSP, AIXM 5.1)"
ISLANDS = {"TNCA": "Aruba", "TNCB": "Bonaire", "TNCC": "Curaçao", "TNCM": "Sint Maarten",
           "TNCS": "Saba", "TNCE": "Sint Eustatius"}


def current_dataset():
    """(effective date, amendment, url) of the newest AIXM file already in force."""
    page = fetch_text(PAGE)
    files = []
    for href in re.findall(r'href="([^"]+AeroDb[^"]+\.xml)"', page):
        name = href.replace("%20", " ")
        m = re.search(r"_(\d{2} [A-Z]{3} \d{2})_.*(AIRAC AMDT \d{2}-\d{2})", name)
        if m:
            files.append((datetime.strptime(m.group(1).title(), "%d %b %y").date(), m.group(2), href))
    past = [f for f in files if f[0] <= date.today()]
    return max(past or files)


def _dist(a, b):
    return math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(a[0])))


def scrape_islands(icaos, log):
    eff, amdt, url = current_dataset()
    db = aixm.load(fetch(url))
    col = Collection(SOURCE, eff.isoformat(), amdt, PAGE)
    col.documents += 1
    airports = aixm.airports(db)
    arp = {a["icao"]: (a["lat"], a["lon"]) for a in airports}
    nearest = lambda lat, lon: min(arp, key=lambda k: _dist(arp[k], (lat, lon)))

    for a in airports:
        if a["icao"] in icaos:
            col.add_aerodrome(a, "AD 2", url)

    # one navaid per ident (AIXM lists VOR/DME, VOR and DME separately); ILS belong to an aerodrome
    navs = aixm.navaids(db)
    ils_idents = {n["ident"] for n in navs if n["type"].startswith(("ILS", "LOC"))}
    rank = lambda n: (0 if "/" in n["type"] and not n["type"].startswith("ILS") else 1, n["frequency"] is None)
    nav_by_uuid, nav_by_key = {}, {}
    for n in sorted(navs, key=rank):
        ap = nearest(n["lat"], n["lon"])
        ils = n["ident"] in ils_idents  # the ILS's own DME/LOC components share its ident
        key = f"NAV/{ap}/{n['ident']}/ILS" if ils else f"NAV/{n['ident']}"
        nav_by_uuid[n["uuid"]] = {**n, "key": key, "airport": ap}
        nav_by_key.setdefault(key, nav_by_uuid[n["uuid"]])
    points = {d["uuid"]: {**d, "key": f"WPT/{d['ident']}"} for d in aixm.designated_points(db)}

    # this country's routes, and every point they use (even ones nearer another island)
    rts = [r for r in aixm.routes(db, {**points, **nav_by_uuid})
           if any(nearest(p["lat"], p["lon"]) in icaos for p in r["points"])]
    used = {p["key"] for r in rts for p in r["points"]}
    for key, n in nav_by_key.items():
        if n["airport"] in icaos or key in used:
            ils = "/ILS" in key
            col.add_navaid({**n, "ident": f"{n['ident']}/ILS" if ils else n["ident"]},
                           f"{n['airport']} AD 2.19" if ils else "ENR 4.1", url, parent=n["airport"] if ils else None)
    for d in points.values():
        if nearest(d["lat"], d["lon"]) in icaos or d["key"] in used:
            col.add_waypoint(d, "ENR 4.4", url)
    for r in rts:
        col.add_route(r, "ENR 3", url, lambda p: p["key"],
                      nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)
    log(f"  {amdt} effective {eff}: {', '.join(ISLANDS[i] for i in icaos)}")
    return col
