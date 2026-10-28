"""French Guiana - French SIA eAIP "CAR SAM NAM" (Antilles, Guyane, Saint-Pierre et Miquelon).

HTML eAIP at /media/dvd/eAIP_<DD_MON_YYYY>/CAR-SAM-NAM/AIRAC-<date>/html/. The
publication also covers the French Antilles and Saint-Pierre; only French
Guiana is kept: SO** aerodromes and ENR items south of 11°N (Cayenne FIR).
"""
import re
from datetime import date, timedelta

from ..common import clean, fetch, fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

SIA = "https://www.sia.aviation-civile.gouv.fr/media/dvd/"
SOURCE = "eAIP CAR SAM NAM (SIA France)"
MAX_LAT = 11.0
AIRAC_EPOCH = date(2026, 1, 22)  # AIRAC 01/26
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def current_base():
    """Newest AIRAC cycle whose eAIP is online (the SIA publishes ahead of time)."""
    today = date.today()
    cycle = AIRAC_EPOCH + timedelta(days=28 * ((today - AIRAC_EPOCH).days // 28))
    for d in (cycle, cycle - timedelta(days=28), cycle - timedelta(days=56)):
        base = f"{SIA}eAIP_{d.day:02d}_{MONTHS[d.month - 1]}_{d.year}/CAR-SAM-NAM/AIRAC-{d.isoformat()}/html/"
        try:
            fetch(base + "index-fr-FR.html")
            return base, d
        except Exception:
            continue
    raise RuntimeError("no CAR-SAM-NAM eAIP found for the last three AIRAC cycles")


def scrape(log):
    base, cycle = current_base()
    eaip = base + "eAIP/"
    col = Collection(SOURCE, cycle.isoformat(), f"AIRAC {cycle.month:02d}/{cycle.year % 100:02d}", base + "index-fr-FR.html")
    page = lambda name: fetch_text(f"{eaip}FR-{name}-fr-FR.html")

    # ENR 4.4 significant points: name | coordinates | ATS routes | remarks
    url = f"{eaip}FR-ENR-4.4-fr-FR.html"
    col.documents += 1
    for r in rows(page("ENR-4.4")):
        c = coord(r[1]) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]) and c[0] < MAX_LAT:
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                              "usage": r[2] if len(r) > 2 else None}, "ENR 4.4", url)

    # ENR 4.1 navaids: station | service | ID | FREQ | HOR | coordinates ...
    url = f"{eaip}FR-ENR-4.1-fr-FR.html"
    col.documents += 1
    for r in rows(page("ENR-4.1")):
        c = coord(r[5]) if len(r) > 5 else None
        if not c or c[0] >= MAX_LAT:
            continue
        f = re.search(r"(\d+(?:\.\d+)?)\s*(MHz|kHz)", r[3], re.I)
        col.add_navaid({"ident": r[2], "type": r[1].replace("-", "/"), "name": r[0],
                        "frequency": float(f.group(1)) if f else None,
                        "frequency_unit": f.group(2).upper() if f else None, "raw_frequency": r[3],
                        "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", url)

    # ENR 3.2 routes: designator line, then "symbol | point name | coordinates" rows
    url = f"{eaip}FR-ENR-3.2-fr-FR.html"
    col.documents += 1
    routes = parse_routes(text(page("ENR-3.2")))
    for r in routes:
        if len(r["points"]) >= 2 and any(p["lat"] < MAX_LAT for p in r["points"]):
            col.add_route(r, "ENR 3.2", url, lambda p: point_key(p["name"]), nav_spec="RNAV 5")

    # AD 2 aerodromes in French Guiana
    menu = fetch_text(eaip + "FR-menu-fr-FR.html")
    icaos = sorted(set(re.findall(r"FR-AD-2\.(SO[A-Z]{2})-fr-FR\.html", menu)))
    log(f"  AD 2: {len(icaos)} aerodromes")
    for icao in icaos:
        url = f"{eaip}FR-AD-2.{icao}-fr-FR.html"
        col.documents += 1
        rec = parse_ad2(page(f"AD-2.{icao}"), icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", url)
    return col

