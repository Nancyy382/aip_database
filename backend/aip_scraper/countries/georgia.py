"""Georgia - Sakaeronavigatsia eAIP (https://airnav.ge/eaip/).

The history page at https://airnav.ge/eaip/history-en-GB.html lists all published issues.
The newest one with effective date <= today is selected.
Standard eAIP layout, prefix "UG", language "en-GB".
"""
from datetime import date, datetime
import re

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

HIST_URL = "https://airnav.ge/eaip/history-en-GB.html"
SOURCE = "eAIP Georgia (Sakaeronavigatsia)"


def scrape(log):
    txt = fetch_text(HIST_URL)
    today = date.today()
    issues = []
    for tr in re.findall(r"<tr\b.*?</tr>", txt, re.S):
        dates = re.findall(r"\d{2}\s+[A-Z]{3}\s+\d{4}", tr)
        href = re.search(r"href=[\"']([^\"']+)[\"']", tr)
        amdt = re.search(r"AIRAC\s+AIP\s+AMDT\s+[0-9/]+", tr)
        if dates and href:
            dt = datetime.strptime(dates[0], "%d %b %Y").date()
            issues.append((dt, amdt.group(0) if amdt else f"AIRAC {dt.isoformat()}", href.group(1)))

    eff, amdt, href = max([i for i in issues if i[0] <= today] or issues)
    base = "https://airnav.ge/eaip/" + href.rsplit("/", 1)[0] + "/"
    index_url = "https://airnav.ge/eaip/" + href

    col = Collection(SOURCE, eff.isoformat(), amdt, index_url)
    return scrape_eaip(col, base + "eAIP/", "UG", "en-GB", log)

