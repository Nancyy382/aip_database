"""Helpers for Eurocontrol-style HTML eAIPs (French SIA, Colombia, Venezuela...)."""
import html as htmllib
import re

from .common import LAT, LATLON, LON, clean, dms, lat_of, lon_of, normalize_coords


def rows(page):
    """Table rows of an eAIP page as lists of cell texts (line breaks inside a cell -> ' ')."""
    page = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S | re.I)
    # hidden database annotations (Bahrain, Oman...): <span class="sdParams" style="display: none;">
    page = re.sub(r"<span[^>]*display:\s*none[^>]*>.*?</span>", "", page, flags=re.S | re.I)
    # eAIP marks deleted text (amendment history) with class="AmdtDeletedAIRAC"/"del"
    page = re.sub(r"<(del|span)\b[^>]*class=\"[^\"]*Deleted[^\"]*\"[^>]*>.*?</\1>", "", page, flags=re.S)
    page = re.sub(r"<del\b.*?</del>", "", page, flags=re.S | re.I)
    out = []
    for tr in re.findall(r"<tr\b.*?</tr>", page, re.S | re.I):
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
        out.append([cell_text(c) for c in cells])
    return out


def cell_text(cell):
    cell = re.sub(r"<br\s*/?>|</p>|</div>", " ", cell, flags=re.I)
    cell = clean(htmllib.unescape(re.sub(r"<[^>]+>", " ", cell)))
    cell = re.sub(r"(\d)\s*\.\s+(\d)|(\d)\s+\.\s*(\d)", r"\1\3.\2\4", cell)  # "115640 . 80N" -> "115640.80N"
    return normalize_coords(cell)


def text(page):
    """Whole page as plain text, one table row per line (cells joined by ' | ')."""
    return "\n".join(" | ".join(r) for r in rows(page))


def coord(s):
    """First lat/lon in a string, either as a pair or as 'Lat : ... Long : ...'."""
    s = s or ""
    m = LATLON.search(s)
    if m:
        return dms(*m.groups()[0:4]), dms(*m.groups()[4:8]), clean(m.group(0))
    la, lo = LAT.search(s), LON.search(s)
    if la and lo and lo.start() > la.start():
        return lat_of(la), lon_of(lo), f"{clean(la.group(0))} {clean(lo.group(0))}"
    return None


# runway "length x width": 2950 x 45, "2 772 X 60" (thousands separated by a space or comma)
DIMS = re.compile(r"(?<![\d.])(\d{1,2}[ ,.]\d{3}|\d{3,4})\s*m?\s*[xX×]\s*(\d{2,3})(?!\d)")  # also "3600m × 45m"

SURFACE_WORDS = {"revêtue": "PAVED", "non revêtue": "UNPAVED", "herbe": "GRASS", "latérite": "LATERITE",
                 "paved": "PAVED", "unpaved": "UNPAVED", "grass": "GRASS",
                 "pavimento": "PAVED", "asfalto": "ASPH", "hormigón": "CONC", "concreto": "CONC", "césped": "GRASS",
                 "tierra": "EARTH", "lastre": "GRAVEL", "asphalt": "ASPH", "concrete": "CONC", "gravel": "GRAVEL",
                 "sand/gravel": "SAND/GRAVEL"}
SURFACE_RE = re.compile(r"\b(Sand/Gravel|CONC/ASPH|CONC|ASPH|ASP|BIT|GRASS|GRAVEL|PAVED|UNPAVED|non revêtue|revêtue|herbe|"
                        r"latérite|laterite|unpaved|paved|grass|pavimento|asfalto|hormigón|concreto|césped|tierra|lastre|asphalt|concrete)\b", re.I)


