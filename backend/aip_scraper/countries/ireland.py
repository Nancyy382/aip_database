"""Ireland - AirNav Ireland eAIP (https://www.airnav.ie/air-traffic-management/aeronautical-information-management).

Standard Eurocontrol eAIP, prefix "EI", lang "en-IE".
"""
from datetime import date, datetime
import re

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://www.airnav.ie/air-traffic-management/aeronautical-information-management"
SOURCE = "eAIP Ireland (AirNav Ireland)"


def scrape(log):
    html = fetch_text(PAGE)
    matches = re.findall(r"href=[\"'](https?://www\.airnav\.ie/[^\s\"']*/(\d{4}-\d{2}-\d{2})-AIRAC/html/index\.html)[\"']", html)
    issues = []
    for url, dt_str in matches:
        dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        issues.append((dt, url))

    past = [i for i in issues if i[0] <= date.today()]
    curr_dt, curr_url = max(past or issues)

    base = curr_url.rsplit("/", 1)[0] + "/"
    col = Collection(SOURCE, curr_dt.isoformat(), f"AIRAC {curr_dt.isoformat()}", curr_url)
    return scrape_eaip(col, base + "eAIP/", "EI", "en-IE", log)
