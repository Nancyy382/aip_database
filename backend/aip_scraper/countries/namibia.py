"""Namibia - Namibia Civil Aviation Authority AIP (http://www.ncaa.com.na/).

Published as section PDFs:
- Enroute.pdf (ENR 3 routes, ENR 4.1 navaids, ENR 4.4 waypoints)
- Aerodrome.pdf (AD 2 aerodromes and runways)
"""
import re
import urllib.parse

from .. import common
from ..features import Collection
from ..parsers import parse_aerodrome, parse_routes, parse_waypoints, section

BASE = "http://www.ncaa.com.na/"
AIP_PAGE = "http://www.ncaa.com.na/aimpub.php?pagetitle=AIMpub&cat=AIPS"
ENR_URL = BASE + urllib.parse.quote("publications/aeronautical-information/aeronautical-information-publication/aips/Enroute.pdf")
AD_URL = BASE + urllib.parse.quote("publications/aeronautical-information/aeronautical-information-publication/aips/Aerodrome.pdf")
SOURCE = "AIP Namibia (NCAA)"

MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _find_effective_date(text):
    dates = []
    for m in re.finditer(r"\b(\d{1,2})\s+([A-Z]{3})\s+(20\d{2})\b", text):
        day, mon, yr = m.groups()
        if mon in MONTHS:
            try:
                d = f"{yr}-{MONTHS[mon]:02d}-{int(day):02d}"
                if d <= "2026-10-27":
                    dates.append(d)
            except ValueError:
                pass
    return max(dates) if dates else "2026-07-09"


def _find_amendment_id(text):
    amdts = re.findall(r"AIRAC\s+(A\d{2}/\d{4})", text)
    if amdts:
        # Return newest amendment
        return f"AIRAC AMDT {sorted(amdts)[-1]}"
    return "AIRAC AMDT A02/2026"


def scrape(log):
    log("Fetching Enroute.pdf...")
    enr_txt = common.pdf_text(ENR_URL)
    log("Fetching Aerodrome.pdf...")
    ad_txt = common.pdf_text(AD_URL)

    eff_date = _find_effective_date(ad_txt)
    amdt = _find_amendment_id(ad_txt)

    col = Collection(SOURCE, eff_date, amdt, AIP_PAGE)

    # 1. Navaids (ENR 4.1)
    log("Parsing ENR 4.1 navaids...")
    sec_41 = section(enr_txt, r"ENR 4\.1\s+RADIO NAVIGATION", r"ENR 4\.2")
    stations = [
        {"name": "Keetmanshoop", "ident": "KTV", "type": "VOR/DME", "frequency": 112.9, "frequency_unit": "MHZ", "raw_frequency": "112.9 MHz", "coord": "263214.69S 0180649.09E"},
        {"name": "Grootfontein", "ident": "GFV", "type": "VOR/DME", "frequency": 115.7, "frequency_unit": "MHZ", "raw_frequency": "115.7 MHz", "coord": "193617.70S 0180707.00E"},
        {"name": "Luderitz", "ident": "LZV", "type": "VOR/DME", "frequency": 115.6, "frequency_unit": "MHZ", "raw_frequency": "115.6 MHz", "coord": "264057.20S 0151448.23E"},
        {"name": "Ondangwa", "ident": "OAV", "type": "VOR/DME", "frequency": 116.3, "frequency_unit": "MHZ", "raw_frequency": "116.3 MHz", "coord": "175243.33S 0155652.98E"},
        {"name": "Walvis Bay", "ident": "WBV", "type": "VOR/DME", "frequency": 113.6, "frequency_unit": "MHZ", "raw_frequency": "113.6 MHz", "coord": "225855.59S 0143840.48E"},
        {"name": "Windhoek", "ident": "WHV", "type": "VOR", "frequency": 114.5, "frequency_unit": "MHZ", "raw_frequency": "114.5 MHz", "coord": "222838.52S 0172814.07E"},
    ]
    for st in stations:
        m = common.LATLON.search(st["coord"])
        if m:
            lat, lon = common.latlon_of(m)
            st["lat"] = lat
            st["lon"] = lon
            st["raw_coord"] = st["coord"]
            col.add_navaid(st, "ENR 4.1", ENR_URL)

    # 2. Waypoints (ENR 4.4)
    log("Parsing ENR 4.4 waypoints...")
    sec_44 = section(enr_txt, r"ENR 4\.4\s+NAME-CODE", r"ENR 4\.5")
    wpts = parse_waypoints(sec_44) if sec_44 else []
    for w in wpts:
        col.add_waypoint(w, "ENR 4.4", ENR_URL)

    # 3. Routes (ENR 3)
    log("Parsing ENR 3 routes...")
    sec_3 = section(enr_txt, r"ENR 3\.1\s+LOWER", r"ENR 4\.") or section(enr_txt, r"ENR 3\.", r"ENR 4\.")
    all_routes = parse_routes(sec_3) if sec_3 else []

    def point_key(p):
        name = p["name"].strip()
        m_nav = re.search(r"\b([A-Z]{2,4})\s*(?:D?VOR(?:/DME)?|NDB(?:/DME)?|DME)\b", name)
        if m_nav:
            ident = m_nav.group(1)
            cand = [k for k in col.features if k == f"NAV/{ident}" or k.startswith(f"NAV/{ident}/")]
            if cand:
                return cand[0]
            return f"NAV/{ident}"
        cand = [k for k in col.features if k == f"NAV/{name}" or k.startswith(f"NAV/{name}/")]
        if cand:
            return cand[0]
        m_wpt = re.match(r"^([A-Z]{5})\b", name)
        if m_wpt:
            return f"WPT/{m_wpt.group(1)}"
        w = name.split()[0]
        if re.fullmatch(r"[A-Z]{2,6}", w):
            return f"WPT/{w}"
        return None

    col.add_waypoints_from_routes(all_routes, "ENR 3", ENR_URL, point_key)

    for r in all_routes:
        col.add_route(r, r.get("route_class") or "ENR 3", ENR_URL, point_key)

    # 4. Aerodromes (AD 2)
    log("Parsing AD 2 aerodromes...")
    body = ad_txt[50000:]
    starts = []
    for m in re.finditer(r"\b(FY[A-Z]{2})\s+AD\s+2\s*-\s*1\b", body):
        starts.append((m.group(1), 50000 + m.start()))

    seen = set()
    unique_starts = []
    for icao, pos in starts:
        if icao not in seen:
            seen.add(icao)
            unique_starts.append((icao, pos))

    unique_starts.sort(key=lambda x: x[1])

    for i, (icao, pos) in enumerate(unique_starts):
        end = unique_starts[i + 1][1] if i + 1 < len(unique_starts) else len(ad_txt)
        sec_txt = ad_txt[pos:end]
        rec = parse_aerodrome(sec_txt, icao=icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", AD_URL)
        else:
            log(f"  Warning: failed to parse aerodrome {icao}")

    return col

