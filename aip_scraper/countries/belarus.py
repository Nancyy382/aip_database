"""Belarus - BELAERONAVIGATSIA eAIP (http://www.ban.by/ru/sbornik-aip/amdt).

The amendments page links the issue in force ("/AIP/Belarus261001/html/index.html",
labelled "eAIP EFFECTIVE DATE 2026-10-01"). The HTML pages only list charts; the
text sections are PDFs in "../pdf/" ("UM_ENR_4_4_en.pdf", "UM_AD_2_UMMS_en.pdf").
ENR 4.1/4.4 print the latitude on the line above the name and the longitude below it.
"""
import re
from urllib.parse import urljoin

from ..common import LAT, LON, fetch_text, lat_of, lon_of, pdf_text
from ..features import Collection
from ..parsers import parse_aerodrome, point_key

PAGE = "https://www.ban.by/ru/sbornik-aip/amdt"
SOURCE = "eAIP Republic of Belarus (BELAERONAVIGATSIA)"
NAV_TYPE = re.compile(r"\b(VOR/DME|VOR|NDB|DME)\b")


def near(lines, i, pattern, offsets):
    """First match of `pattern` on lines i+offset."""
    for o in offsets:
        if 0 <= i + o < len(lines):
            m = pattern.search(lines[i + o])
            if m:
                return m
    return None


def parse_waypoints(text):
    lines = text.splitlines()
    out = []
    for i, l in enumerate(lines):
        m = re.match(r"\s*([A-Z]{5})\s", l)
        la, lo = near(lines, i, LAT, (0, -1)), near(lines, i, LON, (0, 1))
        if m and la and lo:
            out.append({"ident": m.group(1), "lat": lat_of(la), "lon": lon_of(lo),
                        "raw_coord": f"{la.group(0)} {lo.group(0)}"})
    return out


def parse_navaids(text):
    """Ident line: "<type?>  BRT   H24   500 FT"; FREQ + lat above, CH + lon below;
    name (sometimes two lines) and type in the first column around it."""
    lines = text.splitlines()
    out, prev = [], -3
    for i, l in enumerate(lines):
        m = re.match(r"(.{0,16}?)\s+([A-Z]{3})\s{10,}H24\b", l)
        la, lo = near(lines, i, LAT, (-1,)), near(lines, i, LON, (1,))
        if not (m and la and lo):
            continue
        first = " ".join(lines[j][:16] for j in range(max(prev + 2, i - 3), i + 3))
        prev = i
        t = NAV_TYPE.search(first)
        name = " ".join(w for w in re.findall(r"[A-Z][A-Z0-9-]+", NAV_TYPE.sub(" ", first)) if w != "CH")
        f = re.search(r"(\d{3}\.\d+)\s*MHZ", lines[i - 1])
        out.append({"ident": m.group(2), "type": t.group(1) if t else None, "name": name or None,
                    "frequency": float(f.group(1)) if f else None, "frequency_unit": "MHZ" if f else None,
                    "raw_frequency": f.group(0) if f else None,
                    "lat": lat_of(la), "lon": lon_of(lo), "raw_coord": f"{la.group(0)} {lo.group(0)}"})
    return out


def parse_routes(text):
    """"L23" alone at the line start opens a route; points are "C LOVIK  520500N 0310054E"
    (C/R = compulsory/on request); navaids put their name above and "(GOL)" below."""
    lines = text.splitlines()
    routes, cur = [], None
    for i, l in enumerate(lines):
        d = re.match(r"([A-Z]{1,2}\d{1,3})(?:\s|$)", l)
        if d:
            cur = {"designator": d.group(1), "points": []}
            routes.append(cur)
            continue
        p = re.match(r"\s*[CR]\s+(\S.*?)\s+(\d{6}[NS])\s+(\d{7}[EW])", l)
        if cur is None or not p:
            continue
        name = p.group(1)
        if NAV_TYPE.fullmatch(name):
            ident = re.match(r"\s*\(([A-Z]{3})\)", lines[i + 1])
            name = f"{lines[i - 1].strip()} {name}" + (f" ({ident.group(1)})" if ident else "")
        la, lo = LAT.search(p.group(2)), LON.search(p.group(3))
        cur["points"].append({"name": name, "lat": lat_of(la), "lon": lon_of(lo),
                              "raw_coord": f"{p.group(2)} {p.group(3)}"})
    return [r for r in routes if len(r["points"]) >= 2]


def scrape(log):
    page = fetch_text(PAGE)
    href = re.search(r'href="([^"]*/AIP/Belarus\d+/)html/index\.html"', page).group(1)
    eff = re.search(r"eAIP EFFECTIVE DATE\s*(\d{4}-\d{2}-\d{2})", re.sub(r"<[^>]+>", " ", page))
    eff = eff.group(1) if eff else "unknown"
    base = urljoin(PAGE, href)
    menu = fetch_text(base + "html/eAIP/UM-menu-en-GB.html")
    pdfs = sorted(set(re.findall(r"pdf/(UM_[A-Z0-9_]+_en\.pdf)", menu)))
    col = Collection(SOURCE, eff, f"eAIP effective {eff}", base + "html/index.html")
    pdf = lambda name: base + "pdf/" + name

    col.documents += 2
    for w in parse_waypoints(pdf_text(pdf("UM_ENR_4_4_en.pdf"))):
        col.add_waypoint(w, "ENR 4.4", pdf("UM_ENR_4_4_en.pdf"))
    for n in parse_navaids(pdf_text(pdf("UM_ENR_4_1_en.pdf"))):
        col.add_navaid(n, "ENR 4.1", pdf("UM_ENR_4_1_en.pdf"))

    for name in (n for n in pdfs if re.fullmatch(r"UM_ENR_3_[1-3]_en\.pdf", n)):
        sec = f"ENR 3.{name[9]}"
        col.documents += 1
        for r in parse_routes(pdf_text(pdf(name))):
            col.add_route(r, sec, pdf(name), lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if sec == "ENR 3.3" else None)

    ads = [(re.search(r"AD_2_([A-Z]{4})", n).group(1), pdf(n)) for n in pdfs if re.fullmatch(r"UM_AD_2_[A-Z]{4}_en\.pdf", n)]
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, url in ads:
        col.documents += 1
        text = pdf_text(url)
        a = parse_aerodrome(text, icao=icao)
        if not a:
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
            continue
        a["icao"] = icao
        if a.get("elevation_ft") is None:  # "Elevation/reference temperature   681 FT/25.9° C"
            e = re.search(r"Elevation/reference temperature\s+(\d+)\s*FT", text)
            a["elevation_ft"], a["raw_elevation"] = (float(e.group(1)), e.group(0)) if e else (None, None)
        col.add_aerodrome(a, "AD 2", url)
    return col
