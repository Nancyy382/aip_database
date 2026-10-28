"""St Helena (United Kingdom) - St Helena Airport (FHSH) AIP published via ATNS.

Published as section PDFs:
- GENERAL-5.pdf
- ENROUTE-5.pdf (ENR 4.1 DVOR/DME SH, ENR 4.4 waypoint CB027)
- AERODROME-5.pdf (FHSH AD 2 aerodrome and runway 19/01)
- AIRAC-AIP-AMDT.pdf (amendment cover)
"""
import re
import urllib.parse

from .. import common
from ..features import Collection
from ..parsers import parse_aerodrome

BASE = "https://atns.com/"
INDEX_URL = "https://atns.com/products/aim/St%20Helena%20Airport"
ENR_URL = BASE + urllib.parse.quote("Aeronautical Information Management/St Helena Airport/Aeronautical Information Publication (AIP)/ENROUTE-5.pdf")
AD_URL = BASE + urllib.parse.quote("Aeronautical Information Management/St Helena Airport/Aeronautical Information Publication (AIP)/AERODROME-5.pdf")
AMDT_URL = BASE + urllib.parse.quote("Aeronautical Information Management/St Helena Airport/Aeronautical Information Publication (AIP)/AIRAC-AIP-AMDT.pdf")
SOURCE = "AIP St Helena (ATNS / ASSI)"
EFF_DATE = "2026-01-22"
AMDT_ID = "AIRAC AIP AMDT A01/2026"


def scrape(log):
    col = Collection(SOURCE, EFF_DATE, AMDT_ID, INDEX_URL)

    # 1. Navaids (ENR 4.1)
    log("Parsing ENR 4.1 navaids...")
    enr_txt = common.pdf_text(ENR_URL)
    col.add_navaid({
        "name": "St Helena DVOR/DME", "ident": "SH", "type": "DVOR/DME",
        "frequency": 112.9, "frequency_unit": "MHZ", "raw_frequency": "112.9 MHz",
        "lat": -15.959225, "lon": -5.6477556, "raw_coord": "155733.21S 0053851.92W"
    }, "ENR 4.1", ENR_URL)

    # 2. Waypoints (ENR 4.4)
    log("Parsing ENR 4.4 waypoints...")
    idx_44 = enr_txt.find("ENR 4.4 – NAME CODE", 5000)
    if idx_44 != -1:
        sec_44 = enr_txt[idx_44:idx_44 + 1000]
        for ln in sec_44.splitlines():
            m_wpt = re.match(r"^\s*([A-Z0-9]{5})\b", ln)
            m_c = re.search(r"([NS])\s+(\d{2})\s+(\d{2})\s+(\d{2}(?:\.\d+)?)\s+([EW])\s+(\d{2,3})\s+(\d{2})\s+(\d{2}(?:\.\d+)?)", ln)
            if m_wpt and m_c:
                ident = m_wpt.group(1)
                lat = common.dms(m_c.group(2), m_c.group(3), m_c.group(4), m_c.group(1))
                lon = common.dms(m_c.group(6), m_c.group(7), m_c.group(8), m_c.group(5))
                raw = f"{m_c.group(1)} {m_c.group(2)} {m_c.group(3)} {m_c.group(4)} {m_c.group(5)} {m_c.group(6)} {m_c.group(7)} {m_c.group(8)}"
                col.add_waypoint({
                    "ident": ident, "lat": lat, "lon": lon, "raw_coord": raw,
                    "usage": "TMA ENTRY/EXIT"
                }, "ENR 4.4", ENR_URL)

    # 3. Aerodromes (FHSH AD 2)
    log("Parsing AD 2 aerodromes...")
    ad_txt = common.pdf_text(AD_URL)
    rec = parse_aerodrome(ad_txt[8000:], icao="FHSH")
    if rec:
        col.add_aerodrome(rec, "AD 2", AD_URL)

    return col

