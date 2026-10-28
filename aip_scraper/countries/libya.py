"""Libya - Libyan Civil Aviation Authority (https://caa.gov.ly/ais/).

AIP documents are published as PDFs on the official AIS portal:
- ENR 4.1: Radio navigation aids (pdfId 71 & 72)
- ENR 4.4: Significant points (pdfId 75, 76, 77, 78)
- ENR 3.1 & 3.2: ATS routes (pdfId 36 to 70)
- AD 2 & AD 3: 14 aerodrome PDFs under /ais/AD/DownloadPDF?pdfId=X
"""
import os
import re
import subprocess
import tempfile

from .. import common, parsers
from ..features import Collection

PAGE = "https://caa.gov.ly/ais/"
BASE = "https://caa.gov.ly/"
SOURCE = "AIP Libya (Libyan Civil Aviation Authority)"
EFF_DATE = "2023-11-30"
AMDT_ID = "AIRAC AMDT 02/23"

AD_LIST = [
    ("HLGD", 21), ("HLKF", 22), ("HLLB", 23), ("HLLM", 24),
    ("HLLQ", 25), ("HLLS", 26), ("HLLT", 27), ("HLMS", 28),
    ("HLGT", 15), ("HLBK", 16), ("HLTD", 17), ("HLTQ", 18),
    ("HLUB", 19), ("HLZW", 20)
]


