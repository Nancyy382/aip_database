"""Algeria - SIA ENNA (https://www.sia-enna.dz/).

AIP documents are published as PDFs on the official portal:
- ENR 4.1: Radio navigation aids en-route
- ENR 4.4: Significant points (vector PDF, OCR applied)
- ENR 3.1 & 3.2: ATS routes
- AD 2: 33 aerodrome PDFs under PDF/AIP/AD/AD2/<ICAO>/<ICAO>.pdf
"""
import os
import re
import subprocess
import tempfile

from .. import common, parsers
from ..features import Collection

PAGE = "https://www.sia-enna.dz/aeronautical-information-publication.html"
BASE = "https://www.sia-enna.dz/"
SOURCE = "AIP Algeria (SIA ENNA)"
EFF_DATE = "2026-09-03"
AMDT_ID = "AIRAC AMDT 03/26"


def ocr_pdf(pdf_bytes):
    """Run pdftoppm + tesseract on vector or scanned PDF bytes."""
    with tempfile.TemporaryDirectory() as td:
        pdf_path = os.path.join(td, "doc.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        subprocess.run(["pdftoppm", "-png", "-r", "150", pdf_path, os.path.join(td, "pg")],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        imgs = sorted([os.path.join(td, fn) for fn in os.listdir(td) if fn.endswith(".png")])
        pages = []
        for img in imgs:
            txt = subprocess.check_output(["tesseract", img, "stdout"],
                                          stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
            # Replace common OCR misreads in coordinates
            txt = re.sub(r"(\d)\s*€", r"\1 E", txt)
            pages.append(txt)
        return common.normalize_coords("\f".join(pages))


def parse_navaids(txt):
    """Parse ENR 4.1 navaids table."""
    lines = txt.splitlines()
    navaids = []
    for ln in lines:
        c = common.LATLON.search(ln)
        if not c:
            continue
        m_type = re.search(r"\b(DVOR/DME|VOR/DME|DVOR|VOR|NDB/DME|NDB|DME)\b", ln)
        if not m_type:
            continue
        name = ln[:m_type.start()].strip()
        after_type = ln[m_type.end():c.start()]
        m_id = re.search(r"\b([A-Z]{2,4})\b", after_type)
        if not m_id:
            continue
        ident = m_id.group(1)
        m_freq = re.search(r"(\d{2,4}(?:\.\d+)?)\s*(MHZ|KHZ)?\b", after_type, re.I)
        lat, lon = common.latlon_of(c)
        freq_val = float(m_freq.group(1)) if m_freq else None
        unit = None
        if m_freq:
            if m_freq.group(2):
                unit = m_freq.group(2).upper()
            else:
                unit = "KHZ" if "NDB" in m_type.group(1) else "MHZ"
        navaids.append({
            "ident": ident,
            "name": name,
            "type": m_type.group(1),
            "frequency": freq_val,
            "frequency_unit": unit,
            "raw_frequency": m_freq.group(0).strip() if m_freq else None,
            "lat": lat,
            "lon": lon,
            "raw_coord": c.group(0).strip()
        })
    return navaids


def parse_routes(txt, route_class):
    """Parse ENR 3.1 or 3.2 route text."""
    txt = re.sub(r"[←-⯿-▲🔺△]", " ", txt)
    routes = []
    cur = None
    for ln in txt.splitlines():
        m_desig = re.match(r"^\s*([A-Z]{1,2}(?:/[A-Z]{1,2})?\s*\d{1,4}[A-Z]?)\s*$", ln)
        if m_desig:
            desig = re.sub(r"\s+", "", m_desig.group(1))
            if re.search(r"\d", desig):
                cur = {"designator": desig, "route_class": route_class, "points": []}
                routes.append(cur)
                continue
        if cur is None:
            continue
        c = common.LATLON.search(ln)
        if not c:
            continue
        before = ln[:c.start()].strip()
        before = re.sub(r"^[^A-Za-z0-9]+", "", before).strip()
        if not before:
            continue
        m_name = re.match(r"^([A-Z0-9]{2,10}(?:\s+(?:D?VOR(?:/DME)?|NDB|DME))?)\b", before)
        p_name = m_name.group(1) if m_name else before.split()[0]
        lat, lon = common.latlon_of(c)
        cur["points"].append({"name": p_name, "lat": lat, "lon": lon, "raw_coord": c.group(0).strip()})
    return [r for r in routes if len(r["points"]) >= 2]


def scrape(log):
    col = Collection(SOURCE, EFF_DATE, AMDT_ID, PAGE)

    # 1. Navaids (ENR 4.1)
    url_enr41 = BASE + "PDF/AIP/ENR/ENR4/ENR4.1.pdf"
    log("Fetching ENR 4.1 navaids...")
    txt_enr41 = common.pdf_text(url_enr41)
    navaids = parse_navaids(txt_enr41)
    for n in navaids:
        col.add_navaid(n, "ENR 4.1", url_enr41)

    # 2. Waypoints from ENR 4.4 (OCR)
    url_enr44 = BASE + "PDF/AIP/ENR/ENR4/ENR4.4.pdf"
    log("Fetching ENR 4.4 waypoints via OCR...")
    pdf_bytes_enr44 = common.fetch(url_enr44)
    ocr_enr44 = ocr_pdf(pdf_bytes_enr44)
    for ln in ocr_enr44.splitlines():
        m_desig = re.match(r"^\s*([A-Z]{5})\b", ln)
        if not m_desig:
            continue
        name = m_desig.group(1)
        c = common.LATLON.search(ln)
        if not c:
            c = re.search(r"(\d{2,6}(?:[\.,]\d+)?\s*[NS]\s*\d{3,7}(?:[\.,]\d+)?\s*[EW])", ln)
        if c:
            try:
                c_str = c.group(0).replace(",", ".")
                m_c = common.LATLON.search(c_str)
                if m_c:
                    lat, lon = common.latlon_of(m_c)
                    col.add_waypoint({"ident": name, "lat": lat, "lon": lon, "raw_coord": c.group(0).strip()},
                                     "ENR 4.4", url_enr44)
            except Exception:
                pass

    # 3. Routes (ENR 3.1 & 3.2)
    url_enr31 = BASE + "PDF/AIP/ENR/ENR3/ENR3.1.pdf"
    url_enr32 = BASE + "PDF/AIP/ENR/ENR3/ENR3.2.pdf"
    log("Fetching ENR 3.1 & 3.2 routes...")
    r31 = parse_routes(common.pdf_text(url_enr31), "ENR 3.1")
    r32 = parse_routes(common.pdf_text(url_enr32), "ENR 3.2")
    all_routes = r31 + r32

    def point_key(p):
        name = p["name"].strip()
        m_nav = re.search(r"\b([A-Z]{2,4})\s*(?:D?VOR(?:/DME)?|NDB(?:/DME)?|DME)\b", name)
        if m_nav:
            ident = m_nav.group(1)
            cand = [k for k in col.features if k == f"NAV/{ident}" or k.startswith(f"NAV/{ident}/")]
            if cand:
                return cand[0]
            return f"NAV/{ident}"
        # Direct ident match in existing navaids
        cand = [k for k in col.features if k == f"NAV/{name}" or k.startswith(f"NAV/{name}/")]
        if cand:
            return cand[0]
        # 5LNC waypoint
        m_wpt = re.match(r"^([A-Z]{5})\b", name)
        if m_wpt:
            return f"WPT/{m_wpt.group(1)}"
        w = name.split()[0]
        if re.fullmatch(r"[A-Z]{2,6}", w):
            return f"WPT/{w}"
        return None

    # Harvest route points missing from ENR 4.4
    col.add_waypoints_from_routes(all_routes, "ENR 3", url_enr31, point_key)

    # Emit routes
    for r in all_routes:
        col.add_route(r, r["route_class"], url_enr31 if r["route_class"] == "ENR 3.1" else url_enr32, point_key)

    # 4. Aerodromes (AD 2)
    log("Fetching AD 2 aerodromes...")
    html = common.fetch_text(PAGE)
    ad_links = sorted(set(re.findall(r'href=[\'"](PDF/AIP/AD/AD2/([A-Z]{4})/\2\.pdf)[\'"]', html)))
    for href, icao in ad_links:
        url = BASE + href
        raw_bytes = common.fetch(url)
        txt = common.pdf_bytes_text(raw_bytes, url)
        if len(txt.strip()) < 50:
            txt = ocr_pdf(raw_bytes)
        ad = parsers.parse_aerodrome(txt, icao)
        if not ad:
            continue
        if not ad.get("name"):
            m = re.search(r"AD\s*2\.1[^\n]*\n\s*([A-Z][^\n]{2,80})", txt)
            if m:
                ad["name"] = m.group(1).strip()
        col.add_aerodrome(ad, icao, url)

    return col
