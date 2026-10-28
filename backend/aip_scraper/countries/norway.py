"""Norway - Avinor eAIP (https://aim-prod.avinor.no/no/AIP/).

Standard Eurocontrol eAIP, prefix "EN", lang "no-NO".
"""
import re
import urllib.parse
import urllib.request

from ..common import USER_AGENT, fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://aim-prod.avinor.no/no/AIP/"
SOURCE = "eAIP Norway (Avinor)"


def current_issue():
    # Avinor redirects /no/AIP/ to View/Index/<num>/history-no-NO.html
    # We fetch with fetch_text which handles redirects and caches
    page = fetch_text(PAGE)
    m = re.search(r"href=[\"']([^\"']*(\d{4}-\d{2}-\d{2})[^\"]*index[^\"]*\.html)[\"']", page)
    if not m:
        # Fallback search for any date in page
        m = re.search(r"(\d{4}-\d{2}-\d{2})", page)
        eff = m.group(1) if m else "2026-09-03"
        curr_url = f"https://aim-prod.avinor.no/no/AIP/View/Index/155/{eff}-AIRAC/html/index-no-NO.html"
        return eff, curr_url
    eff, rel = m.group(2), m.group(1)
    curr_url = urllib.parse.urljoin("https://aim-prod.avinor.no/no/AIP/View/Index/155/history-no-NO.html", rel)
    return eff, curr_url


def scrape(log):
    eff, curr_url = current_issue()
    base_eaip = curr_url.rsplit("/", 1)[0] + "/eAIP/"

    m_amdt = re.search(r"AIP\s+AMDT\s+[\d/]+", curr_url)
    amdt_id = m_amdt.group(0) if m_amdt else f"AIRAC {eff}"

    col = Collection(SOURCE, eff, amdt_id, curr_url)
    return scrape_eaip(col, base_eaip, "EN", "no-NO", log)
