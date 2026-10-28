"""Shared scraper for the SMATSA eAIP (https://smatsa.rs/upload/aip/published/start_page.html).

Covers Serbia and Montenegro. Standard Eurocontrol eAIP with prefix "LY", lang "en-GB".
"""
from datetime import date, datetime
import math
import re

from ..common import fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

BASE = "https://smatsa.rs/upload/aip/published/"
PAGE = BASE + "start_page.html"
SOURCE = "eAIP Serbia and Montenegro (SMATSA)"
NAV_TYPE = re.compile(r"\b(VOR[/-]TACAN|D?VOR[/-]DME|VORTAC|D?VOR|NDB[/-]DME|NDB|DME|TACAN)\b")


def current_issue():
    html = fetch_text(PAGE)
    matches = re.findall(r"href=[\"'](\./[^\s\"']*/(\d{4}-\d{2}-\d{2})-AIRAC/html/index_commands\.html)[\"']", html)
    issues = []
    for rel, dt_str in matches:
        dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        issues.append((dt, BASE + rel[2:]))
    past = [i for i in issues if i[0] <= date.today()]
    return max(past or issues)


def dist(a, b):
    return math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(a[0])))


def scrape_state(state_name, state_icaos, log):
    eff, index_url = current_issue()
    eaip = index_url.rsplit("/", 1)[0] + "/eAIP/"
    menu = fetch_text(eaip + "LY-menu-en-GB.html")

    all_icaos = sorted(set(re.findall(r"LY-AD-2\.([A-Z]{4})-en-GB\.html", menu)))
    arp = {}
    for icao in all_icaos:
        rec = parse_ad2(fetch_text(f"{eaip}LY-AD-2.{icao}-en-GB.html"), icao)
        if rec:
            arp[icao] = (rec["lat"], rec["lon"])

    col = Collection(f"eAIP {state_name} (SMATSA)", eff.isoformat(), f"AIRAC {eff.isoformat()}", index_url)
    ours = lambda lat, lon: min(arp, key=lambda k: dist(arp[k], (lat, lon))) in state_icaos

    # 1. Aerodromes
    for icao in sorted(state_icaos):
        rec = parse_ad2(fetch_text(f"{eaip}LY-AD-2.{icao}-en-GB.html"), icao)
        if rec:
            col.documents += 1
            col.add_aerodrome(rec, f"{icao} AD 2", f"{eaip}LY-AD-2.{icao}-en-GB.html")

    # 2. Waypoints
    wpt_url = eaip + "LY-ENR-4.4-en-GB.html"
    try:
        wpt_html = fetch_text(wpt_url)
        col.documents += 1
        for r in rows(wpt_html):
            c = coord(" ".join(r[1:3])) if len(r) > 1 else None
            if c and re.fullmatch(r"[A-Z]{5}", r[0]) and ours(c[0], c[1]):
                col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "LY ENR 4.4", wpt_url)
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.4", "LY ENR 4.4", f"{wpt_url}: {e}")

    # 3. Navaids
    nav_url = eaip + "LY-ENR-4.1-en-GB.html"
    try:
        nav_html = fetch_text(nav_url)
        col.documents += 1
        for r in rows(nav_html):
            m_nav = NAV_TYPE.search(r[0])
            c = next((coord(" ".join(r[i : i + 2])) for i in range(1, len(r)) if coord(" ".join(r[i : i + 2]))), None)
            ident = next((x for x in r[1:3] if re.fullmatch(r"[A-Z]{3}", x)), None)
            if m_nav and c and ident and ours(c[0], c[1]):
                freq = next((x for x in r if re.search(r"\b\d{3}(?:\.\d+)?\s*(?:MHZ|KHZ)\b", x, re.I)), None)
                col.add_navaid(
                    {
                        "ident": ident,
                        "name": r[0].split("\n")[0].strip(),
                        "type": m_nav.group(1),
                        "freq": freq,
                        "lat": c[0],
                        "lon": c[1],
                        "raw_coord": c[2],
                    },
                    "LY ENR 4.1",
                    nav_url,
                )
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.1", "LY ENR 4.1", f"{nav_url}: {e}")

    # 4. Routes
    for s in ["LY-ENR-3.1-en-GB.html", "LY-ENR-3.2-en-GB.html"]:
        r_url = eaip + s
        try:
            r_html = fetch_text(r_url)
            col.documents += 1
            for rte in parse_routes(text(r_html)):
                if any(ours(p["lat"], p["lon"]) for p in rte["points"]):
                    col.add_route(rte, s.split("-")[1], r_url, lambda p: point_key(p["name"]))
        except Exception:
            pass

    return col
