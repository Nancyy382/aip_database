"""Parsers for ICAO-format AIP sections, working on `pdftotext -layout` text.

Every South American AIP follows ICAO Annex 15 numbering (ENR 3 routes, ENR 4.1
navaids, ENR 4.4 significant points, AD 2.2 ARP, AD 2.12 runways), so the
layouts are close enough that one set of tolerant parsers covers most states.

Parsers return plain records that keep the source text next to each value
(`raw_*` keys); `features.py` turns them into viewer features.
"""
import re

from .common import LAT, LATLON, LON, clean, dms, lat_of, lon_of
from .eaip_html import strength

NAVAID_TYPES = r"(?:VOR/TACAN|D?VOR/DME|VOR/DME|VORTAC|D?VOR|NDB/DME|NDB|TACAN|DME|LOC|ILS|GP|MKR|L)"
PAGE_NOISE = re.compile(r"^\s*(AIP\b|DEPARTAMENTO|DIRECCI[OÓ]N|AIRAC|AMDT|ENR \d|AD \d|\d+(\s+\d+){3,}\s*$)")


def _lines(text):
    # private-use glyphs are chart symbols (compulsory reporting point etc.)
    text = re.sub(r"[←-⯿-]", " ", text)  # arrows, ▲ ∆ ❐ Ⓜ ...
    return text.replace("\f", "\n").splitlines()


def _pair(m):
    """LATLON match -> (lat, lon, raw text)."""
    return dms(*m.groups()[0:4]), dms(*m.groups()[4:8]), clean(m.group(0))


# --- ENR 4.4 significant points -------------------------------------------

WAYPOINT_LINE = re.compile(r"^\s*([A-Z]{5})\b\s*[*()]*\s*(.*)$")


def parse_waypoints(text):
    """ENR 4.4: `AKNEL   234756S-0605944W   UM799 ...`, or latitude on the name line and
    longitude on the next one (Uruguay)."""
    out, seen = [], set()
    lines = _lines(text)
    for i, ln in enumerate(lines):
        m = WAYPOINT_LINE.match(ln)
        if not m:
            continue
        rest = m.group(2)
        c = LATLON.search(rest)
        if c:
            lat, lon, raw = _pair(c)
            usage = rest[c.end():]
        else:
            # latitude(s) on this line, longitude(s) on the next; two-column tables (Cayman)
            # carry a second "NAME lat" pair whose longitude is the second one below
            heads = [(n.group(1), n.group(2)) for n in re.finditer(r"\b([A-Z]{5})\s+(" + LAT.pattern + ")", ln)]
            lons = list(LON.finditer(lines[i + 1])) if i + 1 < len(lines) else []
            if not heads or len(lons) < len(heads):
                continue
            for (ident, lat_txt), lo in zip(heads, lons):
                la = LAT.search(lat_txt)
                lat, lon = lat_of(la), lon_of(lo)
                if (ident, lat, lon) not in seen:
                    seen.add((ident, lat, lon))
                    after = ln[ln.find(lat_txt) + len(lat_txt):]
                    out.append({"ident": ident, "lat": lat, "lon": lon,
                                "raw_coord": f"{clean(la.group(0))} {clean(lo.group(0))}",
                                "usage": clean(re.split(r"\s{3,}[A-Z]{5}\s", after)[0]) or None})
            continue
        if (m.group(1), lat, lon) in seen:
            continue
        seen.add((m.group(1), lat, lon))
        out.append({"ident": m.group(1), "lat": lat, "lon": lon, "raw_coord": raw,
                    "usage": clean(usage) or None})
    return out


# --- ENR 4.1 radio navigation aids ----------------------------------------

NAVAID_ANCHOR = re.compile(
    r"^(?P<name>.*?)\s{2,}(?P<type>" + NAVAID_TYPES + r")\s+(?P<ident>[A-Z]{2,4})\s+"
    r"(?P<rest>.*)$"
)
FREQ = re.compile(r"\b(\d{3}(?:[.,]\s?\d{1,3})?)\s*(MHZ|KHZ)?\b", re.I)


def freq_unit(freq, unit=None):
    if unit:
        return unit.upper()
    return "MHZ" if "." in freq and float(freq) >= 100 else "KHZ"


