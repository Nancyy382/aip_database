"""Israel - CAAI eAIP (https://e-aip.azurefd.net/).

Eurocontrol lists https://www.gov.il/en/Departments/General/electronic-aip, which sits
behind a Cloudflare browser check; the eAIP itself is published on its own host,
whose start page lists the issues ("2026-08-06-AIRAC/html/index.html"). The newest
issue in force is used. Standard eAIP layout, prefix "LL".
"""
import re
from datetime import date, datetime

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

BASE = "https://e-aip.azurefd.net/"
SOURCE = "eAIP Israel (CAAI)"


def scrape(log):
    issues = [(datetime.strptime(d, "%Y-%m-%d").date(), href) for href, d in
              re.findall(r'href="((\d{4}-\d{2}-\d{2})-AIRAC/html/index\.html)"', fetch_text(BASE))]
    eff, href = max([i for i in issues if i[0] <= date.today()] or issues)
    col = Collection(SOURCE, eff.isoformat(), f"AIRAC {eff:%d %b %Y}".upper(), BASE + href)
    return scrape_eaip(col, BASE + href.rsplit("/", 1)[0] + "/eAIP/", "LL", "en-GB", log)
