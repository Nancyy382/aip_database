"""Finland - Fintraffic eAIP (https://www.ais.fi/).

eAIP is published under /eaip/currently_effective/eAIP/.
Cover page /eaip/currently_effective/EF-Cover Page-en-GB.html gives effective date
and amendment. Menu is at /eaip/currently_effective/eAIP/menu.html.
ENR 4.4 waypoints and individual ENR 3 routes are parsed from HTML;
ENR 4.1 navaids are read from EF-ENR 4.1-fi-FI.html (complete bilingual table);
AD 2 aerodrome pages (EF-AD 2 <ICAO> ... 1-en-GB.html) contain full aerodrome details.
"""
from datetime import datetime
import re

from ..common import fetch_text
from ..eaip_html import coord, parse_ad2, rows
from ..features import Collection
from ..parsers import point_key

BASE = "https://www.ais.fi/eaip/currently_effective/eAIP/"
COVER_URL = "https://www.ais.fi/eaip/currently_effective/EF-Cover Page-en-GB.html"
SOURCE = "eAIP Finland (Fintraffic)"
NAV_TYPE = re.compile(r"\b(VOR/TACAN|D?VOR/DME|VORTAC|D?VOR|NDB/DME|NDB|DME|TACAN)\b")


def parse_finland_route(page_html):
    rs = rows(page_html)
    desig = None
    points = []
    for i, r in enumerate(rs):
        if not r:
            continue
        if len(r) >= 2 and re.fullmatch(r"[A-Z]{1,2}\d{1,4}[A-Z]?", r[0].strip()):
            desig = r[0].strip()
            continue
        if desig and len(r) >= 2:
            name = r[1].strip()
            if re.fullmatch(r"[A-Z0-9]{2,5}", name):
                lat_str = rs[i + 1][1].strip() if i + 1 < len(rs) and len(rs[i + 1]) >= 2 else ""
                lon_str = rs[i + 2][1].strip() if i + 2 < len(rs) and len(rs[i + 2]) >= 2 else ""
                c = coord(f"{lat_str} {lon_str}")
                if c:
                    points.append({"name": name, "lat": c[0], "lon": c[1], "raw_coord": c[2]})
    if desig and len(points) >= 2:
        return {"designator": desig, "points": points}
    return None


def scrape(log):
    cover = fetch_text(COVER_URL)
    m_eff = re.search(r"Effective date\s*:\s*([0-9]{2}\s+[A-Z]{3}\s+[0-9]{4})", cover)
    eff_date = datetime.strptime(m_eff.group(1), "%d %b %Y").date().isoformat()
    m_amdt = re.search(r"AIP AIRAC AMDT\s*([0-9]{2}\s+[A-Z]{3}\s+[0-9]{4})\s*\(([^)]+)\)", cover)
    amdt = f"AIRAC AMDT {m_amdt.group(2)}" if m_amdt else f"AIRAC {eff_date}"

    col = Collection(SOURCE, eff_date, amdt, BASE + "menu.html")

    # ENR 4.4 waypoints
    w_url = BASE + "EF-ENR 4.4-en-GB.html"
    col.documents += 1
    for r in rows(fetch_text(w_url)):
        c = coord(" ".join(r[1:3])) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]):
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                              "usage": r[2] if len(r) > 2 else None}, "ENR 4.4", w_url)

    # ENR 4.1 navaids (fi-FI has the complete bilingual table)
    nav_url = BASE + "EF-ENR 4.1-fi-FI.html"
    col.documents += 1
    for r in rows(fetch_text(nav_url)):
        ci = next((i for i, x in enumerate(r) if coord(x)), None)
        t = NAV_TYPE.search(r[0]) if r else None
        ident = next((x for x in r[1:ci] if re.fullmatch(r"[A-Z]{2,4}", x)), None) if ci else None
        if not (t and ident):
            continue
        c = coord(r[ci])
        f = re.search(r"(\d{3,4}(?:\.\d+)?)\s*(MHZ|KHZ)", " ".join(r[1:ci]), re.I)
        col.add_navaid({"ident": ident, "type": t.group(1), "name": r[0][:t.start()].strip() or None,
                        "frequency": float(f.group(1)) if f else None,
                        "frequency_unit": f.group(2).upper() if f else None,
                        "raw_frequency": f.group(0) if f else None,
                        "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", nav_url)

    # Menu links
    menu_txt = fetch_text(BASE + "menu.html")
    en_links = set(re.findall(r'href=[\"\']([^\"\'#]+en-GB\.html)', menu_txt))

    # ENR 3 routes
    r_links = sorted([l for l in en_links if re.search(r"EF-ENR\s*3\.[1-3]\s+[A-Z0-9]+", l)])
    for rel in r_links:
        col.documents += 1
        url = BASE + rel
        r = parse_finland_route(fetch_text(url))
        if r:
            col.add_route(r, "ENR 3.2", url, lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)

    # AD 2 aerodromes
    ad2_links = {}
    for l in sorted(en_links):
        m = re.search(r"EF-AD\s+2\s+([A-Z]{4})\b.*?1-en-GB\.html$", l)
        if m:
            ad2_links[m.group(1)] = l

    log(f"  eAIP EF: {len(ad2_links)} aerodromes")
    for icao, rel in sorted(ad2_links.items()):
        col.documents += 1
        url = BASE + rel
        try:
            page = fetch_text(url)
            ad = parse_ad2(page, icao)
            if ad:
                col.add_aerodrome(ad, "AD 2", url)
            else:
                col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
        except Exception as e:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))

    return col

