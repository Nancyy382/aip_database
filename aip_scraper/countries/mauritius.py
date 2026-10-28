"""Mauritius - Department of Civil Aviation eAIP (https://civil-aviation.govmu.org/eAIP/eAIPMauritius/index.html).

Standard eAIP without prefix, language "en-GB".
"""
from datetime import datetime
import re
from urllib.parse import urljoin

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

BASE = "https://civil-aviation.govmu.org/eAIP/eAIPMauritius/"
SOURCE = "eAIP Mauritius (DCA)"


def scrape(log):
    index = fetch_text(urljoin(BASE, "index.html"))
    m = re.search(r'src=[\"\'](final/(\d{4}-\d{2}-\d{2})/html/[^\"\']+)[\"\']', index)
    if not m:
        m = re.search(r'src=[\"\']([^\"\']*toc-frameset[^\"\']*)[\"\']', index)
    rel_path = m.group(1) if m else "final/2026-07-23/html/toc-frameset-en-GB.html"
    issue_folder = m.group(2) if m and m.lastindex >= 2 else "2026-07-23"
    html_dir = urljoin(BASE, rel_path.rsplit("/", 1)[0] + "/")
    eaip_dir = urljoin(html_dir, "eAIP/")

    # Read cover for amendment id
    cover = fetch_text(urljoin(html_dir, "cover-en-GB.html"))
    amdt = f"AIRAC {issue_folder}"
    m_amdt = re.search(r"AIRAC\s*(?:AIP\s*)?AMDT\s*([0-9]+/[0-9]+)", cover, re.I)
    if m_amdt:
        amdt = f"AIRAC AMDT {m_amdt.group(1)}"

    col = Collection(SOURCE, issue_folder, amdt, urljoin(BASE, "index.html"))
    return scrape_eaip(col, eaip_dir, "", "en-GB", log)

