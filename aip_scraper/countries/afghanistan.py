"""Afghanistan - ACAA AIS (https://www.afgais.com/).

The home page links the current edition as three PDFs ("GENERAL/ENROUTE/AERODROME
EDITION nnn EFFECTIVE DATE ..."). Layout notes:
- ENR 4.1: "BAGRAM VORTAC   BGM   H24   CH74/112.7   345701N 0691617E" (type inside the name);
- ENR 3: point coordinates sit right of the usual name column;
- AD 2.12 is transposed: one row per property, one column per runway end.
"""
import html
import re
from datetime import datetime

from ..common import LATLON, clean, dms, fetch_text, pdf_text
from ..features import Collection
from ..parsers import parse_aerodrome, parse_routes, parse_waypoints, point_key, section

PAGE = "https://www.afgais.com/"
SOURCE = "AIP Afghanistan (ACAA)"
NAV_TYPE = re.compile(r"\b(VORTAC|D?VOR/DME|D?VOR|NDB|DME|TACAN)\b")


def documents():
    page = fetch_text(PAGE)
    docs = {}
    for href, text in re.findall(r'<a[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', page, re.S):
        label = clean(html.unescape(re.sub(r"<[^>]+>", " ", text)))
        m = re.match(r"(ENROUTE|AERODROME) EDITION (\d+)\s+EFFECTIVE DATE\s+(\d{2} \w{3}\s+\d{4})", label)
        if m:
            docs[m.group(1)] = (href, m.group(2), datetime.strptime(clean(m.group(3)), "%d %b %Y").date())
    return docs


def parse_navaids(text):
    """ENR 4.1 rows; a long station name wraps onto the lines around the ID/coordinates line."""
    lines = text.splitlines()
    out = []
    for i, ln in enumerate(lines):
        c = LATLON.search(ln)
        m = re.search(r"\s([A-Z]{2,3})(?:-\s?X)?\s+(?:H24|NA|HJ|HN|O/R)\b", ln)
        if not (c and m):
            continue
        around = " ".join(clean(lines[j][:m.start(1)]) for j in (i - 1, i, i + 1) if 0 <= j < len(lines)
                          and (j == i or not LATLON.search(lines[j])))
        t = NAV_TYPE.search(around)
        if not t:
            continue
        f = re.search(r"(\d{3}\.\d+)|(\d{3})\s*KHz", ln[m.end():c.start()], re.I)
        freq = float(f.group(1) or f.group(2)) if f else None
        out.append({"ident": m.group(1), "type": t.group(1), "name": clean(around[:t.start()]) or None,
                    "frequency": freq, "frequency_unit": ("KHZ" if f and f.group(2) else "MHZ") if f else None,
                    "raw_frequency": clean(f.group(0)) if f else None,
                    "lat": dms(*c.groups()[0:4]), "lon": dms(*c.groups()[4:8]), "raw_coord": clean(c.group(0))})
    return out


def _prop(lines, label):
    """Text of one property row: the label line, else the lines above it (OAHR prints values
    above their label), else the lines below, stopping at the neighbouring numbered labels."""
    is_label = lambda ln: re.match(r"^\s*(?:\d+\.)?\s*[A-Z][A-Za-z]", ln) and not LATLON.search(ln)
    for k, ln in enumerate(lines):
        if re.search(label, ln):
            above = []
            for j in range(k - 1, -1, -1):
                if is_label(lines[j]) and not re.match(r"^\s*\(", lines[j]):
                    break
                above.insert(0, lines[j])
            below = []
            for j in range(k + 1, len(lines)):
                if is_label(lines[j]):
                    break
                below.append(lines[j])
            return ln, "\n".join(above), "\n".join(below)
    return "", "", ""


def _first(regex, parts, flags=0):
    for part in parts:
        found = list(re.finditer(regex, part, flags))
        if found:
            return found
    return []


