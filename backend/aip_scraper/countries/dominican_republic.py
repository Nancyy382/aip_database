"""Dominican Republic - IDAC AIP (https://aip.sna.gob.do/)."""
from urllib.parse import urljoin
import re

from ..common import LAT, LON, fetch, lat_of, lon_of, pdf_bytes_text
from ..eaip_html import coord
from ..features import Collection
from ..parsers import parse_aerodrome, parse_routes, point_key

BASE = "https://aip.sna.gob.do/"
SOURCE = "AIP República Dominicana (IDAC)"
EFF = "2025-12-25"
AMDT = "AIRAC AMDT 02/25"

INTL_ADS = ["MDSD", "MDPC", "MDPP", "MDLR", "MDST", "MDJB", "MDCY", "MDBH", "MDSI"]


def near(lines, i, pattern, offsets):
    for o in offsets:
        if 0 <= i + o < len(lines):
            m = pattern.search(lines[i + o])
            if m:
                return m
    return None


def parse_dr_waypoints(txt):
    txt = txt.replace("´", "'")
    lines = txt.splitlines()
    wpts = []
    for i, l in enumerate(lines):
        m = re.match(r"^\s*([A-Z]{5})\s", l)
        if m:
            la = near(lines, i, LAT, (0, -1, -2))
            lo = near(lines, i, LON, (0, 1, 2))
            if la and lo:
                wpts.append({
                    "ident": m.group(1), "lat": lat_of(la), "lon": lon_of(lo),
                    "raw_coord": f"{la.group(0)} {lo.group(0)}"
                })
    return wpts


def parse_dr_navaids(txt):
    lines = txt.splitlines()
    navs = []
    for i, l in enumerate(lines):
        m = re.match(r"^\s*([A-Z\s]{3,20}?)\s+([A-Z]{3})\s+([\d\.]+\s*MHZ)", l)
        if m:
            name = m.group(1).strip()
            ident = m.group(2)
            freq_raw = m.group(3)
            lat_m = re.search(r"(\d{6}(?:\.\d+)?N)", l)
            lon_m = None
            for j in range(i + 1, min(len(lines), i + 3)):
                lo = re.search(r"(\d{7}(?:\.\d+)?W)", lines[j])
                if lo:
                    lon_m = lo
                    break
            if lat_m and lon_m:
                c = coord(f"{lat_m.group(1)} {lon_m.group(1)}")
                t_str = "VOR/DME"
                for j in range(i + 1, min(len(lines), i + 3)):
                    if "VOR" in lines[j]:
                        t_str = "VOR/DME" if "DME" in lines[j] else "VOR"
                f_val = float(re.search(r"[\d\.]+", freq_raw).group(0))
                navs.append({
                    "ident": ident, "type": t_str, "name": name,
                    "frequency": f_val, "frequency_unit": "MHZ", "raw_frequency": freq_raw,
                    "lat": c[0], "lon": c[1], "raw_coord": c[2]
                })
    return navs