def parse_ad2(page, icao):
    """AD 2 page of an HTML eAIP -> aerodrome record (see parsers.parse_aerodrome)."""
    page = re.sub(r"<table\b[^>]*AD_2_12[^\"]*internal_table\b.*?</table>", "", page, flags=re.S | re.I)
    rs = rows(page)
    arp = None
    for idx, r in enumerate(rs):
        if any(re.search(r"ARP|(?i:reference point)|Hnattstaða", x) for x in r):
            c = coord(" ".join(r))
            if not c and idx > 0:
                c = coord(" ".join(rs[idx - 1]))
            if not c and idx + 1 < len(rs):
                c = coord(" ".join(rs[idx + 1]))
            if c:
                arp = c
                break
    if not arp:
        return None
    elev = None
    for idx, r in enumerate(rs):
        joined = " ".join(r)
        if re.search(r"(?i)altitude|elev|Landhæð", joined) and not re.search(r"\bTHR\b|GUND", joined):
            for cand in [joined, " ".join(rs[idx - 1]) if idx > 0 else "", " ".join(rs[idx + 1]) if idx + 1 < len(rs) else ""]:
                m = re.search(r"(\d+(?:\.\d+)?)\s*FT", cand, re.I)
                mm = None if m else re.search(r"(\d+(?:[.,]\d+)?)\s*M\b", cand)
                if m or mm:
                    elev = (round(float(m.group(1)) if m else float(mm.group(1).replace(",", ".")) * 3.28084), cand)
                    break
            if elev is not None:
                break
    # the AD 2.1 heading is followed by "XXXX — NAME"; tables later also list "XXXX - ADC Chart" files
    plain = htmllib.unescape(re.sub(r"<[^>]+>", "\n", page)).replace("\xa0", " ")
    after = plain[plain.find("AD 2.1"):] if "AD 2.1" in plain else ""
    # "XXXX — NAME", or "XXXX NAME" without a dash (Oman); skip the "XXXX AD 2.x" headings
    m = next((m for m in re.finditer(rf"^\s*{icao}\s*(?:[–—-]\s*)?([^\n]{{3,100}})$", after[:3000], re.M)
              if not re.match(r"\s*AD\s*2", m.group(1))), None)
    name = clean(m.group(1)) if m and not re.search(r"(?i)chart|\.pdf", m.group(1)) else None
    in_table = next((clean(m.group(1)) for r in rs for m in [re.search(rf"\b{icao}\s*[-–—]\s*(.+)", " ".join(r))]
                     if m and not re.search(r"(?i)chart|\bADC\b|APDC|\.pdf", m.group(1))), None)
    # the table cell has the full name when the heading line breaks it ("MAIQUETIA /" ...)
    if in_table and re.search(r"[A-Za-z]{3}", in_table) and (not name or in_table.startswith(name.rstrip(" /"))):
        name = in_table
    if not name:  # name line outside tables: "SEQM – QUITO / Mariscal Sucre Intl."
        name = next((clean(m.group(1)) for m in re.finditer(rf"^\s*{icao}\s*[–—-]\s*(\S[^\n]{{2,80}})$", plain, re.M)
                     if not re.search(r"(?i)chart|\bADC\b|APDC|\.pdf", m.group(1))), None)
    if not name:
        t = re.search(r"<title>(.*?)</title>", page, re.S)
        name = clean(re.sub(r"<[^>]+>", " ", t.group(1))) if t else None

    # AD 2.12: header row with a bearing column, then one row per runway end
    ends, cols = [], None
    for r in rs:
        joined = " ".join(r)
        if cols is None:
            if len(r) >= 4 and re.search(r"BRG|Bearing", joined, re.I) and re.search(r"RWY|pista|Designa", r[0], re.I):
                find = lambda pat: next((i for i, c in enumerate(r) if re.search(pat, c, re.I)), None)
                cols = {"brg": find(r"BRG|Bearing"), "dims": find(r"Dimension|DMN"),
                        "sfc": find(r"SFC|surface|superficie|Strength"), "thr": find(r"COORD|Position GEO|THR")}
            continue
        # one row per end ("09"), or one row for the whole runway ("11/29", Oman)
        if not r or not re.fullmatch(r"\d{2}[LRC]?(?:\s*/\s*\d{2}[LRC]?)?", r[0].strip()):
            if ends and (re.search(r"Slope|SWY|OFZ|RESA|Declared|AD\s*2\.\d+", joined, re.I) or (len(r) >= 3 and any(re.search(r"RWY|Designa", c, re.I) for c in r))):
                break
            continue
        cell = lambda k: r[cols[k]] if cols.get(k) is not None and cols[k] < len(r) else ""
        if "/" in r[0]:
            d = DIMS.search(cell("dims"))
            sf = SURFACE_RE.search(cell("sfc"))
            for desig in re.split(r"\s*/\s*", r[0]):
                ends.append({"designator": desig, "lat": None, "lon": None, "raw_coord": None,
                             "bearing": None, "raw_bearing": None,
                             "dims": (float(re.sub(r"[ ,.]", "", d.group(1))), float(d.group(2)), d.group(0)) if d else None,
                             "surface": SURFACE_WORDS.get(sf.group(1).lower(), sf.group(1).upper()) if sf else None})
            continue
        c = coord(cell("thr")) or coord(" ".join(r[1:]))
        geo = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*°?\s*GEO", cell("brg"))
        b = geo or re.match(r"\s*(\d{1,3}(?:[.,]\d+)?)", cell("brg"))
        d = DIMS.search(cell("dims"))
        sf = SURFACE_RE.search(cell("sfc"))
        ends.append({"designator": r[0], "lat": c[0] if c else None, "lon": c[1] if c else None,
                     "raw_coord": c[2] if c else None,
                     "bearing": float(b.group(1).replace(",", ".")) if b else None, "raw_bearing": cell("brg") or None,
                     "dims": (float(re.sub(r"[ ,.]", "", d.group(1))), float(d.group(2)), d.group(0)) if d else None,
                     "surface": SURFACE_WORDS.get(sf.group(1).lower(), sf.group(1).upper()) if sf else None})
    runways, used = [], set()
    for i, a in enumerate(ends):
        if i in used:
            continue
        used.add(i)
        pair = [a]
        for j in range(i + 1, len(ends)):
            if j not in used and (int(a["designator"][:2]) + 17) % 36 + 1 == int(ends[j]["designator"][:2]):
                used.add(j)
                pair.append(ends[j])
                break
        dims = next((e["dims"] for e in pair if e["dims"]), (None, None, None))
        runways.append({"pair": "-".join(e["designator"] for e in pair), "length": dims[0], "width": dims[1],
                        "raw_dims": dims[2], "surface": next((e["surface"] for e in pair if e["surface"]), None),
                        "ends": pair})
    return {"icao": icao, "name": name, "raw_name": name, "lat": arp[0], "lon": arp[1], "raw_coord": arp[2],
            "elevation_ft": elev[0] if elev else None, "raw_elevation": elev[1] if elev else None,
            "runways": runways}


