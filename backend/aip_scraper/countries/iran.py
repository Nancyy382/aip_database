"""Iran - IAC AIS (https://ais.airport.ir/).

The home page links one Liferay document library per AIP edition ("AIP (Including
AIRAC AMDT 2/26,WEF 01 OCT 2026)" -> /144). Folders ENR 3 / ENR 4 hold one PDF per
section; AD 2 holds one subfolder per aerodrome with its text PDF "OIII.pdf". File
entries open a view page whose "download-document" link is the PDF. Folder listings
are paginated; asking for a 500-entry page returns everything at once.
"""
import html
import re
from datetime import datetime

from ..common import clean, fetch_text, pdf_text
from ..features import Collection
from ..parsers import (parse_aerodrome, parse_navaids_ident_first, parse_routes, parse_waypoints, point_key,
                       section)

HOME = "https://ais.airport.ir/home"
SOURCE = "AIP Islamic Republic of Iran (IAC AIS)"


def anchors(page):
    return {clean(html.unescape(re.sub(r"<[^>]+>", " ", x))): html.unescape(u)
            for u, x in re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.S)}


def listing(url):
    """All entries of a (possibly paginated) folder."""
    links = anchors(fetch_text(url))
    if links.get("Next", "").startswith("http"):  # single-page folders show a disabled "javascript:;" link
        # the paging parameters are numbered per container (cur1/delta1, cur2/delta2, ...)
        links = anchors(fetch_text(re.sub(r"(_delta\d*=)\d+", r"\g<1>500", re.sub(r"(_cur\d*=)\d+", r"\g<1>1", links["Next"]))))
    return links


def download(view_url):
    m = re.search(r'class="download-document">.*?href="([^"]+)"', fetch_text(view_url), re.S)
    return html.unescape(m.group(1)) if m else None


def current_edition():
    """(effective date, label, library URL) of the newest AIP edition already in force."""
    editions = []
    for label, url in anchors(fetch_text(HOME)).items():
        m = re.match(r"AIP \(Including (AIRAC AMDT [\d/]+),\s*WEF (\d{2} \w{3} \d{4})\)", label)
        if m:
            editions.append((datetime.strptime(m.group(2), "%d %b %Y").date(), m.group(1), url))
    today = datetime.now().date()
    return max([e for e in editions if e[0] <= today] or editions)


def scrape(log):
    eff, amdt, library = current_edition()
    col = Collection(SOURCE, eff.isoformat(), amdt, library)
    folders = anchors(fetch_text(library))
    pdf = lambda view: pdf_text(download(view))

    enr4 = listing(folders["ENR 4"])
    for name, sec, parse in (("ENR 4.4.pdf", "ENR 4.4", parse_waypoints), ("ENR 4.1.pdf", "ENR 4.1", parse_navaids_ident_first)):
        col.documents += 1
        url = download(enr4[name])
        for item in parse(pdf_text(url)):
            (col.add_waypoint if sec == "ENR 4.4" else col.add_navaid)(item, sec, url)

    enr3 = listing(folders["ENR 3"])
    for name in sorted(n for n in enr3 if re.fullmatch(r"ENR 3\.[1-3]\.pdf", n)):
        col.documents += 1
        url = download(enr3[name])
        for r in parse_routes(pdf_text(url)):
            col.add_route(r, name[:-4], url, lambda p: point_key(p["name"]),
                          nav_spec="RNAV" if re.match(r"U?[LMNPQTYZ]\d", r["designator"]) else None)

    ads = {k: v for k, v in listing(folders["AD 2"]).items() if re.fullmatch(r"OI[A-Z]{2}", k)}
    log(f"  AD 2: {len(ads)} aerodromes")
    for icao, folder in sorted(ads.items()):
        files = listing(folder)
        view = next((v for k, v in files.items() if k.lower() == f"{icao}.pdf".lower()), None)  # "OIAI.PDF"
        if not view:
            col.issue("warning", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", "no aerodrome text PDF in folder")
            continue
        col.documents += 1
        url = download(view)
        try:
            a = parse_aerodrome(pdf_text(url), icao=icao)
        except Exception as e:
            col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))
            continue
        if a:
            a["icao"] = icao
            col.add_aerodrome(a, "AD 2", url)
    return col
