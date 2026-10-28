"""Denmark (Faeroe Islands-Greenland) - Naviair AIM (https://aim.naviair.dk/).

Naviair publishes Denmark, Faeroe Islands and Greenland via Umbraco tree-view APIs
at /umbraco/api/naviairapi/getnodesforparent?parentId=.
ENR sections and aerodromes are individual PDFs.
"""
from datetime import datetime
import re
from urllib.parse import urljoin

from ..common import fetch_json, pdf_text
from ..features import Collection
from ..parsers import (parse_aerodrome, parse_navaids_ident_first, parse_routes,
                       parse_waypoints, point_key)

BASE = "https://aim.naviair.dk"
SOURCE = "AIP Denmark, Faeroe Islands, Greenland (Naviair)"
API_URL = f"{BASE}/umbraco/api/naviairapi/getnodesforparent?parentId="


def get_nodes(pid=""):
    return fetch_json(f"{API_URL}{pid}")


def scrape(log):
    root_nodes = get_nodes("")
    regions = [r for r in root_nodes if any(k in r.get("title", "") for k in
                                           ["AIP Danmark", "AIP Færøerne", "AIP Grønland"])]

    # Determine effective date and amendment from Denmark's main AIP or AMDT folder
    dk_node = next(r for r in regions if "AIP Danmark" in r.get("title", ""))
    dk_children = get_nodes(dk_node["id"])
    aip_node = next((n for n in dk_children if n.get("title") == "AIP"), None)
    eff_date = "2026-10-01"
    amdt = "AIRAC AMDT 11/2026"
    if aip_node:
        for f in get_nodes(aip_node["id"]):
            href = f.get("href", "")
            m = re.search(r"AIRAC_AMDT_([0-9]{2}[A-Z]{3}[0-9]{4})", href)
            if m:
                eff_date = datetime.strptime(m.group(1), "%d%b%Y").date().isoformat()
                amdt = f"AIRAC AMDT 11/{eff_date[:4]}"

    col = Collection(SOURCE, eff_date, amdt, BASE)

    for region in regions:
        r_name = region.get("title", "")
        r_children = get_nodes(region["id"])

        # ENR sections
        enr_node = next((n for n in r_children if "PART 2 - EN ROUTE (ENR)" in n.get("title", "")), None)
        if enr_node:
            for sub in get_nodes(enr_node["id"]):
                sub_title = sub.get("title", "")
                if "ENR 4" in sub_title:
                    for f in get_nodes(sub["id"]):
                        title, href = f.get("title", ""), f.get("href")
                        if not (href and href.endswith(".pdf")):
                            continue
                        url = urljoin(BASE, href)
                        if "ENR 4.4" in title or "ENR_4_4" in href:
                            col.documents += 1
                            for w in parse_waypoints(pdf_text(url)):
                                col.add_waypoint(w, "ENR 4.4", url)
                        elif "ENR 4.1" in title or "ENR_4_1" in href:
                            col.documents += 1
                            for n in parse_navaids_ident_first(pdf_text(url)):
                                col.add_navaid(n, "ENR 4.1", url)
                elif "ENR 3" in sub_title:
                    for f in get_nodes(sub["id"]):
                        title, href = f.get("title", ""), f.get("href")
                        if not (href and href.endswith(".pdf")):
                            continue
                        url = urljoin(BASE, href)
                        m_sec = re.search(r"ENR\s*3\.[1-3]|ENR_3_[1-3]", title + href)
                        if m_sec:
                            col.documents += 1
                            for r in parse_routes(pdf_text(url)):
                                col.add_route(r, "ENR 3", url, lambda p: point_key(p["name"]),
                                              nav_spec="RNAV" if "3_2" in href or "3.2" in title else None)

        # AD 2 aerodromes
        ad_node = next((n for n in r_children if "PART 3 - FLYVEPLADSER (AD)" in n.get("title", "")), None)
        if ad_node:
            ad_subs = get_nodes(ad_node["id"])
            ad2_node = next((n for n in ad_subs if "AD 2" in n.get("title", "")), None)
            if ad2_node:
                airports = get_nodes(ad2_node["id"])
                log(f"  {r_name}: {len(airports)} aerodromes")
                for ap in airports:
                    ap_title = ap.get("title", "")
                    m_icao = re.search(r"\b([A-Z]{4})\b", ap_title)
                    icao = m_icao.group(1) if m_icao else None
                    files = get_nodes(ap["id"])
                    text_pdf = next((f for f in files if re.search(r"Text|AD 2\b", f.get("title", "")) and f.get("href", "").endswith(".pdf")), None)
                    if not text_pdf:
                        text_pdf = next((f for f in files if f.get("href", "").endswith(".pdf")), None)
                    if not text_pdf:
                        continue
                    url = urljoin(BASE, text_pdf["href"])
                    col.documents += 1
                    try:
                        a = parse_aerodrome(pdf_text(url), icao=icao)
                    except Exception as e:
                        col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))
                        continue
                    if a:
                        if icao:
                            a["icao"] = icao
                        col.add_aerodrome(a, "AD 2", url)
                    else:
                        col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")

    return col