def parse_routes(page_text):
    """ENR 3 tables: a designator line ("A247"), then "symbol | point name | coordinates" rows."""
    routes, cur = [], None
    last_point_name = None
    for ln in page_text.splitlines():
        cells = [clean(c) for c in ln.split("|")]
        idx = next((i for i, c in enumerate(cells) if coord(c)), None)
        # designator alone on its line, or first cell of a row without coordinates ("A453 ( RNAV 1 ) | |")
        d = re.match(r"\s*(U?[A-Z]{1,2}\d{1,4}[A-Z]?)(?:\s*\(.*\))?\s*$", cells[0]) if idx is None else None
        if d:
            cur = {"designator": d.group(1), "points": []}
            routes.append(cur)
            last_point_name = None
            continue
        if cur is None:
            continue
        if idx is None:
            cand = next((c for c in cells if re.fullmatch(r"[\w0-9][\w0-9 ()/'.,-]{1,50}", c) and not c.endswith(":")), None)
            if cand and cand not in ("Odd", "Even") and not re.search(r"^\d+\s*NM$", cand):
                last_point_name = cand
            continue
        # "symbol | NAME | coordinates" (France, COCESNA), "NAME | coordinates" (Bermuda) or
        # "symbol | NAME coordinates" in one cell (Bahrain)
        c = coord(cells[idx])
        before = clean(cells[idx][: cells[idx].find(c[2].split(" ")[0])])
        # a symbol-font glyph renders as one lower-case letter: "p MIDSI (5) 264142N ..." (Qatar)
        before = re.sub(r"^[a-z]\s+", "", before)
        name = before or (cells[idx - 1] if idx else None) or last_point_name
        # remark rows also quote coordinates ("... points: 123456N ..."); a point name is short caps
        if not name or not re.fullmatch(r"[\w0-9][\w0-9 ()/'.,-]{1,50}", name) or name.endswith(":"):
            continue
        cur["points"].append({"name": name, "lat": c[0], "lon": c[1], "raw_coord": c[2]})
        last_point_name = None
    return [r for r in routes if len(r["points"]) >= 2]
