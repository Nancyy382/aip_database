"""Bermuda - Bermuda Airport Authority eAIP
(https://www.airportauthority.bm/ais/aeronautical-info-publication.html).

The AIS page links the issue's history page ("/eaip/27-Nov-2025-A/history-en-GB.html"),
which lists the HTML eAIP folder of each effective issue; the newest one in force
is used. Single aerodrome TXKF; ENR 3.2 holds the routes, ENR 4.4 the fixes.
"""
import re
from datetime import date, datetime

from ..common import fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

SITE = "https://www.airportauthority.bm"
PAGE = SITE + "/ais/aeronautical-info-publication.html"
SOURCE = "eAIP Bermuda (Bermuda Airport Authority)"
NAV_TYPE = re.compile(r"\b(D?VOR/DME|D?VOR|NDB/DME|NDB|DME|TACAN|VORTAC)\b")


def current_issue():
    history = SITE + re.search(r'href="(/eaip/[^"]+/history-en-GB\.html)"', fetch_text(PAGE)).group(1)
    page = fetch_text(history)
    issues = [(datetime.strptime(d, "%Y-%m-%d").date(), href)
              for href, d in re.findall(r"href=['\"]((\d{4}-\d{2}-\d{2})-AIRAC/html/index\.html)['\"]", page)]
    past = [i for i in issues if i[0] <= date.today()]
    eff, href = max(past or issues)
    return eff, history.rsplit("/", 1)[0] + "/" + href.rsplit("/", 1)[0] + "/"


def scrape(log):
    eff, base = current_issue()
    eaip = base + "eAIP/"
    col = Collection(SOURCE, eff.isoformat(), f"AIRAC {eff:%d %b %Y}".upper(), base + "index.html")
    page = lambda name: fetch_text(f"{eaip}TX-{name}-en-GB.html")
    url = lambda name: f"{eaip}TX-{name}-en-GB.html"

    col.documents += 1
    for r in rows(page("ENR-4.4")):
        c = coord(r[1]) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]):
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                              "usage": r[2] if len(r) > 2 else None}, "ENR 4.4", url("ENR-4.4"))

    # ENR 4.1: "Bermuda VOR/DME VOR/DME" | BDA | 113.900 MHz | H24 | coordinates | ... (the SSR row has no ID)
    col.documents += 1
    for r in rows(page("ENR-4.1")):
        c = coord(r[4]) if len(r) > 4 else None
        t = NAV_TYPE.search(r[0]) if r else None
        if c and t and re.fullmatch(r"[A-Z]{2,4}", r[1]):
            f = re.search(r"(\d+(?:\.\d+)?)\s*(MHZ|KHZ)", r[2], re.I)
            col.add_navaid({"ident": r[1], "type": t.group(1), "name": r[0][:t.start()].strip() or None,
                            "frequency": float(f.group(1)) if f else None,
                            "frequency_unit": f.group(2).upper() if f else None, "raw_frequency": r[2],
                            "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", url("ENR-4.1"))

    for sec in ("ENR-3.1", "ENR-3.2", "ENR-3.3"):
        col.documents += 1
        for r in parse_routes(text(page(sec))):
            col.add_route(r, sec.replace("-", " "), url(sec), lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if sec == "ENR-3.2" else None)

    menu = fetch_text(eaip + "TX-menu-en-GB.html")
    for icao in sorted(set(re.findall(r"TX-AD-2\.([A-Z]{4})-en-GB\.html", menu))):
        col.documents += 1
        rec = parse_ad2(page(f"AD-2.{icao}"), icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", url(f"AD-2.{icao}"))
    log(f"  issue effective {eff}")
    return col
