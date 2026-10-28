"""Reunion (France) - French SIA eAIP "RUN" (AIP RUN).

HTML eAIP at /media/dvd/eAIP_<DD_MON_YYYY>/RUN/AIRAC-<date>/html/.
Aerodromes: FME* (FMEE Roland Garros, FMEP Pierrefonds).
"""
import re
from datetime import date, timedelta

from ..common import clean, fetch, fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

SIA = "https://www.sia.aviation-civile.gouv.fr/media/dvd/"
SOURCE = "eAIP RUN (SIA France)"
AIRAC_EPOCH = date(2026, 1, 22)  # AIRAC 01/26
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def current_base():
    """Newest AIRAC cycle whose eAIP is online (the SIA publishes ahead of time)."""
    today = date.today()
    cycle = AIRAC_EPOCH + timedelta(days=28 * ((today - AIRAC_EPOCH).days // 28))
    for d in (cycle, cycle - timedelta(days=28), cycle - timedelta(days=56)):
        base = f"{SIA}eAIP_{d.day:02d}_{MONTHS[d.month - 1]}_{d.year}/RUN/AIRAC-{d.isoformat()}/html/"
        try:
            fetch(base + "index-fr-FR.html")
            return base, d
        except Exception:
            continue
    raise RuntimeError("no RUN eAIP found for the last three AIRAC cycles")


def scrape(log):
    base, cycle = current_base()
    eaip = base + "eAIP/"
    col = Collection(SOURCE, cycle.isoformat(), f"AIRAC {cycle.month:02d}/{cycle.year % 100:02d}", base + "index-fr-FR.html")
    page = lambda name: fetch_text(f"{eaip}FR-{name}-fr-FR.html")

    # ENR 4.4 significant points
    url = f"{eaip}FR-ENR-4.4-fr-FR.html"
    col.documents += 1
    for r in rows(page("ENR-4.4")):
        c = coord(r[1]) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]):
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                              "usage": r[2] if len(r) > 2 else None}, "ENR 4.4", url)

    # ENR 4.1 navaids: station | service | ID | FREQ | HOR | coordinates ...
    url = f"{eaip}FR-ENR-4.1-fr-FR.html"
    col.documents += 1
    for r in rows(page("ENR-4.1")):
        c = coord(r[5]) if len(r) > 5 else None
        if not c:
            continue
        f = re.search(r"(\d+(?:\.\d+)?)\s*(MHz|kHz)", r[3], re.I)
        col.add_navaid({"ident": r[2], "type": r[1].replace("-", "/"), "name": r[0],
                        "frequency": float(f.group(1)) if f else None,
                        "frequency_unit": f.group(2).upper() if f else None, "raw_frequency": r[3],
                        "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", url)

    # ENR 3.2 routes
    url = f"{eaip}FR-ENR-3.2-fr-FR.html"
    col.documents += 1
    routes = parse_routes(text(page("ENR-3.2")))
    for r in routes:
        if len(r["points"]) >= 2:
            col.add_route(r, "ENR 3.2", url, lambda p: point_key(p["name"]), nav_spec="RNAV 5")

    # AD 2 aerodromes in Reunion (FMEE, FMEP)
    menu = fetch_text(eaip + "FR-menu-fr-FR.html")
    icaos = sorted(set(re.findall(r"FR-AD-2\.(FME[A-Z])-fr-FR\.html", menu)))
    log(f"  AD 2: {len(icaos)} aerodromes")
    for icao in icaos:
        url = f"{eaip}FR-AD-2.{icao}-fr-FR.html"
        col.documents += 1
        rec = parse_ad2(page(f"AD-2.{icao}"), icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", url)
    return col

