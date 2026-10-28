"""Bosnia and Herzegovina - BHANSA eAIP (https://eaip.bhansa.gov.ba/).

The history page is filled from "updates.json" (effectiveDate + description); each
issue lives at "/<YYYY-MM-DD>-AIRAC/html/". The newest issue in force is used.
Standard eAIP layout, prefix "LQ".
"""
from datetime import date, datetime

from ..common import fetch_json
from ..features import Collection
from ._eaip import scrape_eaip

BASE = "https://eaip.bhansa.gov.ba/"
SOURCE = "eAIP Bosnia and Herzegovina (BHANSA)"


def scrape(log):
    issues = [(datetime.strptime(u["effectiveDate"].title(), "%d %b %Y").date(), u["description"].splitlines()[0])
              for u in fetch_json(BASE + "updates.json")]
    eff, desc = max([i for i in issues if i[0] <= date.today()] or issues)
    base = f"{BASE}{eff.isoformat()}-AIRAC/html/"
    col = Collection(SOURCE, eff.isoformat(), desc, base + "index.html")
    return scrape_eaip(col, base + "eAIP/", "LQ", "en-GB", log)
