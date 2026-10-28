"""Ecuador - DGAC IFIS3 (https://www.ais.aviacioncivil.gob.ec/ifis3/aip/AIP).

AD 2 sections are HTML text, but the ENR tables (ENR 3 routes, ENR 4.1 navaids,
ENR 4.4 points) are only published as scanned page images, so they are read
with Tesseract OCR. OCR output is checked against Ecuador's FIR bounds, and
route points are cross-checked against the ENR 4.4 list; disagreements are
reported as issues (RULE_OCR_MISMATCH).
"""
import html
import math
import re
from datetime import date

from ..common import clean, fetch_text, ocr_image
from ..eaip_html import parse_ad2
from ..features import Collection

BASE = "https://www.ais.aviacioncivil.gob.ec"
AIP = BASE + "/ifis3/aip/"
SOURCE = "AIP Ecuador (DGAC) - ENR tables read by OCR from page images"
OCR_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/.() "
MONTHS = {m: i for i, m in enumerate(["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"], 1)}
MONTHS.update({"JAN": 1, "APR": 4, "AUG": 8, "DEC": 12})

LAT_TOKEN = re.compile(r"(?<![\d.])(\d{2})([0-5]\d)([0-5]\d(?:\.\d+)?)([NS])(?![A-Z0-9])")
LON_TOKEN = re.compile(r"(?<![\d.])(\d{3})([0-5]\d)([0-5]\d(?:\.\d+)?)\s?W(?![A-Z0-9])")
NAME = re.compile(r"\b([A-Z][A-Z0-9]{4})\b")  # AKPOT, TA330


def node(name):
    return fetch_text(AIP + name.replace(" ", "%20"))


def images(name):
    page = node(name)
    content = page[page.find("node-content"):]
    return [BASE + src for src in re.findall(r'<img src="(/ifis3/aip/download/s/[^"]+)"', content)]


def fix_ocr(text):
    """OCR reads the S of a latitude as 5 or 8: '0055468' -> '005546S' (only plausible latitudes)."""
    return re.sub(r"(?<![\d.])([01]\d)([0-5]\d)([0-5]\d)[58](?![\dA-Z])", r"\1\2\3S", text)


def dms(m, lon=False):
    d, mi, s, h = (m.group(1), m.group(2), m.group(3), "W" if lon else m.group(4))
    v = int(d) + int(mi) / 60 + float(s) / 3600
    return round(-v if h in "SW" else v, 7)


def in_fir(lat, lon):
    """Guayaquil FIR incl. Galápagos and the oceanic sector."""
    return -12 <= lat <= 8 and -125 <= lon <= -70


def current_amendment():
    page = node("amdt")
    names = sorted(set(re.findall(r"AIRAC AIP AMDT \d{2}-\d{2}", page)))
    effective = []
    for n in names:
        m = re.search(r"WEF (\d{1,2}) ([A-Z]{3}) (\d{2,4})\b", node(n))
        if m and m.group(2) in MONTHS:
            year = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
            effective.append((date(year, MONTHS[m.group(2)], int(m.group(1))), n))
    past = [e for e in effective if e[0] <= date.today()]
    return max(past or effective)


