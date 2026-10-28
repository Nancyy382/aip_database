"""Qatar - QCAA AIM eAIP (https://aim.gov.qa/AIP/QA-history-en-GB.html).

Eurocontrol links the CAA page, which points at the eAIP history page. Issues are
listed as "<pub date>/AIP-nn/<YYYY-MM-DD>-000000/html/index-en-GB.html"; the newest
one already in force is used. Standard eAIP layout, prefix "QA".
"""
import re
from datetime import date, datetime

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

BASE = "https://aim.gov.qa/AIP/"
SOURCE = "eAIP Qatar (QCAA)"


def scrape(log):
    page = fetch_text(BASE + "QA-history-en-GB.html")
    issues = [(datetime.strptime(d, "%Y-%m-%d").date(), href) for href, d in
              re.findall(r'href="([^"]+/(\d{4}-\d{2}-\d{2})-\d{6}/html/index-en-GB\.html)"', page)]
    eff, href = max([i for i in issues if i[0] <= date.today()] or issues)
    col = Collection(SOURCE, eff.isoformat(), f"AIRAC {eff:%d %b %Y}".upper(), BASE + href)
    return scrape_eaip(col, BASE + href.rsplit("/", 1)[0] + "/eAIP/", "QA", "en-GB", log)
