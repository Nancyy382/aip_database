"""Shared scraper for the ASECNA eAIP (https://aim.asecna.aero/html/index-fr-FR.html).

One eAIP for 17 states, numbered in the menu ("05 Congo", "07 Gabon", ...). Each
section is its own page named after its menu id: "FR-_05ENR-4.1-01-fr-FR.html"
(navaids of state 05), "FR-_05AD-2.FCBB-fr-FR.html" (aerodrome FCBB). ENR 3 and
ENR 4.4 are common to all states ("FR-_00ENR-4.4-01-fr-FR.html"), with no state
column, so waypoints are assigned by country border (borders.py) and a route is
kept when one of its points lies in the country.
"""
import html
import re
from datetime import datetime

from .. import borders
from ..common import clean, fetch_text
from ..eaip_html import coord, parse_ad2, rows
from ..features import Collection
from ..parsers import point_key

EAIP = "https://aim.asecna.aero/html/eAIP/"
SOURCE = "eAIP ASECNA"
NAV_TYPE = re.compile(r"\b(D?VOR-DME|D?VOR|NDB|DME|TACAN)\b")
DESIG = re.compile(r"U?[A-Z]{1,2}\d{1,4}[A-Z]?")
MONTHS = {"JAN": 1, "FEB": 2, "FEV": 2, "MAR": 3, "APR": 4, "AVR": 4, "MAY": 5, "MAI": 5, "JUN": 6, "JUIN": 6,
          "JUL": 7, "JUIL": 7, "AUG": 8, "AOU": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def page(section_id):
    return f"{EAIP}FR-{section_id}-fr-FR.html"


def effective_date(text):
    """"(section ENR-4.4) valide à partir du 22 JAN 2026" -> "2026-01-22"."""
    m = re.search(r"valide à partir du (\d{1,2}) ([A-Z]+) (\d{4})", text)
    return datetime(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).date().isoformat() if m else "unknown"


def point_name(name):
    """"LIBREVILLE DVOR-DME ( LV )" -> "LIBREVILLE DVOR/DME (LV)" so point_key finds the ident."""
    return re.sub(r"\(\s*([A-Z]{2,3})\s*\)", r"(\1)", name).replace("-DME", "/DME")


def parse_routes(text):
    """A "<designator> | Disponibilité:" row opens a route; point rows are
    "▲ | NAME | coordinates" (▲/△ or "Compulsory-..." in the first cell)."""
    routes, cur = [], None
    for r in rows(text):
        d = DESIG.match(r[0]) if len(r) > 1 and r[1].startswith("Disponibilit") else None
        if d:  # "UA400 | Disponibilité:", "UA616 (RNP 10 ) | ...", "R984-1 | ..."
            cur = {"designator": d.group(0), "points": []}
            routes.append(cur)
            continue
        c = coord(r[2]) if len(r) > 2 else None
        if cur is not None and c and r[1]:
            cur["points"].append({"name": point_name(clean(r[1])), "lat": c[0], "lon": c[1], "raw_coord": c[2]})
    return [r for r in routes if len(r["points"]) >= 2]


def scrape_state(number, iso3, log):
    menu = fetch_text(EAIP + "FR-menu-fr-FR.html")
    wpt_page = fetch_text(page("_00ENR-4.4-01"))
    eff = effective_date(wpt_page)
    col = Collection(SOURCE, eff, f"eAIP valid from {eff}", EAIP.replace("eAIP/", "index-fr-FR.html"))
    inside = lambda lat, lon: borders.contains(area, lon, lat)
    area = borders.country(iso3)

    # ENR 4.1 (per state): "NAME TYPE ( VAR )" | ID | "113.1 MHz Ch 78X" | hours | coordinates | ...
    url = page(f"_{number}ENR-4.1-01")
    col.documents += 1
    for r in rows(fetch_text(url)):
        t = NAV_TYPE.search(r[0]) if r else None
        c = coord(r[4]) if len(r) > 4 else None
        if t and c and re.fullmatch(r"[A-Z]{1,3}", r[1]):
            f = re.search(r"(\d+(?:\.\d+)?)\s*(MHz|kHz)", r[2], re.I)
            col.add_navaid({"ident": r[1], "type": t.group(1).replace("-", "/"), "name": clean(r[0][:t.start()]) or None,
                            "frequency": float(f.group(1)) if f else None,
                            "frequency_unit": f.group(2).upper() if f else None, "raw_frequency": r[2],
                            "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", url)

    # ENR 3 (common): routes touching the country, with all their points
    routes = []
    for sec in ("3.1-01", "3.2-01", "3.3-01", "3.5-01"):
        url = page(f"_00ENR-{sec}")
        col.documents += 1
        for r in parse_routes(fetch_text(url)):
            if any(inside(p["lat"], p["lon"]) for p in r["points"]):
                routes.append((r, f"ENR {sec[:3]}", url))
    key = lambda p: point_key(p["name"])
    used = {key(p) for r, _, _ in routes for p in r["points"]}

    # ENR 4.4 (common): points inside the country, plus points its routes use
    url = page("_00ENR-4.4-01")
    col.documents += 1
    for r in rows(wpt_page):
        c = coord(r[1]) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]) and (inside(c[0], c[1]) or f"WPT/{r[0]}" in used):
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                              "usage": r[2] if len(r) > 2 else None}, "ENR 4.4", url)
    for r, sec, url in routes:
        col.add_waypoints_from_routes([r], sec, url, key)  # route points missing from ENR 4.4
        col.add_route(r, sec, url, key, nav_spec="RNAV" if sec == "ENR 3.3" else None)

    # AD 2 (per aerodrome); the name follows the number in the menu: "05 AD-2.FCBB </span> BRAZZAVILLE / MAYA-MAYA"
    ads = re.findall(rf'id="_{number}AD-2\.([A-Z]{{4}})"[^>]*>.*?</span>([^<]*)</a>', menu)
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, title in ads:
        url = page(f"_{number}AD-2.{icao}")
        col.documents += 1
        try:
            a = parse_ad2(fetch_text(url), icao)
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", f"{url}: {e}")
            continue
        if not a:
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
            continue
        name = clean(html.unescape(title))
        if name:  # the AD 2.1 cell is often just "--"
            a["name"] = a["raw_name"] = name
        col.add_aerodrome(a, "AD 2", url)
    return col