def parse_dr_domestic_aerodromes(txt):
    sections = re.split(r"\n(?=\s*AD\s+2\.2\.\d+)", txt)
    ads = []
    for s in sections[1:]:
        header = re.search(r"AD\s+2\.2\.\d+\s+([^\(/]+)(?:/|\()([A-Z]{4})", s)
        if not header:
            continue
        name = header.group(1).strip()
        icao = header.group(2)
        c_m = re.search(r"(\d{6}(?:\.\d+)?N)\s*(\d{7}(?:\.\d+)?W)", s)
        if not c_m:
            continue
        c = coord(f"{c_m.group(1)} {c_m.group(2)}")
        elev_m = re.search(r"Elevaci[oó]n[^\n]*\n\s*[\d\.]+\s*\((\d+)\)", s, re.I)
        elev = int(elev_m.group(1)) if elev_m else None
        rwy_m = re.search(r"Orientaci[oó]n[^\n]*\n\s*(\d{2}/\d{2})\s*\(([\d\s]+)\s*X\s*(\d+)\s*\)", s, re.I)
        surf_m = re.search(r"Superficie[^\n]*\n\s*([A-Z/]+)", s, re.I)
        surf = surf_m.group(1).split("/")[0].strip() if surf_m else "ASPH"
        rwys = []
        if rwy_m:
            pair = rwy_m.group(1).replace("/", "-")
            length = float(rwy_m.group(2).replace(" ", ""))
            width = float(rwy_m.group(3))
            d1, d2 = pair.split("-")
            rwys.append({
                "pair": pair, "length": length, "width": width,
                "surface": "ASPH" if "ASFAL" in surf or "ASPH" in surf else surf,
                "ends": [
                    {"designator": d1, "bearing": int(d1) * 10.0, "surface": surf},
                    {"designator": d2, "bearing": int(d2) * 10.0, "surface": surf}
                ]
            })
        ads.append({
            "icao": icao, "name": name, "lat": c[0], "lon": c[1], "raw_coord": c[2],
            "elevation_ft": elev, "runways": rwys
        })
    return ads


def scrape(log):
    col = Collection(SOURCE, EFF, AMDT, BASE)

    # 1. ENR 4.4 Waypoints
    u_44 = urljoin(BASE, "/Datos/2ENR/enr_4-4.pdf")
    col.documents += 1
    wpts = parse_dr_waypoints(pdf_bytes_text(fetch(u_44), "enr_4-4.pdf"))
    for w in wpts:
        col.add_waypoint(w, "ENR 4.4", u_44)
    log(f"  ENR 4.4: {len(wpts)} waypoints")

    # 2. ENR 4.1 Navaids
    u_41 = urljoin(BASE, "/Datos/2ENR/enr_4-1.pdf")
    col.documents += 1
    navs = parse_dr_navaids(pdf_bytes_text(fetch(u_41), "enr_4-1.pdf"))
    for n in navs:
        col.add_navaid(n, "ENR 4.1", u_41)
    log(f"  ENR 4.1: {len(navs)} navaids")

    # 3. ENR 3 Routes
    routes_total = 0
    for r_file in ["enr_3-1.pdf", "enr_3-2.pdf", "enr_3-3.pdf"]:
        r_url = urljoin(BASE, f"/Datos/2ENR/{r_file}")
        col.documents += 1
        txt = pdf_bytes_text(fetch(r_url), r_file)
        routes = parse_routes(txt)
        for r in routes:
            col.add_route(r, "ENR 3", r_url, lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if "3-2" in r_file or "3-3" in r_file else None)
        routes_total += len(routes)
    log(f"  ENR 3: {routes_total} routes")

    # 4. AD 2 International Aerodromes
    for icao in INTL_ADS:
        p1 = urljoin(BASE, f"/Datos/1AD/{icao}/{icao.lower()}_ad_2-1_2-3.pdf")
        p2 = urljoin(BASE, f"/Datos/1AD/{icao}/{icao.lower()}_ad_2-12_2-13.pdf")
        try:
            t1 = pdf_bytes_text(fetch(p1), f"{icao}_ad1.pdf")
            t2 = pdf_bytes_text(fetch(p2), f"{icao}_ad2.pdf")
            col.documents += 2
            ad = parse_aerodrome(t1 + "\n" + t2, icao)
            if ad:
                col.add_aerodrome(ad, "AD 2", p1)
            else:
                col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2", "ARP not found")
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))

    # 5. AD 2 Domestic Aerodromes
    u_dom = urljoin(BASE, "/Datos/1AD/AD/ad_2-1.pdf")
    col.documents += 1
    dom_txt = pdf_bytes_text(fetch(u_dom), "ad_2-1.pdf")
    dom_ads = parse_dr_domestic_aerodromes(dom_txt)
    for ad in dom_ads:
        col.add_aerodrome(ad, "AD 2", u_dom)
    log(f"  AD 2: {len(INTL_ADS)} intl + {len(dom_ads)} domestic aerodromes")

    return col