def scrape(log):
    wef, amdt = current_amendment()
    col = Collection(SOURCE, wef.isoformat(), amdt, AIP + "AIP")

    # ENR 4.4: two columns per row: NAME LAT ROUTES  NAME LAT ROUTES / next line: LON  LON
    points = {}
    for url in images("ENR 4.4"):
        col.documents += 1
        lines = [ln for ln in fix_ocr(ocr_image(url, OCR_CHARS)).splitlines() if ln.strip()]
        for i, ln in enumerate(lines[:-1]):
            heads = [(n.group(1), lat) for n in NAME.finditer(ln)
                     for lat in [LAT_TOKEN.match(ln, n.end() + 1) or LAT_TOKEN.match(ln, n.end() + 2)] if lat]
            lons = list(LON_TOKEN.finditer(lines[i + 1]))
            if not heads or not lons:
                continue
            if len(heads) == len(lons):
                pairs = list(zip(heads, lons))
            elif len(heads) == 1 and len(lons) == 2:
                # the other column's name was not read: pick this one's column by position
                (name, la), = heads
                pairs = [((name, la), lons[1] if la.start() > len(ln) * 0.45 else lons[0])]
            else:
                continue
            for (name, la), lo in pairs:
                lat, lon = dms(la), dms(lo, lon=True)
                if in_fir(lat, lon):
                    points[name] = (lat, lon)
                    col.add_waypoint({"ident": name, "lat": lat, "lon": lon,
                                      "raw_coord": f"{la.group(0)} {lo.group(0)}"}, "ENR 4.4", url)
    log(f"  ENR 4.4 (OCR): {len(points)} points")

    # ENR 4.1: "VOR/DME COV 1150 MHZ H24 002642S ..." / next line "COCA CH07X 0765944W"
    nav = re.compile(r"\b(D?VOR/DME|D?VOR|NDB|DME)\s+([A-Z]{2,3})\s+(\d{3,5})\s*(MHZ|KHZ)")
    for url in images("ENR 4.1"):
        col.documents += 1
        lines = [ln for ln in fix_ocr(ocr_image(url)).splitlines() if ln.strip()]
        for i, ln in enumerate(lines[:-1]):
            m = nav.search(ln)
            la = LAT_TOKEN.search(ln, m.end()) if m else None
            lo = LON_TOKEN.search(lines[i + 1]) if la else None
            if not lo:
                continue
            lat, lon = dms(la), dms(lo, lon=True)
            if not in_fir(lat, lon):
                continue
            digits, unit = m.group(3), m.group(4)
            freq = float(digits[:3] + "." + digits[3:]) if unit == "MHZ" and len(digits) > 3 else float(digits)
            name = clean(re.split(r"\bCH\s?\w+|\d{7}", lines[i + 1])[0])
            col.add_navaid({"ident": m.group(2), "type": m.group(1), "name": name or None,
                            "frequency": freq, "frequency_unit": unit, "raw_frequency": f"{digits} {unit}",
                            "lat": lat, "lon": lon, "raw_coord": f"{la.group(0)} {lo.group(0)}"}, "ENR 4.1", url)
    navs = {f["properties"]["naturalKey"][4:] for f in col.features.values() if f["properties"]["featureType"] == "navaid"}

    # ENR 3: one image per route (multi-page routes: A566-1, A566-2)
    routes = {}
    for sec in ("ENR 3.1", "ENR 3.2", "ENR 3.3"):
        for url in images(sec):
            col.documents += 1
            desig = re.sub(r"-\d+$", "", html.unescape(re.search(r"/download/s/([^?]+)", url).group(1)).replace("%20", " "))
            rec = routes.setdefault(desig, {"designator": desig, "points": [], "section": sec, "url": url})
            last_name = None
            for ln in fix_ocr(ocr_image(url)).splitlines():
                la, lo = LAT_TOKEN.search(ln), LON_TOKEN.search(ln)
                if la and lo and lo.start() > la.start():
                    lat, lon = dms(la), dms(lo, lon=True)
                    if in_fir(lat, lon) or (last_name and last_name in points):
                        rec["points"].append({"name": last_name, "lat": lat, "lon": lon,
                                              "raw_coord": f"{la.group(0)} {lo.group(0)}"})
                    last_name = None
                    continue
                words = [w for w in re.findall(r"\b[A-Z]{3,5}\b", ln) if w not in ("VER", "AIP", "NM", "FL", "UNL", "ACC", "FIR")]
                if words:
                    last_name = next((w for w in words if w in points or w in navs), words[-1] if len(words[-1]) == 5 else last_name)
    for r in routes.values():
        if len(r["points"]) < 2:
            continue
        for p in r["points"]:
            ref = points.get(p["name"])
            if ref and _nm(ref, (p["lat"], p["lon"])) > 2:
                col.issue("warning", "RULE_OCR_MISMATCH", f"RTE/{r['designator']}", r["section"],
                          f"{p['name']}: route table and ENR 4.4 differ by {_nm(ref, (p['lat'], p['lon'])):.1f} NM",
                          p["raw_coord"])
        col.add_route(r, r["section"], r["url"],
                      lambda p: (f"NAV/{p['name']}" if p["name"] in navs else f"WPT/{p['name']}") if p["name"] else None,
                      nav_spec="RNAV" if r["section"] == "ENR 3.3" else None)
    log(f"  ENR 3 (OCR): {len(routes)} routes")

    # AD 2: HTML text
    page = node("AD 2")
    icaos = sorted(set(re.findall(r'href="/ifis3/aip/AD%202%20(SE[A-Z]{2})"', page)))
    log(f"  AD 2: {len(icaos)} aerodromes")
    for icao in icaos:
        col.documents += 1
        rec = parse_ad2(node(f"AD 2 {icao}"), icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", f"{AIP}AD%202%20{icao}")
    return col


def _nm(a, b):
    """Great-circle distance in NM between (lat, lon) pairs."""
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 3440.065 * math.asin(math.sqrt(h))
