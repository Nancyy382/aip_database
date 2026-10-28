"""Estonia - EANS eAIP (https://aim.eans.ee/en/eaip).

The eAIP landing page links the current issue (e.g. http://eaip.eans.ee/2026-10-01/html/index-en-GB.html).
Standard eAIP layout, prefix "EE", language "en-GB".
"""
from datetime import date, datetime
import re

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://aim.eans.ee/en/eaip"
SOURCE = "eAIP Estonia (EANS)"


def scrape(log):
    eaip_page = fetch_text(PAGE)
    today = date.today()
    issues = []
    for m in re.finditer(r"http://eaip\.eans\.ee/(\d{4}-\d{2}-\d{2})/html/index-en-GB\.html", eaip_page):
        dt = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        issues.append((dt, m.group(0)))
    eff, index_url = max([i for i in issues if i[0] <= today] or issues)
    base = index_url.rsplit("/", 1)[0] + "/"
    cover = fetch_text(base + "EE-cover-en-GB.html")
    m_amdt = re.search(r"AIRAC Amendment\s*([0-9]+/[0-9]+)", cover)
    amdt = f"AIRAC AMDT {m_amdt.group(1)}" if m_amdt else f"AIRAC {eff.isoformat()}"

    col = Collection(SOURCE, eff.isoformat(), amdt, index_url)
    return scrape_eaip(col, base + "eAIP/", "EE", "en-GB", log)

