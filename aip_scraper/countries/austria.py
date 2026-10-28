"""Austria - Austro Control AIP (https://eaip.austrocontrol.at/).

The start page lists issues with "valid from / valid until" dates and a folder per
issue ("./lo/261002/index.htm"); the one valid today is used. Each issue publishes
one PDF per ENR section ("PART_2/LO_ENR_4_4_en.pdf", listed on enr_3.htm / enr_4.htm)
and one per aerodrome ("PART_3/AD_2/PRI/AD_2_LOWW/LO_AD_2_LOWW_en.pdf", on ad_2.htm).
"""
import re
from datetime import date, datetime

from ..common import fetch_text, pdf_text
from ..features import Collection
from ..parsers import (parse_aerodrome, parse_navaids_ident_first, parse_routes, parse_waypoints, point_key,
                       section)

BASE = "https://eaip.austrocontrol.at/"
SOURCE = "AIP Austria (Austro Control)"


def current_issue():
    page = fetch_text(BASE)
    today = date.today()
    issues = []
    for start, end, href in re.findall(r"<TD[^>]*>(\d{2} \w{3} \d{4})</TD>\s*<TD[^>]*>([^<]+)</TD>\s*<TD[^>]*>.*?href=\"\./(lo/\d+/)index\.htm\"",
                                       page, re.S | re.I):
        start = datetime.strptime(start, "%d %b %Y").date()
        end = datetime.strptime(end, "%d %b %Y").date() if re.match(r"\d{2} \w{3} \d{4}", end) else date.max
        issues.append((start, end, href))
    return next((i for i in issues if i[0] <= today <= i[1]), max(issues))


def links(page):
    return sorted(set(re.findall(r"[\"']([^\"']+\.pdf)[\"']", fetch_text(page))))


def summary_runways(text):
    """Small aerodromes use a one-page summary without THR coordinates:
    "Kennung/designation: 03/21  Maße/dimensions: 541 x 25 M  Oberfläche/surface: Gras/grass"."""
    runways = []
    for d in re.finditer(r"designation:\s*(\d{2}[LRC]?)\s*/\s*(\d{2}[LRC]?)", text):
        after = text[d.end(): d.end() + 600]
        dim = re.search(r"dimensions:\s*(\d+)\s*x\s*(\d+)\s*M", after)
        sfc = re.search(r"surface:\s*([^\n]+?)(?:\s{2,}|$)", after, re.M)
        surface = sfc.group(1).split("/")[-1].strip().upper() if sfc else None
        runways.append({"pair": f"{d.group(1)}-{d.group(2)}",
                        "length": float(dim.group(1)) if dim else None, "width": float(dim.group(2)) if dim else None,
                        "raw_dims": dim.group(0) if dim else None,
                        "surface": {"GRASS": "GRASS", "ASPHALT": "ASPH", "CONCRETE": "CONC"}.get(surface, surface),
                        "ends": [{"designator": e, "lat": None, "lon": None} for e in (d.group(1), d.group(2))]})
    return runways


def scrape(log):
    start, _, folder = current_issue()
    base = BASE + folder
    col = Collection(SOURCE, start.isoformat(), f"AIP issue {folder.strip('/').split('/')[-1]}", base + "index.htm")

    enr4 = {re.search(r"ENR_(\d_\d)", u).group(1): base + u for u in links(base + "enr_4.htm")}
    col.documents += 2
    for w in parse_waypoints(pdf_text(enr4["4_4"])):
        col.add_waypoint(w, "ENR 4.4", enr4["4_4"])
    for n in parse_navaids_ident_first(section(pdf_text(enr4["4_1"]), r"ENR 4\.1", r"ENR 4\.2") or pdf_text(enr4["4_1"])):
        col.add_navaid(n, "ENR 4.1", enr4["4_1"])

    for u in links(base + "enr_3.htm"):
        n = re.search(r"ENR_3_([1-3])_", u)
        if not n:
            continue
        col.documents += 1
        for r in parse_routes(pdf_text(base + u)):
            col.add_route(r, f"ENR 3.{n.group(1)}", base + u, lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if n.group(1) == "2" else None)

    ads = [(re.search(r"AD_2_([A-Z]{4})_", u).group(1), base + u) for u in links(base + "ad_2.htm")
           if re.search(r"AD_2_[A-Z]{4}_en\.pdf$", u)]
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, url in ads:
        col.documents += 1
        try:
            a = parse_aerodrome(pdf_text(url), icao=icao)
        except Exception as e:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))
            continue
        if a:
            a["icao"] = icao
            if not a["runways"]:
                a["runways"] = summary_runways(pdf_text(url))
            col.add_aerodrome(a, "AD 2", url)
        else:
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
    return col