def parse_runways_transposed(block):
    """AD 2.12 with one column per runway end: "[1.] RWY 11 29" / "BRG ... 107 º T ..." /
    "RWY Dimensions 3 511m x 45m" / "THR Coordinates <lat lon> <lat lon>"; repeated per runway."""
    runways = []
    for group in re.split(r"\n(?=\s*(?:1\.\s+)?RWY\s+\d{2})", block):
        rwy = re.search(r"^\s*(?:1\.\s+)?RWY\s+(\d{2}.*)$", group, re.M)
        if not rwy:
            continue
        desigs = re.findall(r"\b(\d{2}[LRC]?)\b", rwy.group(1))[:2]
        lines = group.splitlines()
        brg = _first(r"(\d{1,3}(?:\.\d+)?)\s*[º°]?\s*T\b", _prop(lines, r"BRG"))
        # "THR Coordinates", or "THR" with "Coordinates" on the next line (OAKS, OANZ, OAZI)
        coords = _first(LATLON.pattern, _prop(lines, r"THR\s+Coordinates|^\s*\d+\.?\s+THR\b(?!\s*Elevation)"))
        dim = _first(r"(\d[\d ,.]{1,6})\s*(m|M|ft)\s*[xX]\s*(\d+)\s*(m|M|ft)", _prop(lines, r"RWY\s+Dimensions"))
        sfc = re.search(r"\b(ASPH|ASPHALT|CONC|CONCRETE|GRAVEL|PAVED|ASP|BIT)\b", group, re.I)
        ends = [{"designator": d,
                 "lat": dms(*coords[k].groups()[0:4]) if k < len(coords) else None,
                 "lon": dms(*coords[k].groups()[4:8]) if k < len(coords) else None,
                 "raw_coord": clean(coords[k].group(0)) if k < len(coords) else None,
                 "bearing": float(brg[k].group(1)) if k < len(brg) else None,
                 "raw_bearing": clean(brg[k].group(0)) if k < len(brg) else None}
                for k, d in enumerate(desigs)]
        if not ends:
            continue
        length = width = None
        if dim:
            ft = lambda v, u: float(v.replace(" ", "").replace(",", "")) * (0.3048 if u == "ft" else 1)
            length, width = round(ft(dim[0].group(1), dim[0].group(2))), round(ft(dim[0].group(3), dim[0].group(4)))
        pair = "-".join(e["designator"] for e in ends)
        found = sum(e["lat"] is not None for e in ends)
        twin = next((r for r in runways if r["pair"] == pair), None)
        if twin:  # some aerodromes print the table twice; keep the copy with more thresholds
            if sum(e["lat"] is not None for e in twin["ends"]) >= found:
                continue
            runways.remove(twin)
        runways.append({"pair": pair, "length": length, "width": width,
                        "raw_dims": clean(dim[0].group(0)) if dim else None,
                        "surface": {"ASPHALT": "ASPH", "CONCRETE": "CONC"}.get(sfc.group(1).upper(), sfc.group(1).upper())
                        if sfc else None, "ends": ends})
    return runways


def scrape(log):
    docs = documents()
    enr_url, edition, eff = docs["ENROUTE"]
    ad_url = docs["AERODROME"][0]
    enr, ad = pdf_text(enr_url), pdf_text(ad_url)
    col = Collection(SOURCE, eff.isoformat(), f"EDITION {edition}", PAGE)
    col.documents += 2

    for w in parse_waypoints(section(enr, r"ENR 4\.4", r"ENR 4\.5")):
        col.add_waypoint(w, "ENR 4.4", enr_url)
    for n in parse_navaids(section(enr, r"ENR 4\.1", r"ENR 4\.2")):
        col.add_navaid(n, "ENR 4.1", enr_url)
    # ENR 3 points carry their coordinates far right of the name (up to column ~66)
    for r in parse_routes(section(enr, r"ENR 3\.1", r"ENR 3\.4"), name_width=66):
        col.add_route(r, "ENR 3", enr_url, lambda p: point_key(p["name"]),
                      nav_spec="RNP 10" if re.match(r"[A-Z]\d", r["designator"]) else None)

    # aerodrome blocks start at the real "XXXX AD 2.1 AERODROME LOCATION" heading
    heads = [(m.start(), m.group(1)) for m in
             re.finditer(r"^\s*(OA[A-Z]{2}) AD 2\.1 (?:AERODROME LOCATION|OA[A-Z]{2}\s*[–—-])", ad, re.M)]
    log(f"  AD 2: {len(heads)} aerodromes")
    for k, (start, icao) in enumerate(heads):
        block = ad[start: heads[k + 1][0] if k + 1 < len(heads) else len(ad)]
        a = parse_aerodrome(block, icao=icao)
        if not a:
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
            continue
        n = re.search(rf"{icao}\s*[–—-]\s*([^\n]+)", block)
        a["icao"], a["name"] = icao, clean(n.group(1)) if n else a["name"]
        a["raw_name"] = a["name"]
        rw = re.search(rf"{icao} AD 2\.12\b.*?(?={icao} AD 2\.13\b|\Z)", block, re.S)
        a["runways"] = parse_runways_transposed(rw.group(0)) if rw else []
        col.add_aerodrome(a, "AD 2", ad_url)
    return col
