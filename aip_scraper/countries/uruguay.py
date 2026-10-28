"""Uruguay - DINACIA AIS (http://www.dinacia.gub.uy/ais/aip-uruguay).

The AIP page is a Drupal view filtered by `field_indice_aip_target_id`; every
section (ENR 3, ENR 4, "SUAA AD 2.8 - ...") is a term id and the filtered
page links that section's current PDF.
"""
import html
import re
from datetime import datetime

from ..common import clean, fetch_text, pdf_text
from ..features import Collection
from ..parsers import (parse_aerodrome, parse_navaids_ident_first, parse_routes, parse_waypoints,
                       point_key, section)

BASE = "http://www.dinacia.gub.uy"
PAGE = BASE + "/ais/aip-uruguay"
SOURCE = "AIP Uruguay (DINACIA)"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def terms():
    """{option label: term id} from the AIP index filter (first id wins for duplicate labels)."""
    page = fetch_text(PAGE)
    out = {}
    for tid, label in re.findall(r'<option value="(\d+)"[^>]*>(.*?)</option>', page):
        out.setdefault(clean(html.unescape(label)), tid)
    return out


def pdf_for(tid):
    page = fetch_text(f"{PAGE}?field_indice_aip_target_id={tid}")
    m = re.search(r'href="([^"]+\.pdf)"', page)
    return (BASE + m.group(1) if m.group(1).startswith("/") else m.group(1)) if m else None


def scrape(log):
    t = terms()
    enr3_url = pdf_for(t["ENR 3 Rutas ATS"])
    enr4_url = pdf_for(t["ENR 4 Radioayudas y Sistemas de Navegación"])
    enr3, enr4 = pdf_text(enr3_url), pdf_text(enr4_url)
    dates = [datetime(int(y), MONTHS[m], int(d)).date().isoformat()
             for d, m, y in re.findall(r"\b(\d{2}) (JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC) (\d{4})\b", enr3 + enr4)]
    amdt = max((int(n) for n in re.findall(r"AIRAC AIP AMDT NR (\d+)", enr3 + enr4)), default=None)
    col = Collection(SOURCE, max(dates), f"AIRAC AIP AMDT NR {amdt:02d}" if amdt else "unknown", PAGE)
    col.documents += 2

    # Uruguay numbers significant points ENR 4.3 (ENR 4.4 is aeronautical lights)
    for w in parse_waypoints(section(enr4, r"ENR 4\.3", r"ENR 4\.4")):
        col.add_waypoint(w, "ENR 4.3", enr4_url)
    for n in parse_navaids_ident_first(section(enr4, r"ENR 4\.1", r"ENR 4\.2")):
        col.add_navaid(n, "ENR 4.1", enr4_url)
    # ENR 3.3+ are VFR/other routes named by towns, not ATS routes
    for r in parse_routes(section(enr3, r"ENR 3\.1", r"ENR 3\.3") or enr3):
        col.add_route(r, "ENR 3", enr3_url, lambda p: point_key(p["name"]),
                      nav_spec="RNAV 5" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)

    ads = {}
    for label, tid in t.items():
        m = re.match(r"(SU[A-Z]{2}) AD 2\.\d+", label)
        if m:
            ads.setdefault(m.group(1), tid)
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, tid in sorted(ads.items()):
        url = pdf_for(tid)
        if not url:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", "no PDF linked")
            continue
        col.documents += 1
        try:
            a = parse_aerodrome(pdf_text(url), icao=icao)
        except Exception as e:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))
            continue
        if a:
            a["icao"] = icao
            col.add_aerodrome(a, "AD 2", url)
    return col
