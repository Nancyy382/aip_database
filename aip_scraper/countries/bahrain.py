"""Bahrain - MTT AIM eAIP (https://aim.mtt.gov.bh/eaip).

The eAIP page links each AIRAC issue ("/eAIP/2026-07-09-AIRAC/html/index-en-BH.html");
the newest one already in force is used. Standard eAIP layout, prefix "OB".
"""
import re
from datetime import date, datetime

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://aim.mtt.gov.bh/eaip"
SOURCE = "eAIP Bahrain (MTT)"


def scrape(log):
    issues = [(datetime.strptime(d, "%Y-%m-%d").date(), u) for u, d in
              re.findall(r'href="(https://aim\.mtt\.gov\.bh/eAIP/(\d{4}-\d{2}-\d{2})-AIRAC/html/index-en-BH\.html)"',
                         fetch_text(PAGE))]
    eff, index = max([i for i in issues if i[0] <= date.today()] or issues)
    col = Collection(SOURCE, eff.isoformat(), f"AIRAC {eff:%d %b %Y}".upper(), index)
    return scrape_eaip(col, index.rsplit("/", 1)[0] + "/eAIP/", "OB", "en-BH", log)
