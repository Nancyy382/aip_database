"""AIP Spain (Balearic Is. - Canary Is.) (ENAIRE) scraper.

Spain publishes its official AIP in HTML and PDF formats via ENAIRE:
https://aip.enaire.es/aip/
"""
import datetime
import re
from urllib.parse import urljoin

from ..common import clean, fetch_text
from ..eaip_html import coord, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

INDEX_URL = "https://aip.enaire.es/aip/"
NAV_TYPES = re.compile(
    r"\b(DVOR/DME|VOR/DME|VORTAC|DVOR|VOR|NDB/DME|NDB|DME|TACAN|LOC|ILS|L)\b"
)


def current_issue():
    html = fetch_text(INDEX_URL)
    m_amdt = re.search(r"LE_Amdt_A_(\d{4})_(\d+)_", html)
    amdt = f"AIRAC AMDT {m_amdt.group(2)}/{m_amdt.group(1)}" if m_amdt else "AIRAC AMDT 09/2026"

    m_date = re.search(r"(\d{2})-([A-Z]{3})-(\d{2,4})", html)
    eff_date = "2026-10-01"
    if m_date:
        d_str = m_date.group(0)
        try:
            dt = datetime.datetime.strptime(d_str, "%d-%b-%y").strftime("%Y-%m-%d")
            if dt <= "2026-10-28":
                eff_date = dt
        except Exception:
            pass

    return eff_date, amdt


def _parse_spain_aerodrome(html, icao):
    # 1. Aerodrome Name
    m_name = re.search(rf"\b{icao}\s*-\s*([^\n<]+)", html)
    name = clean(m_name.group(1)) if m_name else icao

    # 2. ARP coordinates & Elevation
    m_arp = re.search(
        r"<td>\s*<p[^>]*>\s*ARP\s*</p>\s*</td>\s*<td>\s*<p[^>]*>([0-9NSWE\s\.]+)",
        html,
        re.I,
    )
    arp = coord(m_arp.group(1)) if m_arp else None
    if not arp:
        return None

    m_elev = re.search(
        r"<td>\s*<p[^>]*>\s*Elevaci[óo]n\s*</p>\s*</td>\s*<td>\s*<p[^>]*>.*?(?:/\s*(\d+)\s*ft|\b(\d+)\s*FT)",
        html,
        re.I,
    )
    elev = int(m_elev.group(1) or m_elev.group(2)) if m_elev else None

    # 3. Runways
    tbl_m = re.search(
        r"<table[^>]*tablepistas[^>]*>.*?<tbody>(.*?)</tbody>", html, re.S | re.I
    )
    ends = []
    if tbl_m:
        for tr in re.findall(r"<tr\b.*?</tr>", tbl_m.group(1), re.S | re.I):
            cells = [
                re.sub(r"<[^>]+>", " ", c).strip()
                for c in re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.S | re.I)
            ]
            if len(cells) >= 11:
                desig_m = re.match(r"^(\d{2}[LRC]?)", cells[0])
                if not desig_m:
                    continue
                desig = desig_m.group(1)

                brg_m = re.search(r"(\d+(?:\.\d+)?)[º°]\s*GEO", cells[1])
                brg = float(brg_m.group(1)) if brg_m else None

                dim_m = re.search(r"(\d+)\s*x\s*(\d+)", cells[2])
                dim = (
                    (
                        float(dim_m.group(1)),
                        float(dim_m.group(2)),
                        f"{dim_m.group(1)} x {dim_m.group(2)}",
                    )
                    if dim_m
                    else None
                )

                c = coord(cells[3])

                sfc_m = re.search(
                    r"\b(ASPH|CONC|GRASS|TURF|BITU|MAC|SAND|CLAY|DIRT)\b",
                    cells[10].upper(),
                )
                sfc = sfc_m.group(1) if sfc_m else "ASPH"

                ends.append(
                    {
                        "designator": desig,
                        "bearing": brg,
                        "raw_bearing": f"{brg}°" if brg else None,
                        "lat": c[0] if c else None,
                        "lon": c[1] if c else None,
                        "raw_coord": c[2] if c else None,
                        "dims": dim,
                        "surface": sfc,
                    }
                )

    pairs, used = [], set()
    for i, a in enumerate(ends):
        if i in used:
            continue
        used.add(i)
        na = int(a["designator"][:2])
        for j in range(i + 1, len(ends)):
            if j not in used and (na + 18 - 1) % 36 + 1 == int(ends[j]["designator"][:2]):
                used.add(j)
                pairs.append([a, ends[j]])
                break
        else:
            pairs.append([a])

    runways = []
    for p in pairs:
        d = next((e["dims"] for e in p if e.get("dims")), (None, None, None))
        s = next((e["surface"] for e in p if e.get("surface")), "ASPH")
        runways.append(
            {
                "pair": "-".join(e["designator"] for e in p),
                "length": d[0],
                "width": d[1],
                "raw_dims": d[2],
                "surface": s,
                "ends": p,
            }
        )

    return {
        "icao": icao,
        "name": name,
        "lat": arp[0],
        "lon": arp[1],
        "raw_coord": arp[2],
        "elevation": elev,
        "runways": runways,
    }


