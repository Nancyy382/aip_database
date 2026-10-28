"""Iceland - Isavia eAIP (https://eaip.isavia.is/).

Dynamic lookup of the currently effective AIRAC amendment from the history page.
eAIP package uses IDS AIRNAV layout with prefix "BI", language "en-GB".
"""
from datetime import date, datetime
import re
from urllib.parse import quote, urljoin

from ..common import fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

BASE = "https://eaip.isavia.is/"
SOURCE = "eAIP Iceland (Isavia)"
NAV_TYPE = re.compile(r"\b(VOR[/-]TACAN|D?VOR[/-]DME|VORTAC|D?VOR|NDB[/-]DME|NDB|DME|TACAN)\b")


def current_issue():
    page = fetch_text(BASE)
    today = date.today()
    issues = []
    for m in re.finditer(
        r'<td[^>]*><a\s+href=[\"\']([^\"\']+)[\"\'][^>]*>\s*(\d{2}\s+[A-Z]{3}\s+\d{4})\s*</a></td>\s*<td[^>]*>[^<]*</td>\s*<td[^>]*>\s*(AIRAC\s+\d+/\d+)\s*</td>',
        page, re.I
    ):
        href, dt_str, amdt = m.group(1), m.group(2).strip(), m.group(3).strip()
        try:
            d = datetime.strptime(dt_str, "%d %b %Y").date()
        except ValueError:
            continue
        issues.append((d, amdt, href))
    issues.sort(key=lambda x: x[0])
    valid = [i for i in issues if i[0] <= today]
    return valid[-1] if valid else issues[0]


def scrape(log):
    d, amdt, issue_url = current_issue()
    log(f"  Iceland issue: {amdt} (effective {d.isoformat()}) at {issue_url}")
    col = Collection(SOURCE, d.isoformat(), amdt, issue_url)

    eaip_dir = urljoin(issue_url, "eAIP/")
    menu_url = urljoin(eaip_dir, "menu.html")
    menu = fetch_text(menu_url)
    col.documents += 1

    # ENR 4.4 waypoints
    w_url = urljoin(eaip_dir, quote("BI-ENR 4.4-en-GB.html"))
    log("  Fetching ENR 4.4 waypoints...")
    try:
        col.documents += 1
        for r in rows(fetch_text(w_url)):
            c = coord(" ".join(r[1:3])) if len(r) > 1 else None
            if c and re.fullmatch(r"[A-Z]{5}", r[0]):
                col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2],
                                  "usage": r[2] if len(r) > 2 else None}, "ENR 4.4", w_url)
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR-4.4", "ENR 4.4", str(e))

    # ENR 4.1 navaids
    n_url = urljoin(eaip_dir, quote("BI-ENR 4.1-en-GB.html"))
    log("  Fetching ENR 4.1 navaids...")
    try:
        col.documents += 1
        for r in rows(fetch_text(n_url)):
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
                            "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", n_url)
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR-4.1", "ENR 4.1", str(e))

    # ENR 3 routes
    raw_links = re.findall(r'href=[\'\"](BI-ENR 3[^\'\"]*en-GB\.html[^\'\"]*)[\'\"]', menu)
    enr3_pages = sorted(set(l.split("#")[0] for l in raw_links if not l.startswith("BI-ENR 3-") and not l == "BI-ENR 3-en-GB.html"))
    log(f"  Fetching {len(enr3_pages)} ENR 3 route pages...")
    for p in enr3_pages:
        r_url = urljoin(eaip_dir, quote(p))
        try:
            col.documents += 1
            txt = fetch_text(r_url)
            for r in parse_routes(text(txt)):
                col.add_route(r, "ENR 3", r_url, lambda pt: point_key(pt["name"]),
                              nav_spec="RNAV" if "RNAV" in p or re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", p, "ENR 3", str(e))

    # AD 2 aerodromes
    ad_pages = {}
    for m in re.finditer(r'href=[\'\"](BI-AD ([A-Z]{4})[^\'\"]* 1-en-GB\.html[^\'\"]*)[\'\"]', menu):
        href, icao = m.group(1).split('#')[0], m.group(2)
        ad_pages[icao] = href
    log(f"  Fetching {len(ad_pages)} AD 2 aerodromes...")
    for icao, href in sorted(ad_pages.items()):
        a_url = urljoin(eaip_dir, quote(href))
        col.documents += 1
        try:
            rec = parse_ad2(fetch_text(a_url), icao)
            if rec:
                col.add_aerodrome(rec, "AD 2", a_url)
            else:
                col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
        except Exception as e:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))

    log(f"  Parsed {len(col.features)} features ({len(col.issues)} issues)")
    return col

