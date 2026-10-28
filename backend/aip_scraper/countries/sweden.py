"""Sweden - LFV eAIP (https://aro.lfv.se/Editorial/View/IAIP).

The issue list (content/eaip/default_offline.html) links each issue as
"AIRAC AIP AMDT 6-2026_2026_10_29\\index-v2.html"; the newest one in force is used.
The viewer has no eAIP menu page: its table of contents is v2/js/datasource.js, whose
"href" entries name the section pages in eAIP/ ("ES-ENR 4.4-en-GB.html"). ENR 3 has one
page per route ("ES-ENR 3.2 L24-en-GB.html"), AD 2 several numbered pages per aerodrome
("ES-AD 2 ESGG GÖTEBORG-LANDVETTER 1-en-GB.html").
"""
import re
from datetime import date
from urllib.parse import quote

from ..common import clean, fetch_text
from ..eaip_html import coord, parse_ad2, parse_routes, rows, text
from ..features import Collection
from ..parsers import point_key

ROOT = "https://aro.lfv.se/content/eaip/"
SOURCE = "eAIP Sweden (LFV)"
NAV_TYPE = re.compile(r"\b(DVOR/DME|VOR/DME|DVOR|VOR|NDB/DME|NDB|DME|TACAN|VORTAC)\b")


def current_issue():
    issues = [(f"{y}-{m}-{d}", folder) for folder, y, m, d in
              re.findall(r'href="([^"\\]+_(\d{4})_(\d{2})_(\d{2}))\\index-v2\.html"', fetch_text(ROOT + "default_offline.html"))]
    return max([i for i in issues if i[0] <= date.today().isoformat()] or issues)


def scrape(log):
    eff, folder = current_issue()
    base = ROOT + quote(folder) + "/"
    toc = fetch_text(base + "v2/js/datasource.js")
    pages = sorted(set(re.findall(r'"href": "(ES-[^"#]+-en-GB\.html)', toc)))
    url = lambda p: base + "eAIP/" + quote(p)
    col = Collection(SOURCE, eff, folder.split("_")[0], base + "index-v2.html")

    # ENR 4.4: name | coordinates | ATS routes | ...
    col.documents += 1
    for r in rows(fetch_text(url("ES-ENR 4.4-en-GB.html"))):
        c = coord(" ".join(r[1:3])) if len(r) > 1 else None
        if c and re.fullmatch(r"[A-Z]{5}", r[0]):
            col.add_waypoint({"ident": r[0], "lat": c[0], "lon": c[1], "raw_coord": c[2], "usage": r[2] if len(r) > 2 else None},
                             "ENR 4.4", url("ES-ENR 4.4-en-GB.html"))

    # ENR 4.1: "ARLANDA DVOR/DME (8° E 2025)" | ARL | "116.00 MHz CH107X" | H24 | coordinates
    col.documents += 1
    for r in rows(fetch_text(url("ES-ENR 4.1-en-GB.html"))):
        t = NAV_TYPE.search(r[0]) if r else None
        c = coord(r[4]) if len(r) > 4 else None
        if t and c and re.fullmatch(r"[A-Z]{2,3}", r[1]):
            f = re.search(r"(\d+(?:\.\d+)?)\s*(MHz|kHz)", r[2], re.I)
            col.add_navaid({"ident": r[1], "type": t.group(1), "name": clean(r[0][:t.start()]) or None,
                            "frequency": float(f.group(1)) if f else None,
                            "frequency_unit": f.group(2).upper() if f else None, "raw_frequency": r[2],
                            "lat": c[0], "lon": c[1], "raw_coord": c[2]}, "ENR 4.1", url("ES-ENR 4.1-en-GB.html"))

    # ENR 3: one page per route (ENR 3.1 conventional routes is NIL)
    for p in (p for p in pages if re.match(r"ES-ENR 3\.[1-3]\b", p)):
        sec = p[3:10]
        col.documents += 1
        for r in parse_routes(text(fetch_text(url(p)))):
            col.add_route(r, sec, url(p), lambda q: point_key(q["name"]), nav_spec="RNAV" if sec != "ENR 3.1" else None)

    # AD 2: all numbered pages of an aerodrome together
    ads = {}
    for p in pages:
        m = re.match(r"ES-AD 2 ([A-Z]{4}) ", p)
        if m:
            ads.setdefault(m.group(1), []).append(p)
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, ps in sorted(ads.items()):
        col.documents += 1
        ps.sort(key=lambda p: int(re.search(r" (\d+)-en-GB", p).group(1)) if re.search(r" (\d+)-en-GB", p) else 0)
        a = parse_ad2("".join(fetch_text(url(p)) for p in ps), icao)
        if a:
            col.add_aerodrome(a, "AD 2", url(ps[0]))
        else:
            col.issue("warning", "RULE_ARP_MISSING", icao, f"{icao} AD 2.2", "ARP coordinates not found")
    return col
