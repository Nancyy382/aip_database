"""Bahamas - BANSA AIP (https://bansabahamas.com/aip.html).

The page embeds the AIP tree as JSON (<script id="aipData">); each leaf has a
publicId. "fileaipbansa.json?publicId=..." lists that section's PDFs (short-lived
signed S3 links) and "filelinkaipbansa.txt?fileUrl=..." returns a PDF as a
base64 data URL. Every aerodrome has an "AD 2.1 - 2.25" leaf under "XXXX - NAME".
"""
import base64
import hashlib
import json
import os
import re
import urllib.parse
from datetime import datetime

from .. import common
from ..common import fetch, fetch_text, pdf_bytes_text
from ..features import Collection
from ..parsers import parse_aerodrome, parse_navaids_ident_first, parse_routes, parse_waypoints, point_key

BASE = "https://bansabahamas.com/"
PAGE = BASE + "aip.html"
SOURCE = "AIP The Bahamas (BANSA)"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def tree():
    """[(title, publicId, parent title)] for every leaf of the AIP tree."""
    page = fetch_text(PAGE)
    i = page.find('<script id="aipData"')
    start = page.find("[", page.find("children:", i))
    depth = 0
    for n, ch in enumerate(page[start:]):
        depth += (ch == "[") - (ch == "]")
        if depth == 0:
            break
    leaves = []

    def walk(items, parent):
        for it in items:
            if it["children"]:
                walk(it["children"], it["title"])
            else:
                leaves.append((it["title"], it["publicId"], parent))
    walk(json.loads(page[start: start + n + 1]), "")
    return leaves


def section_text(public_id):
    """All PDFs of one AIP leaf as text. The listing is never cached (its S3 links expire after
    10 minutes); the PDFs are cached under .cache/ by their stable S3 path."""
    texts, files = [], json.loads(fetch_text(f"{BASE}fileaipbansa.json?publicId={public_id}&format=json"))
    for f in files if isinstance(files, list) else [files]:
        stable = f["archives_file"].split("?")[0]
        path = os.path.join(common.CACHE_DIR, "bansa-" + hashlib.sha1(stable.encode()).hexdigest())
        if not os.path.exists(path):
            data = fetch(f"{BASE}filelinkaipbansa.txt?fileUrl={urllib.parse.quote(f['archives_file'], safe='')}",
                         cache=False)
            os.makedirs(common.CACHE_DIR, exist_ok=True)
            with open(path, "wb") as out:
                out.write(base64.b64decode(data[data.index(b",") + 1:]))
        with open(path, "rb") as fh:
            texts.append(pdf_bytes_text(fh.read(), stable))
    return "\n".join(texts)


def scrape(log):
    leaves = tree()
    find = lambda prefix: next((pid for title, pid, _ in leaves if title.startswith(prefix)), None)
    enr = {sec: section_text(find(sec)) for sec in ("ENR 3.1", "ENR 3.2", "ENR 4.1", "ENR 4.4")}
    dates = [datetime(int(y), MONTHS[m], int(d)).date().isoformat()
             for t in enr.values() for d, m, y in re.findall(r"\b(\d{2}) ([A-Z]{3}) (\d{4})\b", t) if m in MONTHS]
    col = Collection(SOURCE, max(dates), "current", PAGE)
    col.documents += len(enr)
    url = lambda sec: f"{PAGE}#{sec}"

    for w in parse_waypoints(enr["ENR 4.4"]):
        col.add_waypoint(w, "ENR 4.4", url("ENR 4.4"))
    for n in parse_navaids_ident_first(enr["ENR 4.1"]):
        col.add_navaid(n, "ENR 4.1", url("ENR 4.1"))
    for sec in ("ENR 3.1", "ENR 3.2"):
        for r in parse_routes(enr[sec]):
            col.add_route(r, sec, url(sec), lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if sec == "ENR 3.2" else None)

    ads = [(re.match(r"(MY[A-Z]{2})", parent).group(1), pid) for title, pid, parent in leaves
           if title.startswith("AD 2.1") and re.match(r"MY[A-Z]{2}\b", parent)]
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, pid in ads:
        col.documents += 1
        try:
            a = parse_aerodrome(section_text(pid), icao=icao)
        except Exception as e:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))
            continue
        if a:
            a["icao"] = icao
            col.add_aerodrome(a, "AD 2", url(f"{icao} AD 2"))
    return col
