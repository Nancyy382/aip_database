"""Venezuela - INAC eAIP (https://www.inac.gob.ve/eaip/history-en-GB.html).

Eurocontrol-style HTML eAIP. The history page lists the issues; the newest one
whose effective date has passed is used. ENR 3 is one page per route
("SV-ENR 3.1A300-en-GB.html"), AD 2 one page per aerodrome ("SV-AD2.1SVMI-en-GB.html").
The server omits its intermediate certificate (see common.SSL_CONTEXT).
"""
import re
from datetime import date, datetime

from ..common import clean, fetch_text
from ..eaip_html import coord, parse_ad2, rows
from ..features import Collection
from ..parsers import point_key

BASE = "https://www.inac.gob.ve/eaip/"
SOURCE = "eAIP Venezuela (INAC)"
NAV_TYPES = r"(D?VOR/DME|D?VOR|DME|NDB|TACAN|VORTAC)"


def current_issue():
    page = fetch_text(BASE + "history-body-en-GB.html")
    issues = []
    for folder, label in re.findall(r"href='(\d{4}-\d{2}-\d{2})/html/index-en-GB\.html'[^>]*>([^<]*AMDT[^<]*)<", page):
        issues.append((datetime.strptime(folder, "%Y-%m-%d").date(), clean(label)))
    effective = [i for i in issues if i[0] <= date.today()]
    return max(effective or issues)


def scrape(log):
    issue, label = current_issue()
    eaip = f"{BASE}{issue.isoformat()}/html/eAIP/"
    col = Collection(SOURCE, issue.isoformat(), label, f"{BASE}{issue.isoformat()}/html/index-en-GB.html")
    page = lambda name: fetch_text(f"{eaip}{name}-en-GB.html")
    menu = fetch_text(eaip + "Menu-en-GB.html")

    # ENR 4.4: designator | lat | lon | ATS routes
    col.documents += 1
    for r in rows(page("SV-ENR 4.4")):
        c = coord(" ".join(r[1:3])) if len(r) >= 3 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]):
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                              "usage": r[3] if len(r) > 3 else None}, "ENR 4.4", f"{eaip}SV-ENR 4.4-en-GB.html")

    # ENR 4.1: "VOR/DME ACARIGUA (11°W)" | ID | FREQ (CH) | HR | COORD | ...
    col.documents += 1
    for r in rows(page("SV-ENR 4.1")):
        c = coord(r[4]) if len(r) > 4 else None
        t = re.match(NAV_TYPES + r"\s+(.*)", r[0]) if r else None
        if not (c and t and re.fullmatch(r"[A-Z]{2,4}", r[1])):
            continue
        f = re.search(r"(\d+(?:\.\d+)?)\s*(MHZ|KHZ)", r[2], re.I)
        col.add_navaid({"ident": r[1], "type": t.group(1),
                        "name": clean(re.sub(r"\(\s*\d+\s*°\s*[EW]\s*\)", "", t.group(2))),
                        "frequency": float(f.group(1)) if f else None,
                        "frequency_unit": f.group(2).upper() if f else None, "raw_frequency": r[2],
                        "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", f"{eaip}SV-ENR 4.1-en-GB.html")

    # ENR 3: one page per route; point rows are "symbol | NAME coord | ..."
    route_pages = sorted(set(re.findall(r"SV-ENR 3\.\d[A-Z0-9]+(?=-en-GB\.html)", menu)))
    log(f"  ENR 3: {len(route_pages)} route pages")
    for name in route_pages:
        col.documents += 1
        sec = re.match(r"SV-(ENR 3\.\d)", name).group(1)
        rs = rows(page(name))
        desig = next((c for r in rs for c in r if re.fullmatch(r"U?[A-Z]{1,2}\d{1,4}[A-Z]?", c)), name.split(sec)[1])
        pts = []
        for r in rs:
            cell = next((c for c in r if coord(c)), None)
            if cell:
                c = coord(cell)
                pts.append({"name": clean(cell[: cell.find(c[2].split(" ")[0][:4])]) or None,
                            "lat": c[0], "lon": c[1], "raw_coord": c[2]})
        if len(pts) >= 2:
            col.add_route({"designator": desig, "points": pts}, sec, f"{eaip}{name}-en-GB.html",
                          lambda p: point_key(p["name"]), nav_spec="RNAV" if sec != "ENR 3.1" else None)

    icaos = sorted(set(re.findall(r"SV-AD2\.1(SV[A-Z]{2})-en-GB\.html", menu)))
    log(f"  AD 2: {len(icaos)} aerodromes")
    for icao in icaos:
        col.documents += 1
        url = f"{eaip}SV-AD2.1{icao}-en-GB.html"
        try:
            rec = parse_ad2(page(f"SV-AD2.1{icao}"), icao)
        except Exception as e:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))
            continue
        if rec:
            col.add_aerodrome(rec, "AD 2", url)
        else:
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
    return col
