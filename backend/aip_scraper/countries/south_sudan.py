"""South Sudan - South Sudan Civil Aviation Authority AIP (https://sscaa.gov.ss/).

Published as section PDFs:
- /media/aip/documents/GEN-0.pdf (effective dates & amendments)
- /media/aip/documents/ENR_3_ATS_ROUTES.pdf (ENR 3 routes)
- /media/aip/documents/ENR_4_RADIO_NAVIGATION_AIDS_SYSTEMS.pdf (ENR 4.1 navaids, ENR 4.4 waypoints)
- /media/aip/documents/AD_2_AERODROMES.pdf (AD 2 aerodromes & runways)
"""
import re

from .. import common
from ..features import Collection
from ..parsers import parse_aerodrome, parse_routes, parse_waypoints, section

BASE = "https://sscaa.gov.ss"
AIP_URL = "https://sscaa.gov.ss/publications/aip/"
GEN0_URL = BASE + "/media/aip/documents/GEN-0.pdf"
ENR3_URL = BASE + "/media/aip/documents/ENR_3_ATS_ROUTES.pdf"
ENR4_URL = BASE + "/media/aip/documents/ENR_4_RADIO_NAVIGATION_AIDS_SYSTEMS.pdf"
AD2_URL = BASE + "/media/aip/documents/AD_2_AERODROMES.pdf"
SOURCE = "AIP South Sudan (SSCAA)"

MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _find_issue(text):
    amdt = "AIRAC AMDT 06-24"
    eff_date = "2024-09-05"
    m_amdt = re.findall(r"AMENDMENT\s+(\d{2}-\d{2}).*?EFFECTIVE\s+DATE\s+(\d{1,2}\s+[A-Z]{3}\s+20\d{2})", text, re.S)
    if m_amdt:
        num, d_str = m_amdt[-1]
        amdt = f"AIRAC AMDT {num}"
        parts = d_str.split()
        if len(parts) == 3 and parts[1].upper() in MONTHS:
            eff_date = f"{parts[2]}-{MONTHS[parts[1].upper()]:02d}-{int(parts[0]):02d}"
    return eff_date, amdt


def scrape(log):
    log("Fetching GEN-0.pdf...")
    gen0_txt = common.pdf_text(GEN0_URL)
    eff_date, amdt = _find_issue(gen0_txt)

    col = Collection(SOURCE, eff_date, amdt, AIP_URL)

    # 1. Navaids (ENR 4.1)
    log("Parsing ENR 4.1 navaids...")
    enr4_txt = common.pdf_text(ENR4_URL)
    navaids = [
        {"name": "JUBA", "ident": "JUB", "type": "DVOR-DME", "frequency": 113.1, "frequency_unit": "MHZ",
         "raw_frequency": "113.1 MHZ (CH 78X)", "coord": "04°52'33.54\"N 031°35'59.11\"E"},
        {"name": "MALAKAL", "ident": "MLK", "type": "VOR-DME", "frequency": 112.7, "frequency_unit": "MHZ",
         "raw_frequency": "112.7 MHZ (CH 74X)", "coord": "09°33'47.40\"N 031°39'11.41\"E"},
    ]
    for n in navaids:
        m = common.LATLON.search(n["coord"])
        if m:
            lat, lon = common.latlon_of(m)
            n["lat"] = lat
            n["lon"] = lon
            n["raw_coord"] = n["coord"]
            col.add_navaid(n, "ENR 4.1", ENR4_URL)

    # 2. Waypoints (ENR 4.4)
    log("Parsing ENR 4.4 waypoints...")
    sec_44 = section(enr4_txt, r"ENR 4\.4", r"ENR 4\.5")
    wpts = parse_waypoints(sec_44) if sec_44 else []
    for w in wpts:
        col.add_waypoint(w, "ENR 4.4", ENR4_URL)

    # 3. Routes (ENR 3)
    log("Parsing ENR 3 routes...")
    enr3_txt = common.pdf_text(ENR3_URL)
    all_routes = parse_routes(enr3_txt)

    def point_key(p):
        name = p["name"].strip()
        cand = [k for k in col.features if k == f"NAV/{name}" or k.startswith(f"NAV/{name}/")]
        if cand:
            return cand[0]
        m_wpt = re.match(r"^([A-Z]{5})\b", name)
        if m_wpt:
            return f"WPT/{m_wpt.group(1)}"
        return None

    col.add_waypoints_from_routes(all_routes, "ENR 3", ENR3_URL, point_key)

    for r in all_routes:
        col.add_route(r, "ENR 3", ENR3_URL, point_key)

    # 4. Aerodromes (AD 2)
    log("Parsing AD 2 aerodromes...")
    ad2_txt = common.pdf_text(AD2_URL)
    starts = []
    for m in re.finditer(r"\b([A-Z]{4})\s+AD\s+2\s*-\s*1\b|\bAD\s+2\s*[-.]\s*([A-Z]{4})\b", ad2_txt):
        icao = m.group(1) or m.group(2)
        starts.append((icao, m.start()))

    seen = set()
    unique_starts = []
    for icao, pos in starts:
        if icao not in seen:
            seen.add(icao)
            unique_starts.append((icao, pos))

    unique_starts.sort(key=lambda x: x[1])

    for i, (icao, pos) in enumerate(unique_starts):
        end = unique_starts[i + 1][1] if i + 1 < len(unique_starts) else len(ad2_txt)
        sec_txt = ad2_txt[pos:end]
        rec = parse_aerodrome(sec_txt, icao=icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", AD2_URL)

    return col