def ocr_ad_pdf(data, icao):
    """Run pdftoppm + tesseract on first 5 pages of scanned aerodrome PDF."""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, f"{icao}.pdf")
        with open(p, "wb") as f:
            f.write(data)
        subprocess.run(["pdftoppm", "-png", "-r", "150", "-f", "1", "-l", "5", p, os.path.join(td, "pg")],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        imgs = sorted([os.path.join(td, fn) for fn in os.listdir(td) if fn.endswith(".png")])
        pages = []
        for img in imgs:
            t = subprocess.check_output(["tesseract", img, "stdout"],
                                        stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
            t = re.sub(r"(\d)\s*£", r"\1 E", t)
            t = re.sub(r"£", r"E", t)
            pages.append(t)
        return common.normalize_coords("\f".join(pages))


def parse_navaids_pdf(txt):
    """Parse ENR 4.1 table where lat/name is above and lon/type is below ident row."""
    lines = txt.splitlines()
    navaids = []
    for i, ln in enumerate(lines):
        m_freq = re.search(r"\b(\d{2,4}(?:\.\d+)?)\s*(MHz|KHz)\b", ln, re.I)
        if not m_freq:
            continue
        before_freq = ln[:m_freq.start()].strip()
        m_id = re.search(r"\b([A-Z]{2,4})\b", before_freq)
        if not m_id:
            continue
        ident = m_id.group(1)
        prev_ln = lines[i - 1] if i > 0 else ""
        next_ln = lines[i + 1] if i + 1 < len(lines) else ""
        la = common.LAT.search(prev_ln) or common.LAT.search(ln)
        lo = common.LON.search(next_ln) or common.LON.search(ln)
        if not (la and lo):
            continue
        m_type = (re.search(r"\b(D?VOR(?:/DME)?|NDB(?:/DME)?|DME)\b", next_ln) or
                  re.search(r"\b(D?VOR(?:/DME)?|NDB(?:/DME)?|DME)\b", prev_ln))
        m_name = re.match(r"^\s*([A-Z\s\'-]{3,25})\b", prev_ln)
        name = m_name.group(1).strip() if m_name else ident
        t = m_type.group(1) if m_type else ("VOR/DME" if float(m_freq.group(1)) > 100 else "NDB")
        lat = common.lat_of(la)
        lon = common.lon_of(lo)
        navaids.append({
            "ident": ident,
            "name": name,
            "type": t,
            "frequency": float(m_freq.group(1)),
            "frequency_unit": m_freq.group(2).upper(),
            "raw_frequency": m_freq.group(0),
            "lat": lat,
            "lon": lon,
            "raw_coord": f"{la.group(0)} {lo.group(0)}"
        })
    return navaids


def parse_waypoints_pdf(txt):
    """Parse ENR 4.4 single-line waypoints."""
    wpts = []
    for ln in txt.splitlines():
        c = common.LATLON.search(ln)
        if not c:
            continue
        before = ln[:c.start()].strip()
        m_name = re.match(r"^\s*([A-Z]{5})\b", before)
        if not m_name:
            continue
        name = m_name.group(1)
        after = ln[c.end():].strip()
        lat, lon = common.latlon_of(c)
        wpts.append({
            "ident": name,
            "lat": lat,
            "lon": lon,
            "raw_coord": c.group(0),
            "routes": after
        })
    return wpts


def parse_routes_pdf(txt):
    """Parse ENR 3.1 & 3.2 routes from Libyan PDFs."""
    txt = re.sub(r"([NS])\s*([EW])(\d{6,7}(?:\.\d+)?)", r"\1 \3\2", txt)
    lines = txt.splitlines()
    routes = []
    cur = None

    for i, ln in enumerate(lines):
        m_desig = re.match(r"^\s*([A-Z]\d{1,4}[A-Z]?)\s*$", ln)
        if m_desig:
            desig = m_desig.group(1)
            cur = {"designator": desig, "points": []}
            routes.append(cur)
            continue
        if cur is None:
            continue
        c = common.LATLON.search(ln)
        if not c:
            continue
        name = None
        ident = None
        for k in range(i - 1, max(-1, i - 5), -1):
            prev = lines[k]
            m_nav = re.search(r"\b(?:VOR(?:/DME)?|NDB)\s+([A-Z]{2,4})\b", prev)
            if m_nav and not ident:
                ident = m_nav.group(1)
            m_pt = re.search(r"[\uf070\uf072▲🔺△]\s*([A-Z0-9\'-]{3,20})\b", prev)
            if m_pt:
                name = m_pt.group(1)
                break
            m_wpt = re.match(r"^\s*([A-Z]{5})\b", prev)
            if m_wpt and not name:
                name = m_wpt.group(1)
                break
        if not name and ident:
            name = ident
        if not name:
            continue
        lat, lon = common.latlon_of(c)
        cur["points"].append({
            "name": name,
            "ident": ident,
            "lat": lat,
            "lon": lon,
            "raw_coord": c.group(0)
        })
    return [r for r in routes if len(r["points"]) >= 2]


def scrape(log):
    col = Collection(SOURCE, EFF_DATE, AMDT_ID, PAGE)

    # 1. Navaids (ENR 4.1)
    log("Fetching ENR 4.1 navaids...")
    for pid in [71, 72]:
        url = f"{BASE}ais/ENR/DownloadPDF?pdfId={pid}"
        txt = common.pdf_text(url)
        for n in parse_navaids_pdf(txt):
            col.add_navaid(n, f"ENR 4.1-{pid-70}", url)

    # 2. Waypoints (ENR 4.4)
    log("Fetching ENR 4.4 waypoints...")
    for pid in [75, 76, 77, 78]:
        url = f"{BASE}ais/ENR/DownloadPDF?pdfId={pid}"
        txt = common.pdf_text(url)
        for w in parse_waypoints_pdf(txt):
            col.add_waypoint(w, f"ENR 4.4-{pid-74}", url, routes=w.get("routes"))

    # 3. Routes (ENR 3.1 & 3.2)
    log("Fetching ENR 3.1 & 3.2 routes...")
    all_routes = []
    for pid in range(36, 71):
        url = f"{BASE}ais/ENR/DownloadPDF?pdfId={pid}"
        try:
            txt = common.pdf_text(url)
            all_routes.extend(parse_routes_pdf(txt))
        except Exception:
            pass

    def point_key(p):
        ident = p.get("ident")
        if ident:
            cand = [k for k in col.features if k == f"NAV/{ident}" or k.startswith(f"NAV/{ident}/")]
            if cand:
                return cand[0]
            return f"NAV/{ident}"
        name = p["name"].strip()
        cand = [k for k in col.features if k == f"NAV/{name}" or k.startswith(f"NAV/{name}/")]
        if cand:
            return cand[0]
        m_wpt = re.match(r"^([A-Z]{5})\b", name)
        if m_wpt:
            return f"WPT/{m_wpt.group(1)}"
        w = name.split()[0]
        if re.fullmatch(r"[A-Z]{2,6}", w):
            return f"WPT/{w}"
        return None

    # Harvest route points missing from ENR 4.4
    col.add_waypoints_from_routes(all_routes, "ENR 3", f"{BASE}ais/ENR/DownloadPDF?pdfId=36", point_key)

    for r in all_routes:
        col.add_route(r, "ENR 3", f"{BASE}ais/ENR/DownloadPDF?pdfId=36", point_key)

    # 4. Aerodromes (AD 2 & AD 3)
    log("Fetching AD aerodromes...")
    for icao, pid in AD_LIST:
        url = f"{BASE}ais/AD/DownloadPDF?pdfId={pid}"
        data = common.fetch(url)
        txt = common.pdf_bytes_text(data, icao)
        if len(txt.strip()) < 50:
            txt = ocr_ad_pdf(data, icao)
        ad = parsers.parse_aerodrome(txt, icao)
        if not ad:
            continue
        if not ad.get("name"):
            m = re.search(r"AD\s*[23]\.1[^\n]*\n\s*([A-Z][^\n]{2,80})", txt)
            if m:
                ad["name"] = m.group(1).strip()
        col.add_aerodrome(ad, icao, url)

    return col
