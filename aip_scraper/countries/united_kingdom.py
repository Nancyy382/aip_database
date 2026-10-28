"""United Kingdom - NATS eAIP (https://nats-uk.ead-it.com/cms-nats/opencms/en/Publications/AIP/).

The AIP page links each AIRAC issue ("https://www.aurora.nats.co.uk/htmlAIP/Publications/
2026-10-01-AIRAC/html/index-en-GB.html"); the newest one in force is used.
Standard eAIP layout, prefix "EG".
"""
import re
from datetime import date

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://nats-uk.ead-it.com/cms-nats/opencms/en/Publications/AIP/"
SOURCE = "UK AIP (NATS)"


def scrape(log):
    issues = sorted(set(re.findall(r'href="(https://www\.aurora\.nats\.co\.uk/htmlAIP/Publications/'
                                   r'(\d{4}-\d{2}-\d{2})-AIRAC/html/)index-en-GB\.html"', fetch_text(PAGE))),
                    key=lambda i: i[1])
    base, eff = max([i for i in issues if i[1] <= date.today().isoformat()] or issues, key=lambda i: i[1])
    col = Collection(SOURCE, eff, f"AIRAC {eff}", base + "index-en-GB.html")
    return scrape_eaip(col, base + "eAIP/", "EG", "en-GB", log)
