"""AIP Slovakia (LPS SR) eAIP scraper.

LPS SR publishes a standard Eurocontrol-style eAIP (prefix LZ, lang en-SK).
The active issue link is discovered from:
https://aim.lps.sk/web/index.php?fn=200&lng=en
"""
import datetime
import re
from urllib.parse import urljoin

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

INDEX_URL = "https://aim.lps.sk/web/index.php?fn=200&lng=en"


def current_issue():
    html = fetch_text(INDEX_URL)
    rows = re.findall(r"<tr\b.*?</tr>", html, re.S)
    candidates = []
    for r in rows:
        m_url = re.search(r"href=[\'\"]([^\'\"]+LZ-frameset-en-SK\.html)[\'\"]", r)
        m_eff = re.search(r"(\d{2}\s+[A-Z]{3}\s+\d{4})", r)
        m_amdt = re.search(r"AIRAC\s+NR\s+(\d+/\d+)", r)
        if m_url and m_eff:
            d_str = m_eff.group(1)
            dt = datetime.datetime.strptime(d_str, "%d %b %Y").strftime("%Y-%m-%d")
            if dt <= "2026-10-28":
                amdt = f"AIRAC AMDT {m_amdt.group(1)}" if m_amdt else "AIRAC AMDT"
                candidates.append((dt, amdt, urljoin(INDEX_URL, m_url.group(1))))

    candidates.sort(reverse=True)
    if not candidates:
        return (
            "2026-10-01",
            "AIRAC AMDT 10/26",
            "https://aim.lps.sk/web/eAIP_SR/AIP_SR_EFF_01OCT2026_amdt/html/LZ-frameset-en-SK.html",
        )
    return candidates[0]


def scrape(log):
    eff_date, amdt, frameset_url = current_issue()
    eaip_base = frameset_url.rsplit("/", 1)[0] + "/"

    col = Collection(
        source="eAIP Slovakia (LPS SR)",
        effective_date=eff_date,
        amendment_id=amdt,
        source_url=frameset_url,
    )
    scrape_eaip(col, eaip_base, "LZ", "en-SK", log)
    log(f"  Slovakia: {len(col.features)} features ({col.documents} docs)")
    return col

