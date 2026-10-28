"""South Africa - South African Civil Aviation Authority / ATNS AIP.

Published via SACAA website / Azure Blob Storage as section PDFs:
- Enroute (15_OCT_2026).pdf (ENR 3 routes, ENR 4.1 navaids, ENR 4.4 waypoints)
- Aerodromes (15_OCT_2026).PDF (AD 2 aerodromes and runways)
"""
import re
import urllib.parse

from .. import common
from ..features import Collection
from ..parsers import parse_aerodrome, parse_routes, section

BASE = "https://caasanwebsitestorage.blob.core.windows.net/aeronautical-information-publication/"
ENR_URL = BASE + urllib.parse.quote("Enroute (15_OCT_2026).pdf")
AD_URL = BASE + urllib.parse.quote("Aerodromes (15_OCT_2026).PDF")
SOURCE_URL = "https://www.caa.co.za/industry-information/aip-amendments/"
SOURCE = "AIP South Africa (SACAA / ATNS)"
EFF_DATE = "2026-10-15"
AMDT_ID = "AIRAC AMDT 10/26"


def scrape(log):
    col = Collection(SOURCE, EFF_DATE, AMDT_ID, SOURCE_URL)

    log("Fetching Enroute PDF...")
    enr_txt = common.pdf_text(ENR_URL)
    log("Fetching Aerodromes PDF...")
    ad_txt = common.pdf_text(AD_URL)

    # 1. Navaids (ENR 4.1)
    log("Parsing ENR 4.1 navaids...")
    idx_start = enr_txt.find("ENR 4.1 RADIO NAVIGATION AIDS― EN-ROUTE")
    idx_end = enr_txt.find("ENR 4.2", idx_start)
    sec_41 = enr_txt[idx_start:idx_end]
    lines = sec_41.splitlines()
    seen_nav = set()
    for i, ln in enumerate(lines):
        m_id = re.search(r"/\s*([A-Z]{3})\b", ln)
        if m_id and m_id.group(1) != "DME":
            ident = m_id.group(1)
            if ident in seen_nav:
                continue
            window = "\n".join(lines[max(0, i - 3):min(len(lines), i + 4)])
            m_c = common.LATLON.search(window)
            if not m_c:
                m_lat = re.search(r"\b([0-9]{6}(?:\.[0-9]+)?[NS])\b", window)
                m_lon = re.search(r"\b([0-9]{7}(?:\.[0-9]+)?[EW])\b", window)
                if m_lat and m_lon:
                    m_c = common.LATLON.search(f"{m_lat.group(1)} {m_lon.group(1)}")
            if m_c:
                seen_nav.add(ident)
                lat, lon = common.latlon_of(m_c)
                name = ""
                for k in range(i - 1, max(-1, i - 4), -1):
                    prev = lines[k].strip()
                    if prev and not prev.startswith("ENR") and not prev.startswith("AIRAC"):
                        parts = re.split(r"\s{3,}", prev)
                        if parts and re.match(r"^[A-Z\s/-]+$", parts[0]):
                            name = parts[0].strip()
                            break
                m_type = re.search(r"\b(D?VOR/DME|D?VOR|NDB|DME|TACAN|VORTAC)\b", window)
                nav_type = m_type.group(1) if m_type else "VOR/DME"
                m_freq = re.search(r"(\d{3,4}(?:\.\d+)?)\s*(MHz|kHz)", window, re.I)
                col.add_navaid({
                    "ident": ident, "name": name, "type": nav_type,
                    "lat": lat, "lon": lon, "raw_coord": m_c.group(0),
                    "frequency": float(m_freq.group(1)) if m_freq else None,
                    "frequency_unit": m_freq.group(2).upper() if m_freq else None,
                    "raw_frequency": m_freq.group(0) if m_freq else None
                }, "ENR 4.1", ENR_URL)

    # 2. Waypoints (ENR 4.4)
    log("Parsing ENR 4.4 waypoints...")
    idx_w_start = enr_txt.find("ENR 4.4 Name-code designators of significant points")
    idx_w_end = enr_txt.find("ENR 4.5", idx_w_start)
    sec_44 = enr_txt[idx_w_start:idx_w_end]
    for page in sec_44.split("\x0c"):
        left_lines = []
        right_lines = []
        for ln in page.splitlines():
            if len(ln) > 45:
                left_lines.append(ln[:45])
                right_lines.append(ln[45:])
            else:
                left_lines.append(ln)
                right_lines.append("")
        for half in (left_lines, right_lines):
            txt_half = "\n".join(half)
            for m in re.finditer(r"(?:([0-9]{6}(?:\.[0-9]+)?[NS])\s*\n\s*)?([A-Z]{5})\b(?:\s+([0-9]{6}(?:\.[0-9]+)?[NS]))?\s*\n\s*([0-9]{7}(?:\.[0-9]+)?[EW])", txt_half):
                lat_str = m.group(1) or m.group(3)
                ident = m.group(2)
                lon_str = m.group(4)
                if lat_str and lon_str:
                    m_c = common.LATLON.search(f"{lat_str} {lon_str}")
                    if m_c:
                        lat, lon = common.latlon_of(m_c)
                        col.add_waypoint({
                            "ident": ident, "lat": lat, "lon": lon,
                            "raw_coord": f"{lat_str} {lon_str}"
                        }, "ENR 4.4", ENR_URL)

    # 3. Routes (ENR 3)
    log("Parsing ENR 3 routes...")
    sec_3 = section(enr_txt[20000:], r"ENR 3\.1\s+LOWER", r"ENR 4\.") or section(enr_txt[20000:], r"ENR 3\.", r"ENR 4\.")
    all_routes = parse_routes(sec_3) if sec_3 else []

    def point_key(p):
        name = (p.get("name") or "").strip()
        if not name:
            return None
        cand = [k for k in col.features if k == f"NAV/{name}" or k.startswith(f"NAV/{name}/")]
        if cand:
            return cand[0]
        m_wpt = re.match(r"^([A-Z]{5})\b", name)
        if m_wpt:
            return f"WPT/{m_wpt.group(1)}"
        return None

    col.add_waypoints_from_routes(all_routes, "ENR 3", ENR_URL, point_key)

    for r in all_routes:
        col.add_route(r, "ENR 3", ENR_URL, point_key)

    # 4. Aerodromes (AD 2)
    log("Parsing AD 2 aerodromes...")
    starts = []
    for m in re.finditer(r"\b(FA[A-Z]{2})\s+AD\s+2\.1\b", ad_txt):
        starts.append((m.group(1), m.start()))

    seen_ad = set()
    unique_starts = []
    for icao, pos in starts:
        if icao not in seen_ad:
            seen_ad.add(icao)
            unique_starts.append((icao, pos))

    unique_starts.sort(key=lambda x: x[1])

    for i, (icao, pos) in enumerate(unique_starts):
        end = unique_starts[i + 1][1] if i + 1 < len(unique_starts) else len(ad_txt)
        sec_txt = ad_txt[pos:end]
        rec = parse_aerodrome(sec_txt, icao=icao)
        if rec and rec.get("lat") and rec.get("lon"):
            col.add_aerodrome(rec, "AD 2", AD_URL)

    return col

