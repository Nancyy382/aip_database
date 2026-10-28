"""AIP Poland (PANSA) eAIP scraper.

PANSA publishes an IDS AirNav eAIP. Issue index is at:
https://docs.pansa.pl/ais/eaipifr/default_offline_2026-10-01.html
Content metadata and navigation is in:
<issue_base>/v2/js/datasource.js
Sections live in:
<issue_base>/eAIP/
"""
import json
import re
from urllib.parse import quote, urljoin

from ..common import fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

INDEX_URL = "https://docs.pansa.pl/ais/eaipifr/default_offline_2026-10-01.html"

NAV_TYPE = re.compile(r"\b(VOR[/-]TACAN|D?VOR[/-]DME|VORTAC|D?VOR|NDB[/-]DME|NDB|DME|TACAN)\b")


def current_issue():
    html = fetch_text(INDEX_URL)
    matches = re.findall(r"href=[\'\"]([^\"\']+index-v2\.html)[\'\"]", html)
    candidates = []
    for m in matches:
        m_norm = m.replace("\\", "/")
        dm = re.search(r"(\d{4})_(\d{2})_(\d{2})", m_norm)
        am = re.search(r"AIRAC\s+AMDT\s+([0-9-]+)", m_norm)
        if dm:
            dt = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
            if dt <= "2026-10-27":
                candidates.append((dt, am.group(0) if am else "AIRAC AMDT", m_norm))
    candidates.sort(reverse=True)
    if not candidates:
        return "2026-10-01", "AIRAC AMDT 10-26", "AIRAC AMDT 10-26_2026_10_01/index-v2.html"
    return candidates[0]


def scrape(log):
    eff_date, amdt, rel_idx = current_issue()
    issue_folder = rel_idx.rsplit("/", 1)[0]
    base_url = urljoin(INDEX_URL, quote(issue_folder) + "/")
    eaip_base = urljoin(base_url, "eAIP/")
    js_url = urljoin(base_url, "v2/js/datasource.js")

    col = Collection(
        source="eAIP Poland (PANSA)",
        effective_date=eff_date,
        amendment_id=amdt.replace("-", "/"),
        source_url=INDEX_URL,
    )

    js = fetch_text(js_url)
    m = re.search(r"const\s+DATASOURCE\s*=\s*(\{.*\});?\s*$", js, re.DOTALL)
    if not m:
        log("  Failed to find DATASOURCE in datasource.js")
        return col
    raw = m.group(1).strip()
    if raw.endswith(";"):
        raw = raw[:-1].strip()
    raw = re.sub(r",\s*([\]}])", r"\1", raw)
    data = json.loads(raw, strict=False)
    menu = data["tabs"][0]["contents"]["en-GB"]["menu"]

    pages = {}

    def walk(items):
        for it in items:
            t = it.get("title", "")
            h = it.get("href", "")
            if h and not h.startswith("javascript"):
                p = h.split("#")[0]
                if p and p not in pages:
                    pages[p] = t
            walk(it.get("children", []))

    walk(menu)

    # 1. ENR 4.4 Waypoints
    enr_44_pages = [p for p in pages if p.startswith("ENR 4.4")]
    for p in enr_44_pages:
        u = urljoin(eaip_base, quote(p))
        try:
            html = fetch_text(u)
            col.documents += 1
            for r in rows(html):
                c = coord(r[1]) if len(r) > 1 else None
                if not c and len(r) > 2:
                    c = coord(" ".join(r[1:3]))
                if c and re.fullmatch(r"[A-Z]{5}", r[0].strip()):
                    ident = r[0].strip()
                    usage = r[2].strip() if len(r) > 2 else None
                    col.add_waypoint(
                        {"ident": ident, "lat": c[0], "lon": c[1], "raw_coord": c[2], "usage": usage},
                        "ENR 4.4",
                        u,
                    )
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", p, "ENR 4.4", f"{u}: {e}")

    # 2. ENR 4.1 Navaids
    enr_41_pages = [p for p in pages if p.startswith("ENR 4.1")]
    for p in enr_41_pages:
        u = urljoin(eaip_base, quote(p))
        try:
            html = fetch_text(u)
            col.documents += 1
            for r in rows(html):
                ci = next((i for i, x in enumerate(r) if coord(x)), None)
                if not ci:
                    continue
                t = NAV_TYPE.search(r[1]) if len(r) > 1 else None
                if not t and len(r) > 0:
                    t = NAV_TYPE.search(r[0])
                ident = next(
                    (
                        x.strip()
                        for x in r[1:ci]
                        if re.fullmatch(r"[A-Z]{2,4}", x.strip()) and not NAV_TYPE.fullmatch(x.strip())
                    ),
                    None,
                )
                if not (t and ident):
                    continue
                c = coord(r[ci])
                f = re.search(r"(\d{3,4}(?:\.\d+)?)\s*(MHZ|KHZ)", " ".join(r[1:ci]), re.I)
                name = r[0][: t.start()].strip() if t and NAV_TYPE.search(r[0]) else r[0].strip()
                col.add_navaid(
                    {
                        "ident": ident,
                        "type": t.group(1).replace("-", "/"),
                        "name": name or None,
                        "frequency": float(f.group(1)) if f else None,
                        "frequency_unit": f.group(2).upper() if f else None,
                        "raw_frequency": f.group(0) if f else None,
                        "lat": c[0],
                        "lon": c[1],
                        "raw_coord": c[2],
                    },
                    "ENR 4.1",
                    u,
                )
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", p, "ENR 4.1", f"{u}: {e}")

    # 3. ENR 3 Routes
    enr_3_pages = [p for p in pages if p.startswith("ENR 3")]
    for p in enr_3_pages:
        u = urljoin(eaip_base, quote(p))
        try:
            html = fetch_text(u)
            col.documents += 1
            t = text(html)
            for r in parse_routes(t):
                col.add_route(
                    r,
                    p.split("-")[0].strip(),
                    u,
                    lambda pt: point_key(pt["name"]),
                    nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None,
                )
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", p, "ENR 3", f"{u}: {e}")

    # 4. AD 2 Aerodromes
    ad_1_pages = {}
    for p in pages:
        m_ad = re.match(r"AD 2\s+([A-Z]{4})\s+1-en-GB\.html", p)
        if m_ad:
            ad_1_pages[m_ad.group(1)] = p

    for icao, p in sorted(ad_1_pages.items()):
        u = urljoin(eaip_base, quote(p))
        try:
            html = fetch_text(u)
            col.documents += 1
            rec = parse_ad2(html, icao)
            if rec:
                col.add_aerodrome(rec, f"{icao} AD 2", u)
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", p, f"{icao} AD 2", f"{u}: {e}")

    log(f"  Poland: {len(col.features)} features ({col.documents} docs)")
    return col
