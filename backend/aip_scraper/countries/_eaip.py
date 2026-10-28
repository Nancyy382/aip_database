"""Shared scraper for standard Eurocontrol-style HTML eAIPs.

Most eAIP products (Bahrain, Oman, ...) publish one HTML page per section,
named "<PREFIX>-<SECTION>-<lang>.html" (e.g. "OB-ENR-4.4-en-BH.html") and listed
in "<PREFIX>-menu-<lang>.html". This reads ENR 3 (routes), ENR 4.1 (navaids),
ENR 4.4 (significant points) and every AD 2 aerodrome page.
"""
import re
from urllib.parse import urljoin

from ..common import fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..parsers import point_key

NAV_TYPE = re.compile(r"\b(VOR[/-]TACAN|D?VOR[/-]DME|VORTAC|D?VOR|NDB[/-]DME|NDB|DME|TACAN)\b")


def scrape_eaip(col, eaip, prefix, lang, log):
    """Fill `col` from the eAIP whose section pages live under the `eaip` URL (ending in "/")."""
    pre = f"{prefix}-" if prefix else ""  # some products (Oman) use no prefix: "ENR-4.4-en-GB.html"
    menu_url = f"{eaip}{pre}menu-{lang}.html"
    menu = fetch_text(menu_url)
    # resolve each section from the menu's own links: some products (Oman) keep pages in
    # another issue folder ("../../../2026-09-03-Non-AIRAC/html/eAIP/ENR-4.1-en-GB.html")
    links = {}
    for href in re.findall(r"href=[\"']([^\"'#]+)", menu):
        m = re.search(rf"(?:^|/){pre}((?:ENR|AD)-[\w.-]+?)-{lang}\.html$", href)
        if m:
            links.setdefault(m.group(1), urljoin(menu_url, href))
    sections = set(links) | set(re.findall(rf"(?<![\w-]){pre}((?:ENR|AD)-[\w.-]+?)-{lang}\.html", menu))
    url = lambda name: links.get(name) or f"{eaip}{pre}{name}-{lang}.html"

    def get(name):
        """A section page, or "" (with an issue) when the menu links a page the server lacks."""
        try:
            return fetch_text(url(name))
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", name, name.replace("-", " "), f"{url(name)}: {e}")
            return ""

    # ENR 4.4 significant points: name | coordinates | routes | remarks
    for name in sorted(s for s in sections if s.startswith("ENR-4.4") or s in ("ENR-4.3",)):
        col.documents += 1
        for r in rows(get(name)):
            c = coord(" ".join(r[1:3])) if len(r) > 1 else None
            if c and re.fullmatch(r"[A-Z]{5}", r[0]):
                col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                                  "usage": r[2] if len(r) > 2 else None}, name.replace("-", " "), url(name))

    # ENR 4.1 navaids: "NAME TYPE (VAR)" | ID | FREQ | hours | coordinates | ...
    if "ENR-4.1" in sections:
        col.documents += 1
        for r in rows(get("ENR-4.1")):
            ci = next((i for i, x in enumerate(r) if coord(x)), None)
            t = NAV_TYPE.search(r[0]) or (NAV_TYPE.search(r[1]) if len(r) > 1 else None)
            ident = next((x for x in r[1:ci] if re.fullmatch(r"[A-Z]{2,4}", x) and not NAV_TYPE.fullmatch(x)), None) if ci else None
            if not (t and ident):
                continue
            c = coord(r[ci])
            f = re.search(r"(\d{3,4}(?:\.\d+)?)\s*(MHZ|KHZ)", " ".join(r[1:ci]), re.I)
            name = r[0][:t.start()].strip() if NAV_TYPE.search(r[0]) else r[0].strip()
            col.add_navaid({"ident": ident, "type": t.group(1).replace("-", "/"), "name": name or None,
                            "frequency": float(f.group(1)) if f else None,
                            "frequency_unit": f.group(2).upper() if f else None,
                            "raw_frequency": f.group(0) if f else None,
                            "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", url("ENR-4.1"))

    for name in sorted(s for s in sections if re.fullmatch(r"ENR-3\.[1-3]", s)):
        col.documents += 1
        for r in parse_routes(text(get(name))):
            col.add_route(r, name.replace("-", " "), url(name), lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)

    # aerodrome pages: "AD-2.OBBI" (most products) or "AD-2-OTHH" (Qatar)
    ad_pages = {m.group(1): s for s in sections for m in [re.fullmatch(r"AD-2[.-]([A-Z]{4})", s)] if m}
    icaos = sorted(ad_pages)
    for icao in icaos:
        col.documents += 1
        rec = parse_ad2(get(ad_pages[icao]), icao)
        if rec:
            col.add_aerodrome(rec, "AD 2", url(ad_pages[icao]))
    log(f"  eAIP {prefix or '(no prefix)'}: {len(icaos)} aerodromes")
    return col
