"""North Macedonia - M-NAV eAIP (http://ais.m-nav.info/eAIP/current/en/index.htm).

PDF-based sections linked from the eAIP structure. Prefix "LW".
"""
from datetime import datetime
import re

from ..common import LAT, LON, fetch_text, lat_of, lon_of, pdf_text
from ..features import Collection
from ..parsers import parse_aerodrome, parse_routes, point_key

INDEX = "http://ais.m-nav.info/eAIP/current/en/index.htm"
TOP = "http://ais.m-nav.info/eAIP/current/en/top.htm"
BASE_PDF = "http://ais.m-nav.info/eAIP/current/pdf/"
SOURCE = "eAIP North Macedonia (M-NAV)"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
NAV_TYPE = re.compile(r"\b(VOR/DME|VOR|NDB/DME|NDB|DME)\b")


def near(lines, i, pattern, offsets):
    for o in offsets:
        if 0 <= i + o < len(lines):
            m = pattern.search(lines[i + o])
            if m:
                return m
    return None


def scrape(log):
    top_html = fetch_text(TOP)
    m_date = re.search(r"valid from\s+(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", top_html, re.I)
    if m_date:
        d, m, y = int(m_date.group(1)), MONTHS[m_date.group(2).upper()], int(m_date.group(3))
        eff_date = f"{y:04d}-{m:02d}-{d:02d}"
    else:
        eff_date = "2026-10-15"

    m_amdt = re.search(r"AIP\s*\(([^)]+)\)", top_html)
    amdt_id = f"AIP ({m_amdt.group(1)})" if m_amdt else f"AIP {eff_date}"

    col = Collection(SOURCE, eff_date, amdt_id, INDEX)

    # 1. Aerodromes
    for icao in ["LWSK", "LWOH"]:
        ad_url = f"{BASE_PDF}aerodromes/LW_AD_2_{icao}_en.pdf"
        try:
            txt = pdf_text(ad_url)
            rec = parse_aerodrome(txt, icao)
            if rec:
                col.documents += 1
                col.add_aerodrome(rec, f"{icao} AD 2", ad_url)
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", f"{ad_url}: {e}")

    # 2. Waypoints
    wpt_url = f"{BASE_PDF}enr/LW_ENR_4_4_en.pdf"
    try:
        txt_wpt = pdf_text(wpt_url)
        col.documents += 1
        lines = txt_wpt.splitlines()
        for i, l in enumerate(lines):
            m = re.match(r"\s*([A-Z]{5})\s", l)
            la = near(lines, i, LAT, (0, -1, 1))
            lo = near(lines, i, LON, (0, 1, -1))
            if m and la and lo:
                col.add_waypoint(
                    {
                        "ident": m.group(1),
                        "lat": lat_of(la),
                        "lon": lon_of(lo),
                        "raw_coord": f"{la.group(0)} {lo.group(0)}",
                    },
                    "LW ENR 4.4",
                    wpt_url,
                )
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.4", "LW ENR 4.4", f"{wpt_url}: {e}")

    # 3. Navaids
    nav_url = f"{BASE_PDF}enr/LW_ENR_4_1_en.pdf"
    try:
        txt_nav = pdf_text(nav_url)
        col.documents += 1
        lines = txt_nav.splitlines()
        for i, l in enumerate(lines):
            m = re.search(r"\b([A-Z]{3})\s+H24\b", l)
            if not m:
                continue
            ident = m.group(1)
            la = near(lines, i, LAT, (-1, 0, 1))
            lo = near(lines, i, LON, (0, 1, 2))
            context = " ".join(lines[max(0, i - 4) : i + 3])
            t = NAV_TYPE.search(context)
            name_m = re.search(r"\b([A-Z]{4,15})\b", lines[max(0, i - 3)])
            f = re.search(r"(\d{3}(?:\.\d+)?)\s*(MHZ|KHZ)", context, re.I)
            if la and lo:
                col.add_navaid(
                    {
                        "ident": ident,
                        "type": t.group(1) if t else None,
                        "name": name_m.group(1) if name_m else None,
                        "freq": f.group(0) if f else None,
                        "lat": lat_of(la),
                        "lon": lon_of(lo),
                        "raw_coord": f"{la.group(0)} {lo.group(0)}",
                    },
                    "LW ENR 4.1",
                    nav_url,
                )
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.1", "LW ENR 4.1", f"{nav_url}: {e}")

    # 4. Routes
    for s in ["LW_ENR_3_1_en.pdf", "LW_ENR_3_2_en.pdf", "LW_ENR_3_3_en.pdf"]:
        r_url = f"{BASE_PDF}enr/{s}"
        try:
            txt_r = pdf_text(r_url)
            col.documents += 1
            for rte in parse_routes(txt_r):
                col.add_route(rte, s[:8], r_url, lambda p: point_key(p["name"]))
        except Exception:
            pass

    return col
