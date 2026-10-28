"""Argentina - ANAC AIS (https://ais.anac.gob.ar/aip).

The AIP page loads each part (gen/enr/ad) with jQuery from /aip/<part>; every
row is a section title, its amendment ("01/26 11-Jun-26") and a
/descarga/aip-<id> PDF link.
"""
import html
import re
from datetime import datetime

from ..common import clean, fetch_text, pdf_text
from ..features import Collection
from ..parsers import parse_aerodrome, parse_navaids, parse_routes, parse_waypoints, point_key

BASE = "https://ais.anac.gob.ar"
XHR = {"X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/aip"}
SOURCE = "AIP Argentina (ANAC)"


def index(part):
    page = fetch_text(f"{BASE}/aip/{part}", headers=XHR)
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", page, re.S):
        href = re.search(r'href="(/descarga/[^"]+)"', tr)
        cells = [clean(html.unescape(re.sub(r"<[^>]+>", " ", c))) for c in re.findall(r"<td.*?</td>", tr, re.S)]
        if href and cells:
            amdt = re.search(r"(\d{2}/\d{2})\s+(\d{2}-[A-Za-z]{3}-\d{2})", " ".join(cells[1:]))
            date = datetime.strptime(amdt.group(2), "%d-%b-%y").date().isoformat() if amdt else None
            rows.append({"title": cells[0], "url": BASE + href.group(1),
                         "amdt": amdt.group(1) if amdt else None, "date": date})
    return rows


def scrape(log):
    enr, ad = index("enr"), index("ad")
    latest = max((r for r in enr + ad if r["date"]), key=lambda r: r["date"])
    col = Collection(SOURCE, latest["date"], f"AIRAC AMDT {latest['amdt']}", BASE + "/aip")

    def run(row, parse):
        col.documents += 1
        try:
            return parse(pdf_text(row["url"]))
        except Exception as e:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", row["title"], row["title"].split(" ")[0], str(e))
            return None

    routes = []
    for row in enr:
        sec = row["title"].split(" ")[0].replace("ENR-", "ENR ")
        if sec == "ENR 4.4":
            for w in run(row, parse_waypoints) or []:
                col.add_waypoint(w, sec, row["url"])
        elif sec == "ENR 4.1":
            for n in run(row, parse_navaids) or []:
                col.add_navaid(n, sec, row["url"])
        elif sec in ("ENR 3.1", "ENR 3.2", "ENR 3.3"):
            routes += [(r, sec, row) for r in run(row, parse_routes) or []]
    for r, sec, row in routes:
        r["route_class"] = "lower/upper conventional" if sec == "ENR 3.1" else "RNAV" if sec == "ENR 3.2" else "other"
        col.add_route(r, sec, row["url"], lambda p: point_key(p["name"]),
                      nav_spec="RNAV 5" if sec == "ENR 3.2" else None)

    ad_rows = [r for r in ad if re.match(r"^[A-Z]{4}-AD-2\.0 ", r["title"])]
    log(f"  AD 2: {len(ad_rows)} aerodromes")
    for row in ad_rows:
        m = re.search(r"Datos del AD (.+)$", row["title"])
        a = run(row, lambda t: parse_aerodrome(t, icao=row["title"][:4], name=m and m.group(1)))
        if a:
            col.add_aerodrome(a, "AD 2", row["url"])
    return col
