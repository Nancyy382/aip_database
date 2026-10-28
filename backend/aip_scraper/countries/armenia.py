"""Armenia - ARMATS eAIP (https://armats.am/category/eaip/).

The category page lists one post per AIRAC amendment ("/02-26-09jul2026/"); each
post links its eAIP under "/wp-content/uploads/html-uploads/02-26-09JUL2026/". The
newest amendment in force is used. Standard eAIP layout, prefix "UD".
"""
import re
from datetime import date, datetime

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

CATEGORY = "https://armats.am/category/eaip/"
SOURCE = "eAIP Armenia (ARMATS)"


def scrape(log):
    posts = [(datetime.strptime(d, "%d%b%Y").date(), f"AIRAC AMDT {n}/{y}", u) for u, n, y, d in
             set(re.findall(r'href="(https://armats\.am/(\d{2})-(\d{2})-(\d{2}[a-z]{3}\d{4})/)"', fetch_text(CATEGORY)))]
    eff, amdt, post = max([p for p in posts if p[0] <= date.today()] or posts)
    base = re.search(r'href="([^"]*/html-uploads/[^"]+/)"', fetch_text(post)).group(1) + "html/"
    col = Collection(SOURCE, eff.isoformat(), amdt, post)
    return scrape_eaip(col, base + "eAIP/", "UD", "en-GB", log)
