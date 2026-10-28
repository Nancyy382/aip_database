"""AIP Romania (ROMATSA) scraper.

Romania publishes a PDF-based AIP accessible via:
https://www.aisro.ro/aip/aip.php -> <issue>/index.html
TOCs are in:
<issue>/html/en/aip_toc_enr.html
<issue>/html/en/aip_toc_ad.html
PDFs are under <issue>/DOCS/AIP/
"""
import re
from urllib.parse import urljoin

from ..common import clean, fetch_text, pdf_text
from ..features import Collection
from ..parsers import (
    LAT,
    LON,
    lat_of,
    lon_of,
    parse_aerodrome,
    parse_routes,
    parse_waypoints,
    point_key,
)

AIP_BASE = "https://www.aisro.ro/aip/"
NAV_TYPES = re.compile(r"\b(DVOR/DME|VOR/DME|VORTAC|DVOR|VOR|NDB/DME|NDB|DME|TACAN)\b")


def current_issue():
    html = fetch_text(urljoin(AIP_BASE, "aip.php"))
    matches = re.findall(r"href=[\'\"](\d{4}-\d{2}-\d{2})/index\.html[\'\"]", html)
    candidates = [m for m in matches if m <= "2026-10-27"]
    candidates.sort(reverse=True)
    eff_date = candidates[0] if candidates else "2026-10-01"
    issue_base = urljoin(AIP_BASE, f"{eff_date}/")
    # Read config.js for amendment id
    amdt = "AIRAC AMDT 10/2026"
    try:
        cfg = fetch_text(urljoin(issue_base, "config.js"))
        m = re.search(r'\[\s*"LR_Amdt_A_(\d{4})_(\d+)_en\.pdf"', cfg)
        if m:
            amdt = f"AIRAC AMDT {m.group(2)}/{m.group(1)}"
    except Exception:
        pass
    return eff_date, amdt, issue_base


def _parse_romania_navaids(txt):
    lines = [ln.rstrip() for ln in txt.splitlines()]
    navaids = []
    for i, ln in enumerate(lines):
        m = re.match(
            r"^([A-ZĂÂÎŞŢ \(\)\.\x27/-]{3,25})\s{2,}([A-Z]{2,4})\s{2,}(\d+[\d\.\s]*(?:MHz|KHz|mhz|khz)?)\s+.*?(H24|HJ|HX)?\s+(\d{6}N)",
            ln,
        )
        if not m:
            m = re.match(
                r"^([A-ZĂÂÎŞŢ \(\)\.\x27/-]{3,25})\s{2,}([A-Z]{2,4})\s{2,}(\d+[\d\.\s]*(?:MHz|KHz|mhz|khz)?)\s+(\d{6}N)",
                ln,
            )
        if m:
            name = clean(m.group(1))
            ident = m.group(2)
            raw_freq = clean(m.group(3))
            lat_str = m.group(len(m.groups()))

            ntype = None
            lon_str = None
            for j in (i + 1, i + 2):
                if j < len(lines):
                    if not ntype:
                        tm = NAV_TYPES.search(lines[j])
                        if tm:
                            ntype = tm.group(1)
                    lm = re.search(r"(\d{7}E)", lines[j])
                    if lm and not lon_str:
                        lon_str = lm.group(1)

            if lat_str and lon_str:
                cla = LAT.search(lat_str)
                clo = LON.search(lon_str)
                lat = lat_of(cla)
                lon = lon_of(clo)
                raw_c = f"{lat_str} {lon_str}"

                fm = re.search(r"(\d+(?:\.\d+)?)\s*(MHz|KHz)?", raw_freq, re.I)
                freq = float(fm.group(1)) if fm else None
                unit = (
                    fm.group(2).upper()
                    if (fm and fm.group(2))
                    else ("MHZ" if freq and freq > 50 else "KHZ")
                )

                navaids.append(
                    {
                        "ident": ident,
                        "type": ntype or "VOR",
                        "name": name,
                        "frequency": freq,
                        "frequency_unit": unit,
                        "raw_frequency": raw_freq,
                        "lat": lat,
                        "lon": lon,
                        "raw_coord": raw_c,
                    }
                )
    return navaids


def scrape(log):
    eff_date, amdt, issue_base = current_issue()
    html_base = urljoin(issue_base, "html/en/")
    index_url = urljoin(issue_base, "index.html")

    col = Collection(
        source="AIP Romania (ROMATSA)",
        effective_date=eff_date,
        amendment_id=amdt,
        source_url=index_url,
    )

    # 1. ENR 4.4 Waypoints
    u_44 = urljoin(html_base, "../../DOCS/AIP/ENR/ENR4/LR_ENR_4_4_en.pdf")
    try:
        t_44 = pdf_text(u_44)
        col.documents += 1
        for pt in parse_waypoints(t_44):
            col.add_waypoint(pt, "ENR 4.4", u_44)
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.4", "ENR 4.4", f"{u_44}: {e}")

    # 2. ENR 4.1 Navaids
    u_41 = urljoin(html_base, "../../DOCS/AIP/ENR/ENR4/LR_ENR_4_1_en.pdf")
    try:
        t_41 = pdf_text(u_41)
        col.documents += 1
        for nav in _parse_romania_navaids(t_41):
            col.add_navaid(nav, "ENR 4.1", u_41)
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.1", "ENR 4.1", f"{u_41}: {e}")

    # 3. ENR 3 Routes
    for sec, rel in [
        ("ENR 3.1", "../../DOCS/AIP/ENR/ENR3/LR_ENR_3_1_en.pdf"),
        ("ENR 3.2", "../../DOCS/AIP/ENR/ENR3/LR_ENR_3_2_en.pdf"),
        ("ENR 3.3", "../../DOCS/AIP/ENR/ENR3/LR_ENR_3_3_en.pdf"),
    ]:
        u_rte = urljoin(html_base, rel)
        try:
            t_rte = pdf_text(u_rte)
            col.documents += 1
            for r in parse_routes(t_rte):
                col.add_route(
                    r,
                    sec,
                    u_rte,
                    lambda p: point_key(p["name"]),
                    nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None,
                )
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", sec, sec, f"{u_rte}: {e}")

    # 4. AD 2 Aerodromes
    toc_ad_url = urljoin(html_base, "aip_toc_ad.html")
    try:
        html_toc_ad = fetch_text(toc_ad_url)
        ad2_files = set(
            re.findall(r"(\.\./\.\./DOCS/AIP/AD/AD2/[^\x22\x27]+\.pdf)", html_toc_ad)
        )
        main_ad2 = [f for f in ad2_files if re.search(r"LR_AD_2_([A-Z]{4})_en\.pdf$", f)]
        for f in sorted(main_ad2):
            m_icao = re.search(r"LR_AD_2_([A-Z]{4})_en\.pdf$", f)
            icao = m_icao.group(1)
            u_ad = urljoin(html_base, f)
            try:
                t_ad = pdf_text(u_ad)
                col.documents += 1
                rec = parse_aerodrome(t_ad, icao)
                if rec:
                    col.add_aerodrome(rec, f"{icao} AD 2", u_ad)
            except Exception as e:
                col.issue(
                    "warning", "RULE_SOURCE_UNAVAILABLE", f"{icao} AD 2", f"{icao} AD 2", f"{u_ad}: {e}"
                )
    except Exception as e:
        col.issue(
            "warning", "RULE_SOURCE_UNAVAILABLE", "AD 2 TOC", "AD 2 TOC", f"{toc_ad_url}: {e}"
        )

    log(f"  Romania: {len(col.features)} features ({col.documents} docs)")
    return col

