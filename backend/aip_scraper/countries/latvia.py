"""Latvia - LGS eAIP (https://ais.lgs.lv/aiseaip).

Standard Eurocontrol eAIP, prefix "EV", lang "en-GB".
"""
from datetime import date, datetime
import re

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://ais.lgs.lv/aiseaip"
SOURCE = "Integrated Aeronautical Information Package (LGS)"


def scrape(log):
    html = fetch_text(PAGE)
    matches = re.findall(r"href=[\"'](eAIPfiles/[^\s\"']*/data/(\d{4}-\d{2}-\d{2})/html/index\.html)[\"']", html)
    issues = []
    for rel, dt_str in matches:
        dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        issues.append((dt, "https://ais.lgs.lv/" + rel))

    past = [i for i in issues if i[0] <= date.today()]
    curr_dt, curr_url = max(past or issues)

    base = curr_url.rsplit("/", 1)[0] + "/"
    col = Collection(SOURCE, curr_dt.isoformat(), f"AIRAC {curr_dt.isoformat()}", curr_url)
    return scrape_eaip(col, base + "eAIP/", "EV", "en-GB", log)
