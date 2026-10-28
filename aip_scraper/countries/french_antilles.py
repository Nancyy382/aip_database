"""French Antilles - French SIA eAIP "CAR SAM NAM" (Guadeloupe, Martinique, Saint-Martin, Saint-Barthélemy).

HTML eAIP at /media/dvd/eAIP_<DD_MON_YYYY>/CAR-SAM-NAM/AIRAC-<date>/html/.
Covers TF** aerodromes and ENR items in the Leeward/Windward Islands area (12°N - 20°N, 66°W - 58°W).
"""
import re
from datetime import date, timedelta

from ..common import clean, fetch, fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key
from .french_guiana_france import current_base

SOURCE = "eAIP CAR SAM NAM (SIA France)"
MIN_LAT = 12.0
MAX_LAT = 20.0
MIN_LON = -66.0
MAX_LON = -58.0


def _in_bounds(lat, lon):
    return MIN_LAT <= lat <= MAX_LAT and MIN_LON <= lon <= MAX_LON


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
        if c and re.fullmatch(r"[A-Z]{5}", r[0]) and _in_bounds(c[0], c[1]):
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                              "usage": r[2] if len(r) > 2 else None}, "ENR 4.4", url)

    # ENR 4.1 navaids
    url = f"{eaip}FR-ENR-4.1-fr-FR.html"
    col.documents += 1
    for r in rows(page("ENR-4.1")):
        c = coord(r[5]) if len(r) > 5 else None
        if not c or not _in_bounds(c[0], c[1]):
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
        if len(r["points"]) >= 2 and any(_in_bounds(p["lat"], p["lon"]) for p in r["points"]):
            col.add_route(r, "ENR 3.2", url, lambda p: point_key(p["name"]), nav_spec="RNAV 5")

    # AD 2 aerodromes in French Antilles (TF**)
    menu = fetch_text(eaip + "FR-menu-fr-FR.html")
    icaos = sorted(set(re.findall(r"FR-AD-2\.(TF[A-Z]{2})-fr-FR\.html", menu)))
    log(f"  AD 2: {len(icaos)} aerodromes")
    for icao in icaos:
        url = f"{eaip}FR-AD-2.{icao}-fr-FR.html"
        col.documents += 1
        rec = parse_ad2(page(f"AD-2.{icao}"), icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", url)
    return col

