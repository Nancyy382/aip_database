"""Czech Republic - ANS CR eAIP (http://ais.ans.cz/).

Cover page at /eaip/html/LK-cover-en-GB.html gives effective date and amendment.
Standard eAIP layout, prefix "LK", language "en-GB".
"""
from datetime import datetime
import re

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

BASE = "http://ais.ans.cz/eaip/html/"
SOURCE = "eAIP Czech Republic (ANS CR)"


def scrape(log):
    cover = fetch_text(f"{BASE}LK-cover-en-GB.html")
    m_eff = re.search(r"Effective date:\s*([0-9]{2}\s+[A-Z]{3}\s+[0-9]{4})", cover)
    eff_date = datetime.strptime(m_eff.group(1), "%d %b %Y").date().isoformat()
    m_amdt = re.search(r"AIP AMDT\s*([0-9]+/[0-9]+)", cover)
    amdt = f"AIRAC AMDT {m_amdt.group(1)}" if m_amdt else f"AIRAC {eff_date}"
    col = Collection(SOURCE, eff_date, amdt, f"{BASE}index-en-GB.html")
    return scrape_eaip(col, f"{BASE}eAIP/", "LK", "en-GB", log)

