"""Netherlands - LVNL eAIP (https://eaip.lvnl.nl/).

IDS AirNav software, prefix "EH", lang "en-GB".
"""
from datetime import date
import re
import urllib.parse

from ..common import fetch_text
from ..eaip_html import coord, parse_ad2, rows
from ..features import Collection

PAGE = "https://eaip.lvnl.nl/"
BASE = "https://eaip.lvnl.nl/"
SOURCE = "eAIP The Netherlands (LVNL)"
NAV_TYPE = re.compile(r"\b(VOR[/-]TACAN|D?VOR[/-]DME|VORTAC|D?VOR|NDB[/-]DME|NDB|DME|TACAN)\b")


def current_issue():
    html = fetch_text(PAGE)
    matches = re.findall(r"href=[\"']([^\"']*(\d{4})_(\d{2})_(\d{2})[\\/]index\.html)[\"']", html)
    issues = []
    for rel, y, m, d in matches:
        dt = date(int(y), int(m), int(d))
        issues.append((dt, rel.replace("\\", "/")))
    past = [i for i in issues if i[0] <= date.today()]
    return max(past or issues)


def scrape(log):
    eff, rel = current_issue()
    issue_folder = rel.rsplit("/", 1)[0]
    encoded_folder = urllib.parse.quote(issue_folder)
    eaip_url = f"{BASE}{encoded_folder}/eAIP/"

    m_amdt = re.search(r"(AIRAC\s+AMDT\s+[\d/-]+)", issue_folder)
    amdt_id = m_amdt.group(1) if m_amdt else f"AIRAC {eff.isoformat()}"

    col = Collection(SOURCE, eff.isoformat(), amdt_id, PAGE)

    # 1. Aerodromes
    menu = fetch_text(eaip_url + "menu.html")
    icaos = sorted(set(re.findall(r"EH-AD 2 ([A-Z]{4}) 1-en-GB\.html", menu)))
    for icao in icaos:
        ad_url = f"{eaip_url}EH-AD%202%20{icao}%201-en-GB.html"
        try:
            ad_html = fetch_text(ad_url)
            rec = parse_ad2(ad_html, icao)
            if rec:
                col.documents += 1
                col.add_aerodrome(rec, f"{icao} AD 2", ad_url)
        except Exception as e:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", f"{ad_url}: {e}")

    # 2. Waypoints (ENR 4.4)
    wpt_url = f"{eaip_url}EH-ENR%204.4-en-GB.html"
    try:
        wpt_html = fetch_text(wpt_url)
        col.documents += 1
        for r in rows(wpt_html):
            c = coord(" ".join(r[1:3])) if len(r) > 1 else None
            if c and re.fullmatch(r"[A-Z]{5}", r[0]):
                col.add_waypoint(
                    {"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2]},
                    "EH ENR 4.4",
                    wpt_url,
                )
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.4", "EH ENR 4.4", f"{wpt_url}: {e}")

    # 3. Navaids (ENR 4.1)
    nav_url = f"{eaip_url}EH-ENR%204.1-en-GB.html"
    try:
        nav_html = fetch_text(nav_url)
        col.documents += 1
        for r in rows(nav_html):
            if not r or r[0].strip() == "NIL":
                continue
            m = NAV_TYPE.search(r[0])
            c = next((coord(" ".join(r[i : i + 2])) for i in range(1, len(r)) if coord(" ".join(r[i : i + 2]))), None)
            ident = next((x for x in r[1:3] if re.fullmatch(r"[A-Z]{3}", x)), None)
            if m and c and ident:
                freq = next((x for x in r if re.search(r"\b\d{3}(?:\.\d+)?\s*(?:MHZ|KHZ)\b", x, re.I)), None)
                col.add_navaid(
                    {
                        "ident": ident,
                        "name": r[0].split("\n")[0].strip(),
                        "type": m.group(1),
                        "freq": freq,
                        "lat": c[0],
                        "lon": c[1],
                        "raw_coord": c[2],
                    },
                    "EH ENR 4.1",
                    nav_url,
                )
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.1", "EH ENR 4.1", f"{nav_url}: {e}")

    return col