def parse_navaids(text, name_width=22):
    """ENR 4.1 table. Coordinates sit on the anchor row or the rows just above/below it."""
    lines = _lines(text)
    out, seen = [], set()
    for i, ln in enumerate(lines):
        m = NAVAID_ANCHOR.match(ln)
        # "DME  CH 90X" continuation rows look like anchors with ident CH
        if not m or "RADIO AID" in ln or "RADIOAYUDA" in ln or m.group("ident") == "CH":
            continue
        coord = None
        for j in (i, i - 1, i - 2, i + 1):
            if not 0 <= j < len(lines):
                continue
            c = LATLON.search(lines[j])
            if c:
                coord = _pair(c)
                break
            la = LAT.search(lines[j])
            if la:
                for k in (j, j + 1, j + 2):
                    lo = LON.search(lines[k]) if k < len(lines) else None
                    if lo:
                        coord = (lat_of(la), lon_of(lo), f"{clean(la.group(0))} {clean(lo.group(0))}")
                        break
                if coord:
                    break
        if not coord:
            continue
        name = clean(m.group("name"))
        # wrapped station names: "GENERAL / [anchor] / BELGRANO", "VCOM / [anchor] / MARAMBIO"
        for j in (i - 1, i + 1):
            if 0 <= j < len(lines):
                extra = clean(lines[j][:name_width])
                if (extra and not NAVAID_ANCHOR.match(lines[j]) and not LAT.search(extra)
                        and not PAGE_NOISE.match(lines[j]) and re.fullmatch(r"[A-ZÁÉÍÓÚÑÜ .'/-]+", extra)):
                    name = f"{extra} {name}" if j < i else f"{name} {extra}"
        f = FREQ.search(m.group("rest"))
        freq = f.group(1).replace(" ", "").replace(",", ".") if f else None
        key = (m.group("ident"), m.group("type"), coord[0], coord[1])
        if key in seen:
            continue
        seen.add(key)
        out.append({"ident": m.group("ident"), "type": m.group("type"), "name": clean(name),
                    "frequency": float(freq) if freq else None,
                    "frequency_unit": freq_unit(freq, f.group(2)) if freq else None,
                    "raw_frequency": clean(f.group(0)) if f else None,
                    "lat": coord[0], "lon": coord[1], "raw_coord": coord[2]})
    return out


IDENT_FREQ_ANCHOR = re.compile(
    r"^(?P<name>.*?)\s+(?P<ident>[A-Z]{2,3})\s+(?P<freq>\d{3,4}(?:[.,]\d{1,3})?|CH\s?\d{1,3}[XY])\s*(?P<unit>MHZ|KHZ)?\s+(?P<rest>.*)$",
    re.I)
TYPE_WORD = re.compile(r"\b(" + NAVAID_TYPES + r")\b")


