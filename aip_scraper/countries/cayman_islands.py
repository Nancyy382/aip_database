"""Cayman Islands - Cayman Islands Airports Authority
(https://www.caymanairports.com/aeronautical-information-publication).

The AIP is three PDFs (General, Enroute, Aerodrome) linked from that page, plus
amendment packages. Significant points are in ENR 4.3 (two-column table,
"N18 40 01.00 / W81 15 35.000"); the Aerodrome PDF holds MWCR and MWCB.
"""
import re
from datetime import datetime

from ..common import fetch_text, pdf_text
from ..features import Collection
from ..parsers import (parse_aerodrome, parse_navaids_ident_first, parse_routes, parse_waypoints, point_key,
                       section)

PAGE = "https://www.caymanairports.com/aeronautical-information-publication"
SOURCE = "AIP Cayman Islands (CIAA)"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def documents():
    page = fetch_text(PAGE)
    links = {re.sub(r"<[^>]+>", "", t).strip(): u for u, t in re.findall(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>', page, re.S)}
    amdt = next((t for t in links if t.startswith("Amendment package")), None)
    return links["Enroute"], links["Aerodrome"], amdt


def scrape(log):
    enr_url, ad_url, amdt = documents()
    enr, ad = pdf_text(enr_url), pdf_text(ad_url)
    m = re.search(r"effective (\d{1,2}) (\w+) (\d{4})", amdt or "")
    eff = datetime.strptime(" ".join(m.groups()), "%d %B %Y").date().isoformat() if m else "unknown"
    col = Collection(SOURCE, eff, re.sub(r"\s+effective.*", "", amdt or "unknown"), PAGE)
    col.documents += 2

    for w in parse_waypoints(section(enr, r"ENR 4\.3", r"ENR 4\.4")):
        col.add_waypoint(w, "ENR 4.3", enr_url)
    for n in parse_navaids_ident_first(section(enr, r"ENR 4\.1", r"ENR 4\.2")):
        col.add_navaid(n, "ENR 4.1", enr_url)
    # the ENR 3.1 heading is printed "ENR 3. 1"; ENR 3.3 onwards are VFR/other routes
    start = re.search(r"ENR 3\.\s?1 CONVENTIONAL", enr)
    end = re.search(r"ENR 3\.\s?3 OTHER ROUTES", enr)
    routes = parse_routes(enr[start.start(): end.start() if end else None] if start else enr)
    # a few route points (BRACC, KATAL...) are missing from ENR 4.3; the route tables give them
    col.add_waypoints_from_routes(routes, "ENR 3", enr_url, lambda p: point_key(p["name"]))
    for r in routes:
        col.add_route(r, "ENR 3", enr_url, lambda p: point_key(p["name"]),
                      nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)

    icaos = sorted(set(re.findall(r"\b(MW[A-Z]{2}) AD 2\.1\b", ad)))
    for icao in icaos:
        # the first "XXXX AD 2.1" is the table of contents; the text starts at the last one
        starts = [m.start() for m in re.finditer(rf"\b{icao} AD 2\.1\b", ad)]
        others = [m.start() for o in icaos if o != icao for m in re.finditer(rf"\b{o} AD 2\.1\b", ad)]
        stop = min((s for s in others if s > starts[-1]), default=len(ad))
        a = parse_aerodrome(ad[starts[-1]:stop], icao=icao)
        if a:
            a["icao"] = icao
            col.add_aerodrome(a, "AD 2", ad_url)
    log(f"  {amdt}")
    return col