def scrape(log):
    eff_date, amdt = current_issue()

    col = Collection(
        source="AIP Spain (ENAIRE)",
        effective_date=eff_date,
        amendment_id=amdt,
        source_url=INDEX_URL,
    )

    # 1. ENR 4.4 Waypoints
    u_44 = urljoin(INDEX_URL, "contenido_AIP/ENR/LE_ENR_4_4_es.html")
    try:
        html_44 = fetch_text(u_44)
        col.documents += 1
        for r in rows(html_44):
            if len(r) >= 2 and re.fullmatch(r"[A-Z]{5}", r[0].strip()):
                c = coord(r[1])
                if c:
                    col.add_waypoint(
                        {
                            "ident": r[0].strip(),
                            "lat": c[0],
                            "lon": c[1],
                            "raw_coord": c[2],
                            "usage": r[3].strip() if len(r) > 3 and r[3].strip() else None,
                        },
                        "ENR 4.4",
                        u_44,
                    )
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.4", "ENR 4.4", f"{u_44}: {e}")

    # 2. ENR 4.1 Navaids
    u_41 = urljoin(INDEX_URL, "contenido_AIP/ENR/LE_ENR_4_1_es.html")
    try:
        html_41 = fetch_text(u_41)
        col.documents += 1
        for r in rows(html_41):
            if len(r) >= 5 and re.fullmatch(r"[A-Z]{2,4}", r[1].strip()):
                ident = r[1].strip()
                t_m = NAV_TYPES.search(r[0])
                ntype = t_m.group(1) if t_m else "VOR"
                name = r[0][: t_m.start()].strip() if t_m else r[0].strip()
                name = re.sub(r"\s*\([^)]*\)", "", name).strip()
                raw_freq = r[2].strip()
                c = coord(r[4])
                if c:
                    fm = re.search(r"(\d+(?:\.\d+)?)\s*(MHz|kHz|mhz|khz)?", raw_freq, re.I)
                    freq = float(fm.group(1)) if fm else None
                    unit = (
                        fm.group(2).upper()
                        if (fm and fm.group(2))
                        else ("MHZ" if freq and freq > 50 else "KHZ")
                    )
                    col.add_navaid(
                        {
                            "ident": ident,
                            "type": ntype,
                            "name": name,
                            "frequency": freq,
                            "frequency_unit": unit,
                            "raw_frequency": raw_freq,
                            "lat": c[0],
                            "lon": c[1],
                            "raw_coord": c[2],
                        },
                        "ENR 4.1",
                        u_41,
                    )
    except Exception as e:
        col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "ENR 4.1", "ENR 4.1", f"{u_41}: {e}")

    # 3. ENR 3 Routes
    for sub in ["LE_ENR_3_1_es.html", "LE_ENR_3_2_es.html", "LE_ENR_3_3_es.html"]:
        u_rte = urljoin(INDEX_URL, "contenido_AIP/ENR/" + sub)
        try:
            html_rte = fetch_text(u_rte)
            col.documents += 1
            t = text(html_rte)
            for r in parse_routes(t):
                col.add_route(
                    r,
                    sub.split("_")[2],
                    u_rte,
                    lambda p: point_key(p["name"]),
                    nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None,
                )
        except Exception:
            pass

    # 4. AD 2 Aerodromes
    index_html = fetch_text(INDEX_URL)
    html_ad2 = set(
        re.findall(
            r"href=[\'\"](contenido_AIP/AD/AD2/[A-Z_]+/LE_AD_2_[A-Z]{4}_es\.html)[\'\"]",
            index_html,
        )
    )
    for p in sorted(html_ad2):
        m_icao = re.search(r"LE_AD_2_([A-Z]{4})_es\.html$", p)
        if not m_icao:
            continue
        icao = m_icao.group(1)
        u_ad = urljoin(INDEX_URL, p)
        try:
            html_ad = fetch_text(u_ad)
            col.documents += 1
            rec = _parse_spain_aerodrome(html_ad, icao)
            if rec:
                col.add_aerodrome(rec, f"{icao} AD 2", u_ad)
        except Exception as e:
            col.issue(
                "warning",
                "RULE_SOURCE_UNAVAILABLE",
                f"{icao} AD 2",
                f"{icao} AD 2",
                f"{u_ad}: {e}",
            )

    log(f"  Spain: {len(col.features)} features ({col.documents} docs)")
    return col
