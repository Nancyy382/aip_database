"""Albania - Albcontrol eAIP (https://www.albcontrol.al/aip/).

The AIP page links "Current Version" (e.g. /al/aip/01-OCT-2026-A/2026-10-01-AIRAC/html).
Standard eAIP layout, prefix "LA".
"""
import re

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://www.albcontrol.al/aip/"
SOURCE = "eAIP Albania (Albcontrol)"


def scrape(log):
    m = re.search(r'href="([^"]+/(\d{4}-\d{2}-\d{2})-AIRAC/html)/?"[^>]*>(?:\s*<[^>]+>)*\s*Current Version', fetch_text(PAGE))
    base, eff = m.group(1).rstrip("/") + "/", m.group(2)
    col = Collection(SOURCE, eff, f"AIRAC {eff}", base)
    return scrape_eaip(col, base + "eAIP/", "LA", "en-GB", log)
