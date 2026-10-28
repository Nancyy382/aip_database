"""Cuba AIP scraper."""
from urllib.parse import urljoin
from aip_scraper.common import fetch, pdf_bytes_text
from aip_scraper.eaip_html import coord
from aip_scraper.features import Collection
from aip_scraper.parsers import parse_aerodrome, parse_routes, parse_waypoints, point_key
import re

BASE_PAGE = "https://aismet.avianet.cu/html/aip.html"
BASE_URL = "https://aismet.avianet.cu/assets/data/pdf/AIP/"
SOURCE = "AIP Cuba (ECNA)"
AMDT = "AIP AMDT 04/26"
EFF = "2026-09-22"

def parse_cuba_navaids(txt):
    lines = txt.split('\n')
    navs = []
    for i, l in enumerate(lines):
        m = re.match(r'^\s*([A-Z\s]{3,18})\s+([A-Z]{3,4})\s+([\d\.]+\s*MHZ|\(CH\s+\w+\))\s+([A-Z0-9]+)\s+(\d{6}(?:\.\d+)?N)', l)
        if m:
            name = m.group(1).strip()
            ident = m.group(2)
            raw_freq = m.group(3)
            lat_str = m.group(5)
            lon_str = None
            type_str = 'VOR/DME'
            extra_name = []
            for j in range(i+1, min(len(lines), i+4)):
                lon_m = re.search(r'(\d{7}(?:\.\d+)?W)', lines[j])
                if lon_m and not lon_str:
                    lon_str = lon_m.group(1)
                t_m = re.search(r'\b(VOR/DME|VOR|DME|NDB)\b', lines[j])
                if t_m:
                    type_str = t_m.group(1)
                sub_name = lines[j][:18].strip()
                if sub_name and not t_m and not sub_name.startswith('('):
                    extra_name.append(sub_name)
            if lon_str:
                full_name = f'{name} {" ".join(extra_name)}'.strip()
                c = coord(f'{lat_str} {lon_str}')
                f_m = re.search(r'([\d\.]+)\s*MHZ', raw_freq)
                f_val = float(f_m.group(1)) if f_m else None
                navs.append({
                    'ident': ident, 'type': type_str, 'name': full_name,
                    'frequency': f_val, 'frequency_unit': 'MHZ' if f_val else None,
                    'raw_frequency': raw_freq, 'lat': c[0], 'lon': c[1], 'raw_coord': c[2]
                })
    return navs

def scrape(log):
    col = Collection(SOURCE, EFF, AMDT, BASE_PAGE)

    # 1. ENR 4.4 Waypoints
    url_44 = urljoin(BASE_URL, "ENR_4.4.pdf")
    col.documents += 1
    wpts = parse_waypoints(pdf_bytes_text(fetch(url_44), "ENR_4.4.pdf"))
    for w in wpts:
        col.add_waypoint(w, "ENR 4.4", url_44)
    log(f"  ENR 4.4: {len(wpts)} waypoints")

    # 2. ENR 4.1 Navaids
    url_41 = urljoin(BASE_URL, "ENR_4.1.pdf")
    col.documents += 1
    navs = parse_cuba_navaids(pdf_bytes_text(fetch(url_41), "ENR_4.1.pdf"))
    for n in navs:
        col.add_navaid(n, "ENR 4.1", url_41)
    log(f"  ENR 4.1: {len(navs)} navaids")

    # 3. ENR 3 Routes
    routes_total = 0
    for sec_file in ["ENR_3.1.pdf", "ENR_3.2.pdf"]:
        sec_url = urljoin(BASE_URL, sec_file)
        col.documents += 1
        sec_name = "ENR 3.1" if "3.1" in sec_file else "ENR 3.2"
        routes = parse_routes(pdf_bytes_text(fetch(sec_url), sec_file))
        for r in routes:
            col.add_route(r, sec_name, sec_url, lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if "3.2" in sec_file else None)
        routes_total += len(routes)
    log(f"  ENR 3: {routes_total} routes")

    # 4. AD 2 Aerodromes
    ad_files = [
        ("MUBA", "MUBA.pdf"), ("MUBR", "MUBR.pdf"), ("MUBY", "MUBY.pdf"),
        ("MUCC", "MUCCAD_2.pdf"), ("MUCF", "MUCFAD_2.pdf"), ("MUCL", "MUCLAD_2.pdf"),
        ("MUCM", "MUCM_AD_2.pdf"), ("MUCU", "MUCUAD_2.pdf"), ("MUGT", "MUGT.pdf"),
        ("MUHA", "MUHAAD_2.pdf"), ("MUHG", "MUHGAD_2.pdf"), ("MUMO", "MUMO.pdf"),
        ("MUMZ", "MUMZAD_2.pdf"), ("MUNG", "MUNG.pdf"), ("MUPB", "MUPB.pdf"),
        ("MUSC", "MUSC.pdf"), ("MUTD", "MUTD.pdf"), ("MUVR", "MUVR.pdf"),
        ("MUVT", "MUVT.pdf")
    ]
    log(f"  AD 2: {len(ad_files)} aerodromes")
    for icao, filename in ad_files:
        ad_url = urljoin(BASE_URL, filename)
        col.documents += 1
        txt = pdf_bytes_text(fetch(ad_url), filename)
        rec = parse_aerodrome(txt, icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", ad_url)
        else:
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", f"No ARP found in {filename}")

    return col

