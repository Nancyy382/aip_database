"""Oman - CAA AIM eAIP (https://aim.caa.gov.om/eAIP_Oman/history-en-GB.html).

The history page keeps its issues in a JavaScript array (effDate + link); the
newest issue already in force is used. Standard eAIP pages without a state
prefix ("ENR-4.4-en-GB.html").
"""
import re
from datetime import date, datetime

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

BASE = "https://aim.caa.gov.om/eAIP_Oman/"
SOURCE = "eAIP Oman (CAA)"


def scrape(log):
    page = fetch_text(BASE + "history-en-GB.html")
    issues = [(datetime.strptime(d, "%Y-%m-%d").date(), link, desc) for d, link, desc in
              re.findall(r'effDate:\s*"(\d{4}-\d{2}-\d{2})T[^"]*".*?link:\s*"([^"]+)".*?desc:\s*"([^";]+)', page, re.S)]
    eff, link, desc = max([i for i in issues if i[0] <= date.today()] or issues)
    index = fetch_text(BASE + link)
    html_dir = re.search(r'src="([^"]*/html/)toc-frameset', index).group(1)
    base = BASE + link.rsplit("/", 1)[0] + "/" + html_dir
    col = Collection(SOURCE, eff.isoformat(), desc.strip().rstrip("."), BASE + link)
    return scrape_eaip(col, base + "eAIP/", "", "en-GB", log)
