"""Shared scraper for the COCESNA eAIP Central America (https://www.cocesna.org/aipca/history.html).

One Eurocontrol-style HTML eAIP covers Belize (MZ), Guatemala (MG), Honduras (MH),
El Salvador (MS), Nicaragua (MN) and Costa Rica (MR).
"""
import math
import re
from datetime import date, datetime

from ..common import fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

BASE = "https://www.cocesna.org/aipca/"
SOURCE = "eAIP Central America (COCESNA)"
NAV_TYPE = re.compile(r"\b(D?VOR/DME|D?VOR|NDB/DME|NDB|DME|TACAN|VORTAC)\b")


def current_issue():
    page = fetch_text(BASE + "history.html")
    issues = []
    for href in re.findall(r'href="(AIP_\d+/[^"]+/(\d{4}-\d{2}-\d{2})[^"]*/html/index-es-ES\.html)"', page):
        issues.append((datetime.strptime(href[1], "%Y-%m-%d").date(), href[0]))
    past = [i for i in issues if i[0] <= date.today()]
    return max(past or issues)


def _dist(a, b):
    return math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(a[0])))


def scrape_state(prefix, icaos, log):
    eff, index = current_issue()
    eaip = BASE + index.rsplit("/", 1)[0] + "/eAIP/"
    col = Collection(SOURCE, eff.isoformat(), re.search(r"\d{4}-\d{2}-\d{2}-([^/]+)", index).group(1), BASE + index)
    page = lambda name: fetch_text(f"{eaip}ES-{name}-es-ES.html")
    menu = fetch_text(eaip + "ES-menu-es-ES.html")

    # every COCESNA aerodrome's ARP decides which regional points belong to this state
    arp = {}
    for icao in sorted(set(re.findall(r"ES-AD-2\.([A-Z]{4})-es-ES\.html", menu))):
        rec = parse_ad2(page(f"AD-2.{icao}"), icao)
        if not rec:
            continue
        arp[icao] = (rec["lat"], rec["lon"])
        if icao in icaos:
            col.documents += 1
            col.add_aerodrome(rec, "AD 2", f"{eaip}ES-AD-2.{icao}-es-ES.html")
    ours = lambda lat, lon: min(arp, key=lambda k: _dist(arp[k], (lat, lon))) in icaos

    # every state's ENR 4.1: state's own aids, plus neighbours' aids that state routes use
    navs = {}
    for name in sorted(set(re.findall(r"ES-(M[A-Z]-ENR-4\.1)-es-ES\.html", menu))):
        col.documents += 1
        for r in rows(page(name)):
            c = coord(r[4]) if len(r) > 4 else None
            t = NAV_TYPE.search(r[0]) if r else None
            if not (c and t and re.fullmatch(r"[A-Z]{2,4}", r[1])):
                continue
            f = re.search(r"(\d+(?:\.\d+)?)\s*(MHZ|KHZ)", r[2], re.I)
            n = {"ident": r[1], "type": t.group(1), "name": re.split(r"\s+(?:D?VOR|NDB|DME)", r[0])[0].strip(),
                 "frequency": float(f.group(1)) if f else None, "frequency_unit": f.group(2).upper() if f else None,
                 "raw_frequency": r[2], "lat": c[0], "lon": c[1], "raw_coord": c[2]}
            navs[n["ident"]] = (n, f"{eaip}ES-{name}-es-ES.html", name.startswith(prefix))

    points = {}
    for r in rows(page("CS-ENR-4.4")):
        c = coord(r[1]) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]):
            points[r[0]] = {"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                            "usage": r[2] if len(r) > 2 else None}

    used = set()
    for sec in ("CS-ENR-3.1", "CS-ENR-3.2"):
        col.documents += 1
        url = f"{eaip}ES-{sec}-es-ES.html"
        for r in parse_routes(text(page(sec))):
            if not any(ours(p["lat"], p["lon"]) for p in r["points"]):
                continue
            pk = lambda p: point_key(p["name"])
            used |= {pk(p) for p in r["points"]}
            col.add_route(r, sec[3:].replace("-", " "), url, pk, nav_spec="RNAV" if sec.endswith("3.2") else None)
    for ident, (n, url, own) in navs.items():
        if own or f"NAV/{ident}" in used:
            col.add_navaid(n, "ENR 4.1", url)
    for p in points.values():
        if ours(p["lat"], p["lon"]) or f"WPT/{p['ident']}" in used:
            col.add_waypoint(p, "ENR 4.4", f"{eaip}ES-CS-ENR-4.4-es-ES.html")
    log(f"  COCESNA {index.split('/')[3]}: {len(col.features)} features for prefix {prefix}")
    return col

