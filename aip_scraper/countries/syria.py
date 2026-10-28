"""Syria - GACA eAIP (https://eaip.gaca.gov.sy/).

A custom eAIP web app: the home page lists every section as /section/<id>
("ENR 4.4  Name-Code Designators ...", "AD 2.1  OSDI — Damascus International Airport").
Tables are HTML; ENR 3 puts all points of a route in one cell, separated by "◄".
Several coordinates mix formats ("N0335256.40E37°53.05"); common.normalize_coords
handles them.
"""
import html
import re
from datetime import datetime

from ..common import clean, fetch_text
from ..eaip_html import coord, parse_ad2, rows
from ..features import Collection
from ..parsers import point_key

BASE = "https://eaip.gaca.gov.sy/"
SOURCE = "eAIP Syria (GACA)"
NAV_TYPE = re.compile(r"\b(D?VOR/DME|D?VOR|NDB|DME|TACAN)\b")
DESIG = re.compile(r"^\s*(U?[A-Z]{1,2}\s?\d{1,4}[A-Z]?)\b")


def sections():
    page = fetch_text(BASE)
    return {clean(html.unescape(re.sub(r"<[^>]+>", " ", x))): u for u, x in
            re.findall(r'<a[^>]*href=["\'](https://eaip\.gaca\.gov\.sy/section/\d+)["\'][^>]*>(.*?)</a>', page, re.S)}


def parse_routes(page):
    """Rows: "R655 | ... " then "◄TAN VOR/DME 332856.58N 0383914.63E ◄FIRAS ... | ..." (or both in one cell)."""
    routes, cur = [], None
    for r in rows(page):
        if not r:
            continue
        d = DESIG.match(r[0])
        if d and not r[0].startswith("◄") and "use the consolidated" not in r[0]:
            cur = {"designator": d.group(1).replace(" ", ""), "points": []}
            routes.append(cur)
        cell = next((c for c in r if "◄" in c), None)
        if cur is None or not cell:
            continue
        for piece in cell.split("◄")[1:]:
            c = coord(piece)
            if c:
                name = clean(re.sub(r"(?i)\bFIR\s+boundary\b|\(U/S\)", " ", piece[: piece.find(c[2].split(" ")[0])]))
                cur["points"].append({"name": name, "lat": c[0], "lon": c[1], "raw_coord": c[2]})
    return [r for r in routes if len(r["points"]) >= 2]


def scrape(log):
    sec = sections()
    find = lambda prefix: next(((k, u) for k, u in sec.items() if k.startswith(prefix)), (None, None))
    cycle = re.search(r"AIRAC calendar cycle (\d{2})(\d{2})\s*\|\s*(\d{2} \w{3})", re.sub(r"<[^>]+>", " ", fetch_text(BASE)))
    eff = datetime.strptime(f"{cycle.group(3)} 20{cycle.group(1)}", "%d %b %Y").date().isoformat() if cycle else "unknown"
    col = Collection(SOURCE, eff, f"AIRAC cycle {cycle.group(1)}{cycle.group(2)}" if cycle else "unknown", BASE)

    title, url = find("ENR 4.4")
    col.documents += 1
    for r in rows(fetch_text(url)):
        c = coord(r[1]) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{4,5}", r[0]):
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                              "usage": r[2] if len(r) > 2 else None}, "ENR 4.4", url)

    title, url = find("ENR 4.1")
    col.documents += 1
    for r in rows(fetch_text(url)):
        c = coord(r[4]) if len(r) > 4 else None
        t = NAV_TYPE.search(r[0]) if r else None
        if c and t and re.fullmatch(r"[A-Z]{2,4}", r[1]):
            f = re.search(r"(\d+(?:\.\d+)?)\s*(MHz|kHz)", r[2], re.I)
            col.add_navaid({"ident": r[1], "type": t.group(1), "name": clean(r[0][:t.start()].rstrip("/ ")) or None,
                            "frequency": float(f.group(1)) if f else None,
                            "frequency_unit": f.group(2).upper() if f else None, "raw_frequency": r[2],
                            "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", url)

    for prefix in ("ENR 3.1", "ENR 3.2", "ENR 3.3"):
        title, url = find(prefix)
        if not url:
            continue
        col.documents += 1
        routes = parse_routes(fetch_text(url))
        # ENR 4.4 misses several route points (some rows are garbled); the route tables give them
        col.add_waypoints_from_routes(routes, prefix, url, lambda p: point_key(p["name"]))
        for r in routes:
            col.add_route(r, prefix, url, lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if prefix == "ENR 3.3" else None)

    ads = [(re.search(r"\b(OS[A-Z]{2})\b", k).group(1), u) for k, u in sec.items() if re.match(r"AD 2\.\d+\s+OS[A-Z]{2}", k)]
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, url in ads:
        col.documents += 1
        rec = parse_ad2(fetch_text(url), icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", url)
        else:  # e.g. OSDZ publishes "351707N,735770 E" (70 seconds)
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates missing or invalid in the source")
    return col
