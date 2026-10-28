"""Rwanda - Rwanda Airports Company / Rwanda CAA eAIP (hosted via ASECNA).

Standard IDS AirNav eAIP structure with space-separated file names:
"HR-ENR 4.1-en-GB.html", "HR-ENR 4.4-en-GB.html", "HR-AD 2 <ICAO>-en-GB.html".
"""
import re
import urllib.parse

from .. import common
from ..eaip_html import coord, parse_ad2, rows
from ..features import Collection
from ..parsers import point_key

BASE_URL = "https://aim.asecna.aero/eAIP_Rwanda/01-26_2026_08_06/eAIP/"
INDEX_URL = "https://aim.asecna.aero/eAIP_Rwanda/01-26_2026_08_06/index.html"
SOURCE = "eAIP Rwanda (RAC)"
EFF_DATE = "2026-08-06"
AMDT_ID = "AIRAC AMDT 01/26"

NAV_TYPE = re.compile(r"\b(VOR[/-]TACAN|D?VOR[/-]DME|VORTAC|D?VOR|NDB[/-]DME|NDB|DME|TACAN)\b")

ROUTE_PAGES = [
    "HR-ENR 3.1 B527-en-GB.html", "HR-ENR 3.1 B531-en-GB.html", "HR-ENR 3.1 B607-en-GB.html",
    "HR-ENR 3.1 UB527-en-GB.html", "HR-ENR 3.1 UB531-en-GB.html", "HR-ENR 3.1 UB607-en-GB.html",
    "HR-ENR 3.2 L432 (RNAV 10)-en-GB.html", "HR-ENR 3.2 L442 (RNAV 10)-en-GB.html",
    "HR-ENR 3.2 UL432 (RNAV10)-en-GB.html", "HR-ENR 3.2 UL442 (RNAV10)-en-GB.html",
    "HR-ENR 3.2 UY198 (RNAV10)-en-GB.html"
]

AD_PAGES = [
    ("HRYG", "HR-AD 2 HRYG-en-GB.html"),
    ("HRYI", "HR-AD 2 HRYI-en-GB.html"),
    ("HRYN", "HR-AD 2 HRYN-en-GB.html"),
    ("HRYR", "HR-AD 2 HRYR-en-GB.html"),
    ("HRYU", "HR-AD 2 HRYU-en-GB.html"),
    ("HRZA", "HR-AD 2 HRZA-en-GB.html"),
]


def scrape(log):
    col = Collection(SOURCE, EFF_DATE, AMDT_ID, INDEX_URL)

    # 1. Navaids (HR-ENR 4.1-en-GB.html)
    log("Parsing ENR 4.1 navaids...")
    url_41 = BASE_URL + urllib.parse.quote("HR-ENR 4.1-en-GB.html")
    txt_41 = common.fetch_text(url_41)
    for r in rows(txt_41):
        ci = next((i for i, x in enumerate(r) if coord(x)), None)
        if not ci:
            continue
        t = NAV_TYPE.search(r[0]) or (NAV_TYPE.search(r[1]) if len(r) > 1 else None)
        ident = next((x for x in r[1:ci] if re.fullmatch(r"[A-Z]{2,4}", x) and not NAV_TYPE.fullmatch(x)), None)
        if not (t and ident):
            continue
        c = coord(r[ci])
        f = re.search(r"(\d{3,4}(?:\.\d+)?)\s*(MHZ|KHZ)", " ".join(r[1:ci]), re.I)
        col.add_navaid({
            "ident": ident, "name": r[0].split("\n")[0].strip(), "type": t.group(0),
            "lat": c[0], "lon": c[1], "raw_coord": c[2],
            "frequency": float(f.group(1)) if f else None,
            "frequency_unit": f.group(2).upper() if f else None,
            "raw_frequency": f.group(0) if f else None,
        }, "ENR 4.1", url_41)

    # 2. Waypoints (HR-ENR 4.4-en-GB.html)
    log("Parsing ENR 4.4 waypoints...")
    url_44 = BASE_URL + urllib.parse.quote("HR-ENR 4.4-en-GB.html")
    txt_44 = common.fetch_text(url_44)
    for r in rows(txt_44):
        c = coord(" ".join(r[1:3])) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]):
            col.add_waypoint({
                "ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                "usage": r[2] if len(r) > 2 else None
            }, "ENR 4.4", url_44)

    # 3. Routes (ENR 3)
    log("Parsing ENR 3 routes...")
    all_routes = []
    for rp in ROUTE_PAGES:
        url_rp = BASE_URL + urllib.parse.quote(rp)
        txt_rp = common.fetch_text(url_rp)
        r_list = rows(txt_rp)
        desig = None
        m = re.search(r"HR-ENR\s+3\.\d+\s+([A-Z0-9]+)", rp)
        if m:
            desig = m.group(1)
        for r in r_list:
            if len(r) == 1 and re.fullmatch(r"U?[A-Z]{1,2}\d{1,4}[A-Z]?", r[0].strip()):
                desig = r[0].strip()
                break
        if not desig:
            continue

        points = []
        i = 0
        while i < len(r_list):
            r = r_list[i]
            if len(r) >= 2 and (r[0] in ("▲", "∆", "△", "•") or re.match(r"^[A-Z]{3,5}\b", r[1].strip())):
                pt_name = r[1].strip()
                lat_str = None
                lon_str = None
                for j in range(i + 1, min(len(r_list), i + 4)):
                    rj = r_list[j]
                    line_str = " ".join(rj)
                    c = coord(line_str)
                    if c:
                        lat_str, lon_str = c[0], c[1]
                        break
                    if len(rj) >= 2 and re.search(r"\d{6}(?:\.\d+)?[NS]", rj[1]):
                        lat_str = rj[1].strip()
                    elif len(rj) >= 2 and re.search(r"\d{7}(?:\.\d+)?[EW]", rj[1]):
                        lon_str = rj[1].strip()
                if lat_str and lon_str:
                    if isinstance(lat_str, str):
                        c = coord(lat_str + " " + lon_str)
                        if c:
                            points.append({"name": pt_name, "lat": c[0], "lon": c[1]})
                    else:
                        points.append({"name": pt_name, "lat": lat_str, "lon": lon_str})
            i += 1
        if desig and len(points) >= 2:
            all_routes.append({"designator": desig, "points": points, "url": url_rp})

    def pt_key(p):
        name = p["name"].strip()
        for k in col.features:
            if k.startswith("NAV/"):
                ident = k.split("/")[1]
                if ident in name.split() or f"'{ident}'" in name:
                    return k
        m_wpt = re.match(r"^([A-Z]{5})\b", name)
        if m_wpt:
            return f"WPT/{m_wpt.group(1)}"
        return None

    col.add_waypoints_from_routes(all_routes, "ENR 3", BASE_URL + "menu.html", pt_key)

    for r in all_routes:
        col.add_route(r, "ENR 3", r["url"], pt_key)

    # 4. Aerodromes (AD 2)
    log("Parsing AD 2 aerodromes...")
    for icao, page in AD_PAGES:
        url_ad = BASE_URL + urllib.parse.quote(page)
        txt_ad = common.fetch_text(url_ad)
        rec = parse_ad2(txt_ad, icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", url_ad)

    return col

