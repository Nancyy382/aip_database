"""Kazakhstan - Kazaeronavigatsia eAIP (http://www.ans.kz/en/ais/eaip).

Standard Eurocontrol eAIP, prefix "UA", lang "en-GB".
"""
from datetime import date, datetime
import re

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://www.ans.kz/en/ais/eaip"
SOURCE = "eAIP Kazakhstan (Kazaeronavigatsia)"


def scrape(log):
    html = fetch_text(PAGE)
    matches = re.findall(r"href=[\"'](https?://www\.ans\.kz/AIP/eAIP/(\d{4}-\d{2}-\d{2})-AIRAC/html/index-en-GB\.html)[\"']", html)
    issues = []
    for url, dt_str in matches:
        dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        issues.append((dt, url))

    past = [i for i in issues if i[0] <= date.today()]
    curr_dt, curr_url = max(past or issues)

    base = curr_url.rsplit("/", 1)[0] + "/"
    col = Collection(SOURCE, curr_dt.isoformat(), f"AIRAC {curr_dt.isoformat()}", curr_url)
    return scrape_eaip(col, base + "eAIP/", "UA", "en-GB", log)
