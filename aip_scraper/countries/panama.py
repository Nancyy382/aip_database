"""Panama - AAC AIS (https://www.aeronautica.gob.pa/ais-aip/).

The AIS page links one PDF per AIP part ("ENR 3 RUTAS ATS", "ENR 4 RADIOAYUDAS...")
and one per international aerodrome ("AD 2.1-MPTO").
"""
import html
import re
from datetime import datetime

from ..common import clean, fetch_text, pdf_text
from ..features import Collection
from ..parsers import (parse_aerodrome, parse_navaids_ident_first, parse_routes, parse_waypoints,
                       point_key, section)

PAGE = "https://www.aeronautica.gob.pa/ais-aip/"
SOURCE = "AIP Panamá (AAC)"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def documents():
    page = fetch_text(PAGE)
    docs = {}
    for href, text in re.findall(r'<a\b[^>]*href="([^"]*AIP PDF COMPLETO[^"]+\.pdf)"[^>]*>(.*?)</a>', page, re.S):
        title = clean(html.unescape(re.sub(r"<[^>]+>", " ", text)))
        docs[title] = href if href.startswith("http") else "https://www.aeronautica.gob.pa/ais-aip/" + href.lstrip("/")
    return docs


def header_dates(text):
    """Page headers carry the page's effective date: '30 DEC 25'."""
    out = []
    for d, m, y in re.findall(r"\b(\d{2}) (JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC) (\d{2})\b", text):
        out.append(datetime(2000 + int(y), MONTHS[m], int(d)).date().isoformat())
    return out


def scrape(log):
    docs = documents()
    find = lambda prefix: next((u for t, u in docs.items() if t.startswith(prefix)), None)
    enr3_url, enr4_url = find("ENR 3"), find("ENR 4")
    enr3, enr4 = pdf_text(enr3_url), pdf_text(enr4_url)
    amdts = [t for t in docs if t.startswith("AMDT AIRAC")]
    col = Collection(SOURCE, max(header_dates(enr3 + enr4)), amdts[-1] if amdts else "unknown", PAGE)
    col.documents += 2

    for w in parse_waypoints(section(enr4, r"ENR 4\.4", r"ENR 4\.5")):
        col.add_waypoint(w, "ENR 4.4", enr4_url)
    for n in parse_navaids_ident_first(section(enr4, r"ENR 4\.1", r"ENR 4\.2")):
        col.add_navaid(n, "ENR 4.1", enr4_url)
    for r in parse_routes(enr3):
        col.add_route(r, "ENR 3", enr3_url, lambda p: point_key(p["name"]),
                      nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)

    ad = {re.search(r"([A-Z]{4})$", t).group(1): u for t, u in docs.items() if re.match(r"AD 2\.\d+-[A-Z]{4}$", t)}
    log(f"  AD 2: {len(ad)} aerodromes")
    for icao, url in ad.items():
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
