"""Haiti - OFNAC IAIP (https://ofnac.gouv.ht/IAIP.php?lang=fr)."""
from urllib.parse import urljoin
import re

from ..common import fetch, pdf_bytes_text
from ..eaip_html import coord
from ..features import Collection
from ..parsers import parse_routes, point_key

BASE_PAGE = "https://ofnac.gouv.ht/IAIP.php?lang=fr"
PDF_URL = "https://ofnac.gouv.ht/fichierPDF/AIP-HAITI-AMDT0120-version-Francaise.pdf"
SOURCE = "IAIP République d'Haïti (OFNAC)"
EFF = "2023-11-30"
AMDT = "AIRAC AIP AMDT 01-23"


def scrape(log):
    col = Collection(SOURCE, EFF, AMDT, BASE_PAGE)
    col.documents += 1
    txt = pdf_bytes_text(fetch(PDF_URL), "AIP-HAITI.pdf")

    # 1. ENR 4.1 Navaids
    c_pap = coord("183435.52N 0721815.26W")
    col.add_navaid({
        "ident": "PAP", "type": "VOR/DME", "name": "PORT-AU-PRINCE",
        "frequency": 115.3, "frequency_unit": "MHZ", "raw_frequency": "115.300 MHZ",
        "lat": c_pap[0], "lon": c_pap[1], "raw_coord": c_pap[2]
    }, "ENR 4.1", PDF_URL)
    log("  ENR 4.1: 1 navaid")

    # 2. ENR 4.3 Waypoints (under ENR 4.3 in Haiti AIP)
    idx_start = txt.find("ENR 4.3 INDICATIFS CODES DES POINTS SIGNIFICATIFS")
    idx_end = txt.find("ENR 4.4 FEUX AERONAUTIQUES AU SOL", idx_start)
    pts_sec = txt[idx_start:idx_end] if idx_start != -1 and idx_end != -1 else ""
    wpts_count = 0
    for l in pts_sec.splitlines():
        m = re.search(r"^\s*([A-Z]{5})\s+(\d{6}(?:\.\d+)?N)\s+(\d{7}(?:\.\d+)?W)\s*(.*?)$", l)
        if m:
            c = coord(f"{m.group(2)} {m.group(3)}")
            col.add_waypoint({
                "ident": m.group(1), "lat": c[0], "lon": c[1], "raw_coord": c[2],
                "usage": m.group(4).strip() or None
            }, "ENR 4.3", PDF_URL)
            wpts_count += 1
    log(f"  ENR 4.3: {wpts_count} waypoints")

    # 3. ENR 3.3 Routes
    idx_r_start = txt.find("ENR 3.3 ROUTES DE NAVIGATION DE SURFACE (RNAV)")
    idx_r_end = txt.find("ENR 3.4 ROUTES D’HELICOPTERES", idx_r_start)
    r_sec = txt[idx_r_start:idx_r_end] if idx_r_start != -1 and idx_r_end != -1 else ""
    routes = parse_routes(r_sec)
    for r in routes:
        col.add_route(r, "ENR 3.3", PDF_URL, lambda p: point_key(p["name"]), nav_spec="RNAV")
    log(f"  ENR 3.3: {len(routes)} routes")

    # 4. AD 2 Aerodromes
    # MTPP - Port-au-Prince
    c_mtpp_arp = coord("183448.18N 0721733.15W")
    c_mtpp_10 = coord("183445.58N 0721824.92W")
    c_mtpp_28 = coord("183450.79N 0721641.37W")
    ad_mtpp = {
        "icao": "MTPP", "name": "AÉROPORT INTERNATIONAL TOUSSAINT LOUVERTURE",
        "lat": c_mtpp_arp[0], "lon": c_mtpp_arp[1], "raw_coord": c_mtpp_arp[2],
        "elevation_ft": 122, "raw_elevation": "37m (122 pieds)",
        "runways": [{
            "pair": "10-28", "length": 3060.0, "width": 45.0, "raw_dims": "3060 x 45", "surface": "CONC",
            "ends": [
                {"designator": "10", "lat": c_mtpp_10[0], "lon": c_mtpp_10[1], "raw_coord": c_mtpp_10[2],
                 "bearing": 87.0, "surface": "CONC"},
                {"designator": "28", "lat": c_mtpp_28[0], "lon": c_mtpp_28[1], "raw_coord": c_mtpp_28[2],
                 "bearing": 267.0, "surface": "CONC"}
            ]
        }]
    }
    col.add_aerodrome(ad_mtpp, "MTPP AD 2", PDF_URL)

    # MTCH - Cap-Haïtien
    c_mtch_arp = coord("194358N 0721141W")
    c_mtch_05 = coord("194304.94N 0721227.04W")
    c_mtch_23 = coord("194411.26N 0721108.09W")
    ad_mtch = {
        "icao": "MTCH", "name": "AÉROPORT INTERNATIONAL DU CAP-HAÏTIEN",
        "lat": c_mtch_arp[0], "lon": c_mtch_arp[1], "raw_coord": c_mtch_arp[2],
        "elevation_ft": 10, "raw_elevation": "3m (10 pieds)",
        "runways": [{
            "pair": "05-23", "length": 2652.0, "width": 45.0, "raw_dims": "2652 x 45", "surface": "ASPH",
            "ends": [
                {"designator": "05", "lat": c_mtch_05[0], "lon": c_mtch_05[1], "raw_coord": c_mtch_05[2],
                 "bearing": 39.0, "surface": "ASPH"},
                {"designator": "23", "lat": c_mtch_23[0], "lon": c_mtch_23[1], "raw_coord": c_mtch_23[2],
                 "bearing": 219.0, "surface": "ASPH"}
            ]
        }]
    }
    col.add_aerodrome(ad_mtch, "MTCH AD 2", PDF_URL)
    log("  AD 2: 2 aerodromes")

    return col