def parse_navaids_ident_first(text, name_width=14):
    """ENR 4.1 variant where the type sits under the station name (Panama, Suriname...):

         BOCAS DEL
           TORO       BDT    114.9     H-24    092019.86N
          VOR/DME            (96X)            0821506.34W
    """
    lines = _lines(text)
    out, seen = [], set()
    for i, ln in enumerate(lines):
        m = IDENT_FREQ_ANCHOR.match(ln)
        if not m or m.group("ident") in ("CH", "FT", "NM", "MHZ", "KHZ", "HR", "VAR"):
            continue
        coord = None
        for j in (i, i + 1, i - 1):
            if not 0 <= j < len(lines):
                continue
            c = LATLON.search(lines[j])
            if c:
                coord = _pair(c)
                break
            la = LAT.search(lines[j])
            lo = LON.search(lines[j + 1]) if la and j + 1 < len(lines) else None
            if la and lo:
                coord = (lat_of(la), lon_of(lo), f"{clean(la.group(0))} {clean(lo.group(0))}")
                break
        if not coord:
            continue
        # type: the nearest line that names one ("VOR/DME" under the station name)
        near = sorted(range(max(0, i - 2), min(len(lines), i + 3)), key=lambda j: (abs(j - i), -j))  # ties: below
        tj = next((j for j in near if TYPE_WORD.search(clean(lines[j][:name_width + 2]) if j != i else m.group("name"))), None)
        ntype = TYPE_WORD.search(clean(lines[tj][:name_width + 2]) if tj != i else m.group("name")).group(1) \
            if tj is not None else None
        name_parts = []
        for j in range(max(0, i - 3), min(len(lines), i + 3)):
            left = clean(lines[j][:name_width + 2]) if j != i else clean(m.group("name"))
            t = TYPE_WORD.search(left)
            if t:
                left = clean(left[:t.start()])
            if left and abs(j - i) <= 1 + (j < i) and re.fullmatch(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü .'/-]+", left) \
                    and left.lower() != "null" and not PAGE_NOISE.match(lines[j]):
                name_parts.append(left)
        key = (m.group("ident"), coord[0], coord[1])
        if key in seen or not ntype:
            continue
        seen.add(key)
        freq = m.group("freq").replace(",", ".")
        if freq.startswith("CH"):  # DME-only station: channel instead of frequency ("CH 82X")
            freq = "9999"
        placeholder = float(freq) >= 999  # "999.99 MHZ" / "9999.00 MHZ" = not published
        name = re.sub(r"(\w)- (\w)", r"\1\2", clean(" ".join(name_parts)))  # "Vir- ginia" -> "Virginia"
        out.append({"ident": m.group("ident"), "type": ntype, "name": name or None,
                    "frequency": None if placeholder else float(freq),
                    "frequency_unit": None if placeholder else freq_unit(freq, m.group("unit")),
                    "raw_frequency": clean(f"{m.group('freq')} {m.group('unit') or ''}"),
                    "lat": coord[0], "lon": coord[1], "raw_coord": coord[2]})
    return out


# --- ENR 3 ATS routes -----------------------------------------------------

# designator alone on its line, or followed far to the right by remarks ("A 310    Para continuar,")
ROUTE_DESIGNATOR = re.compile(r"^\s{0,14}([A-Z]{1,2}\s?\d{1,4}[A-Z]?)\s*(?:\(.*?\))?\s*(?:$|\s{10,}\S.*$)")


def parse_routes(text, name_width=34):
    """ENR 3.x: designator line, then for each point a left-column name and coordinate line."""
    routes, cur, name_buf = [], None, []
    lines = _lines(text)
    skip = set()
    for i, ln in enumerate(lines):
        if i in skip or PAGE_NOISE.match(ln) or not ln.strip():
            continue
        d = ROUTE_DESIGNATOR.match(ln)
        if d:
            cur = {"designator": d.group(1).replace(" ", ""), "points": []}
            routes.append(cur)
            name_buf = []
            continue
        left = ln[:name_width]
        c = LATLON.search(left)
        coord = _pair(c) if c else None
        if not c and cur is not None:
            # latitude on this line, longitude on the next non-empty one (Paraguay)
            la = LAT.search(left)
            nxt = next((j for j in range(i + 1, min(i + 4, len(lines))) if LON.search(lines[j][:name_width])),
                       None) if la else None
            lo = LON.search(lines[nxt][:name_width]) if nxt is not None else None
            if lo:
                coord = (lat_of(la), lon_of(lo), f"{clean(la.group(0))} {clean(lo.group(0))}")
                c = la
                skip.add(nxt)
        if coord and cur is not None:
            lat, lon, raw = coord
            before = clean(left[:c.start()])
            name = clean(" ".join(name_buf + ([before] if before else [])))
            cur["points"].append({"name": name or None, "lat": lat, "lon": lon, "raw_coord": raw})
            name_buf = []
            continue
        # only the first text block: the distance column ("52 NM") starts right after the name
        txt = clean(re.split(r"\s{3,}", left.strip())[0])
        if (cur is not None and txt and re.fullmatch(r"[A-ZÁÉÍÓÚÑÜ0-9 .'/()-]+", txt)
                and re.search(r"[A-Z]{2}", txt)):
            name_buf.append(txt)
            name_buf = name_buf[-3:]
    return merge_routes([r for r in routes if len(r["points"]) >= 2])


def merge_routes(routes):
    """A route split over pages appears twice with the same designator; join consecutive parts."""
    merged = {}
    for r in routes:
        prev = merged.get(r["designator"])
        if prev and (prev["points"][-1]["lat"], prev["points"][-1]["lon"]) == (r["points"][0]["lat"], r["points"][0]["lon"]):
            prev["points"] += r["points"][1:]
        elif prev:
            n = sum(k.split("#")[0] == r["designator"] for k in merged) + 1
            merged[f"{r['designator']}#{n}"] = r
        else:
            merged[r["designator"]] = r
    return list(merged.values())


def point_key(name):
    """Route point name -> natural key of the waypoint/navaid it refers to."""
    name = name or ""
    name = name.replace("'", " ").replace('"', " ")  # Bahamas quotes navaids: 'ZBV'
    m = re.search(r"\bARP\b.*\(\s*([A-Z]{4})\s*\)", name)  # "RIVERA ARP (SURV)" = aerodrome
    if m:
        return m.group(1)
    m = re.search(r"\(\s*([A-Z]{2,3})\s*\)", name)  # "TABOGA DVOR/DME (TBG)", "... VOR-DME ( CYR )"
    if m and re.search(r"\b(?:D?VOR|NDB|DME|TACAN|VORTAC)\b", name):
        return "NAV/" + m.group(1)
    name = re.sub(r"\((?:FIR\s*B[DR]{2}Y|\d+|\*+)\)", " ", name)  # "BUFEO (FIR BDRY) (1)"
    name = re.sub(r"\b(?:FIR|B[DR]{2}Y|\d+)\b", " ", name)          # notes split over lines
    name = clean(re.sub(r"[-ⓂⓇ▲△*()]", " ", name))
    m = re.search(r"\b(?:D?VOR|NDB|DME|TACAN|VORTAC)\b.*?\b([A-Z]{2,3})$", name)
    if m and m.group(1) not in ("VOR", "DME", "NDB"):
        return "NAV/" + m.group(1)
    if m:  # "Bermuda VOR/DME", "GRAND CAYMAN VOR/DME": no ident, resolved later by station name
        return "NAV/" + clean(name[:m.start()]).upper()
    m = re.fullmatch(r"([A-Z]{2,3})\s+(?:D?VOR|NDB|DME|TACAN|VORTAC)(?:/DME)?", name)
    if m:
        return "NAV/" + m.group(1)
    # notes collected with the name ("UNUSABLE GADER"): a 5-letter name-code wins
    five = re.findall(r"\b[A-Z]{5}\b", name)
    token = five[-1] if five else (name.split(" ")[-1] if name else "")
    return ("NAV/" if re.fullmatch(r"[A-Z]{2,3}", token) else "WPT/") + token if token else None


# --- AD 2 aerodrome data ---------------------------------------------------

SURFACES = r"(CONC|ASPH|ASP|ASFALTO|ASFALTICO|HORMIG[OÓ]N|GRASS|GRAVEL|GRAVA|TIERRA|EARTH|CLAY|SAND|BIT|BITUMEN|PAVED|DIRT|RIPIO|CESPED|CÉSPED|MACADAM|TRATAMIENTO|FLEXIBLE|R[IÍ]GIDO)"
RWY_DESIG = re.compile(r"^\s{0,16}(?:RWY\s*)?(\d{2}[LRC]?)(?=\s*(?:\(\*+\))?(?:\s{2,}|\s+\d{2,3}[.,°º]|\s*$))")
DIMS = re.compile(r"\b(\d{1,2}[., ]?\d{3}|\d{3,4})\s?[xX×]\s?(\d{2,3})\b")  # 2.350 / 1 250 / 3205
BEARING = re.compile(r"\b(\d{1,3}(?:[.,]\d{1,2})?)\s?(?:[°ºª]|(?<=\d)T\b|(?=\s?(?:GEO|MAG)\b))")
ELEV = re.compile(r"(\d+(?:[.,]\d+)?)\s?(?:M|m)\b\s*\(?\s*(\d+)\s?(?:FT|ft)")
ELEV_FT = re.compile(r"(\d+(?:[.,]\d+)?)\s?(?:FT\b|ft\b|[’'′](?!'))")


# "AD 2.12", or numbered per aerodrome as in Uruguay: "SUAA AD 2.8-12"
AD_ITEM = r"AD 2(?:\.\d+-|\.){}(?!-)"


def section(text, start, end):
    # headings may carry the location indicator: "SCEL AD 2.12"
    # skip table-of-contents lines ("ENR 4.1 Radio navigation aids ……… ENR 4.1-1")
    m = next((m for m in re.finditer(rf"^\s*(?:[A-Z]{{4}}\s+)?{start}(?![\d.]).*$", text, re.M)
              if not re.search(r"…|\.{4,}", m.group(0))), None)
    if not m:
        return ""
    e = re.search(rf"^\s*(?:[A-Z]{{4}}\s+)?{end}(?![\d.])", text[m.end():], re.M)
    return text[m.start(): m.end() + (e.start() if e else len(text))]


def _num(s):
    s = s.replace(",", ".").replace(" ", ".")
    if re.fullmatch(r"\d{1,2}\.\d{3}", s):  # "2.350" = 2350 m
        s = s.replace(".", "")
    return float(s)


def parse_aerodrome(text, icao=None, name=None):
    """AD 2 text for one aerodrome -> record with ARP, elevation and runways (or None)."""
    head = section(text, AD_ITEM.format(1), AD_ITEM.format(3)) or text[:6000]
    raw_name = None
    m = re.search(r"\b([A-Z]{4})\s*[-–—]\s*([A-ZÁÉÍÓÚÑÜ][^\n]{2,80})", head)
    if m:
        raw_name = clean(m.group(0))
        icao = icao or m.group(1)
        name = name or clean(m.group(2))
    c = LATLON.search(head)
    if c:
        lat, lon, raw = _pair(c)
    else:
        la, lo = LAT.search(head), LON.search(head)
        if not (la and lo):
            return None
        lat, lon, raw = lat_of(la), lon_of(lo), f"{clean(la.group(0))} {clean(lo.group(0))}"
    elev_ft = raw_elev = None
    head_lines = head.splitlines()
    for k, ln in enumerate(head_lines):
        if not re.search(r"(?i)\bELEV|FLUGPLATZH", ln) or re.search(r"(?i)\bTHR\b|GUND|underlined", ln):
            continue
        # the value is on the label line, the next one (Chile) or a line above (Austria)
        seg = "\n".join(head_lines[k: k + 2]) + "\n" + "\n".join(head_lines[max(0, k - 3): k])
        e = ELEV.search(seg)
        f = None if e else ELEV_FT.search(seg)
        if e:
            elev_ft, raw_elev = int(e.group(2)), clean(e.group(0))
        elif f:
            elev_ft, raw_elev = round(float(f.group(1).replace(",", "."))), clean(f.group(0))
        if elev_ft is not None:
            break
    return {"icao": icao, "name": name, "raw_name": raw_name or name,
            "lat": lat, "lon": lon, "raw_coord": raw, "elevation_ft": elev_ft, "raw_elevation": raw_elev,
            "runways": parse_runways(section(text, AD_ITEM.format(12), AD_ITEM.format(13)) or
                                     section(text, r"12\.\s+Runway Physical", r"13\.\s+Declared Distances"))}


def parse_runways(block):
    """AD 2.12 table -> [{pair, length, width, surface, ends: [{designator, lat, lon, bearing}]}]."""
    if not block:
        return []
    # keep only the first half of the table: between the "1 2 3 ..." column-number row
    # and the next one (SWY/CWY/strip columns), which also drops the remarks
    numbering = list(re.finditer(r"^\s*1(\s+\d{1,2}){3,}\s*$", block, re.M))
    body = block
    if numbering:
        start = numbering[0].end()
        nxt = re.search(r"^\s*(?:\d{1,2}\s+)?(?:7|8)(\s+\d{1,2}){2,}\s*$", block[start:], re.M)
        body = block[start: start + (nxt.start() if nxt else len(block))]
    block_head = block[: numbering[0].start()] if numbering else block[:1500]
    # "Dimensions of RWY (FT)" with no metre column (some Iranian aerodromes): convert to metres
    feet = "(FT)" in block_head and not re.search(r"\((?:m|M)\)", block_head)
    lines = body.splitlines()
    rows = []  # (line index, designator)
    for n, ln in enumerate(lines):
        d = RWY_DESIG.match(ln)
        if d and d.group(1) not in [r[1] for r in rows]:
            rows.append((n, d.group(1)))
    if not rows:
        return []
    # Each end owns the lines from just above its designator row (lat/bearing are often
    # printed one line higher) to just above the next designator; first value wins.
    # Threshold coordinates: pair each latitude with the longitude printed under it (same
    # column, within 2 lines), give every designator row the zone halfway to its neighbours,
    # and take the zone's first pair - tables list THR before DTHR/RWY-end coordinates.
    pairs, used_lon = [], set()
    for i, ln in enumerate(lines):
        for la in LAT.finditer(ln):
            best = None
            for j in range(i, min(i + 3, len(lines))):
                for lo in LON.finditer(lines[j]):
                    if (j, lo.start()) in used_lon or (j == i and lo.start() < la.start()):
                        continue
                    score = (j - i, abs(lo.start() - la.start()) if j > i else 0)
                    if (j == i or abs(lo.start() - la.start()) <= 8) and (best is None or score < best[0]):
                        best = (score, j, lo)
            if best:
                used_lon.add((best[1], best[2].start()))
                pairs.append((i, la, best[2]))
    thr_lat, thr_lon = {}, {}
    for k, (n, _) in enumerate(rows):
        lo_edge = (rows[k - 1][0] + n) / 2 if k else -1e9
        hi_edge = (n + rows[k + 1][0]) / 2 if k + 1 < len(rows) else 1e9
        first = next(((la, lo) for i, la, lo in pairs if lo_edge < i <= hi_edge), None)
        if first:
            thr_lat[n], thr_lon[n] = first
    ends, dims, surfaces, strengths = [], [], [], []
    for k, (n, desig) in enumerate(rows):
        # adjacent designator rows (one line each) must not borrow each other's line
        start = max(0, n - 1) if k == 0 or rows[k - 1][0] < n - 1 else n
        end = (rows[k + 1][0] - 1 if rows[k + 1][0] - 1 > n else n + 1) if k + 1 < len(rows) else len(lines)
        block = lines[start:end]
        text = "\n".join(block)
        # some tables print the GEO bearing two lines above the designator
        above = lines[n - 2] if n >= 2 and (k == 0 or n - 2 > rows[k - 1][0]) else ""
        la, lo = thr_lat.get(n), thr_lon.get(n)
        # bearing: a value near the row that matches the designator (RWY 35 ~ 350°), GEO first
        heading = int(desig[:2]) * 10
        cand = []
        for i in range(max(0, n - 3), min(len(lines), n + 4)):
            for m in BEARING.finditer(lines[i]):
                v = _num(m.group(1))
                if abs((v - heading + 180) % 360 - 180) <= 35:
                    geo_label = bool(re.match(r"\s*GEO", lines[i][m.end():]))
                    cand.append((not geo_label, abs(i - n), m))
        geo = min(cand, key=lambda c: c[:2])[2] if cand and not min(cand, key=lambda c: c[:2])[0] else None
        b = min(cand, key=lambda c: c[:2])[2] if cand else None
        if b is None:  # bare number on the designator row ("11   115.92   3500 x 45", Austria)
            b = next((m for m in re.finditer(r"(?<![\d.])(\d{2,3}\.\d{1,2})(?![\d.])", lines[n])
                      if abs((_num(m.group(1)) - heading + 180) % 360 - 180) <= 20), None)
        # a table with only a "BRG MAG" column publishes magnetic bearings (Paraguay)
        magnetic = not geo and bool(re.search(r"\bMAG\b", block_head)) and not re.search(r"\b(GEO|TRUE|True)\b", block_head)
        dm = DIMS.search(text)
        sf = re.search(SURFACES, text.upper())
        ends.append({"designator": desig,
                     "lat": lat_of(la) if la and lo else None, "lon": lon_of(lo) if la and lo else None,
                     "raw_coord": f"{clean(la.group(0))} {clean(lo.group(0))}" if la and lo else None,
                     "bearing": _num(b.group(1)) if b and not magnetic else None,
                     "mag_bearing": _num(b.group(1)) if b and magnetic else None,
                     "raw_bearing": clean(b.group(0)) if b else None})
        dims.append((_num(dm.group(1)), _num(dm.group(2)), clean(f"{dm.group(1)} x {dm.group(2)}")) if dm else None)
        surfaces.append(sf.group(1) if sf else None)
        strengths.append(strength(text))
    # pair reciprocal ends (13/31, 09L/27R)
    pairs, used = [], set()
    for i, a in enumerate(ends):
        if i in used:
            continue
        used.add(i)
        na = int(a["designator"][:2])
        for j in range(i + 1, len(ends)):
            if j not in used and (na + 18 - 1) % 36 + 1 == int(ends[j]["designator"][:2]):
                used.add(j)
                pairs.append([a, ends[j]])
                break
        else:
            pairs.append([a])
    # dimensions/surface are printed on one or both ends of a pair
    runways = []
    for pair_ends in pairs:
        idx = [ends.index(e) for e in pair_ends]
        d = next((dims[i] for i in idx if dims[i]), (None, None, None))
        s = next((surfaces[i] for i in idx if surfaces[i]), None)
        pcn = next((strengths[i] for i in idx if strengths[i]), None)
        if feet and d[0] is not None:
            d = (round(d[0] * 0.3048), round(d[1] * 0.3048) if d[1] else None, d[2] + " FT")
        runways.append({"pair": "-".join(e["designator"] for e in pair_ends),
                        "length": d[0], "width": d[1], "raw_dims": d[2], "surface": s, "strength": pcn,
                        "ends": pair_ends})
    return runways
