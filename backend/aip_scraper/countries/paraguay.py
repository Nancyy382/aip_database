"""Paraguay - DINAC AIS (https://www.dinac.gov.py/v3/index.php/ais/aip-paraguay).

The whole AIP is one RAR archive ("AMDT_AIRAC_02_2026.rar") with a PDF per
part (Enr 3, Enr 4) and per aerodrome (AD 2.1_SGAS ...). ENR 4 has no list of
significant points, so waypoints come from the ENR 3 route tables.
"""
import re
from datetime import datetime

from ..common import archive_member, archive_members, fetch_text, pdf_bytes_text
from ..features import Collection
from ..parsers import parse_aerodrome, parse_navaids, parse_routes, point_key, section

PAGE = "https://www.dinac.gov.py/v3/index.php/ais/aip-paraguay"
SOURCE = "AIP Paraguay (DINAC)"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def archive_url():
    m = re.search(r'href="([^"]+\.rar)"', fetch_text(PAGE), re.I)
    if not m:
        raise RuntimeError("AIP archive link not found on " + PAGE)
    return m.group(1) if m.group(1).startswith("http") else "https://www.dinac.gov.py" + m.group(1)


def scrape(log):
    url = archive_url()
    members = archive_members(url)
    find = lambda pattern: next((m for m in members if re.search(pattern, m, re.I)), None)
    read = lambda m: pdf_bytes_text(archive_member(url, m), m)
    enr3, enr4 = read(find(r"/Enr 3\.pdf")), read(find(r"/Enr 4\.pdf"))
    dates = [datetime(int(y), MONTHS[m], int(d)).date().isoformat()
             for d, m, y in re.findall(r"\b(\d{2}) (JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC) (\d{4})\b", enr3 + enr4)]
    amdt = re.search(r"AMDT_AIRAC_(\d+)_(\d{4})", url)
    col = Collection(SOURCE, max(dates), f"AMDT AIRAC {amdt.group(1)}/{amdt.group(2)}" if amdt else "unknown", PAGE)
    col.documents += 2
    src = lambda m: f"{url}#{m}"

    for n in parse_navaids(section(enr4, r"ENR 4\.\s?1", r"ENR 4\.\s?2") or enr4):
        n["name"] = re.sub(r"^\d+\s+|\s\d+\s", " ", n["name"]).strip()  # drop the "N° ORDEN" column
        col.add_navaid(n, "ENR 4.1", src(find(r"/Enr 4\.pdf")))
    routes = parse_routes(enr3)
    pk = lambda p: point_key(p["name"])
    col.add_waypoints_from_routes(routes, "ENR 3", src(find(r"/Enr 3\.pdf")), pk)
    for r in routes:
        col.add_route(r, "ENR 3", src(find(r"/Enr 3\.pdf")), pk,
                      nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)

    ads = [(re.search(r"_(SG[A-Z]{2})\.", m).group(1), m) for m in members if re.search(r"/AD 2\.\d+_SG[A-Z]{2}\.", m)]
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, m in ads:
        col.documents += 1
        a = parse_aerodrome(read(m), icao=icao)
        if a:
            a["icao"] = icao
            col.add_aerodrome(a, "AD 2", src(m))
    return col
