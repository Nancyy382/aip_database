"""AIP Slovenia (Slovenia Control) eAIP scraper.

Slovenia publishes a standard Eurocontrol-style eAIP (prefix LJ, lang en-GB).
The active issue link is discovered from:
https://aim.sloveniacontrol.si/aim/eAIP/Operations/history-en-GB.html
"""
import re
from urllib.parse import urljoin

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

HISTORY_URL = "https://aim.sloveniacontrol.si/aim/eAIP/Operations/history-en-GB.html"


def current_issue():
    html = fetch_text(HISTORY_URL)
    rows = re.findall(r"<tr\b.*?</tr>", html, re.S)
    candidates = []
    for r in rows:
        m_url = re.search(
            r"href=[\'\"]([^\'\"]*?(\d{4}-\d{2}-\d{2})-[^\'\"]*?/html/index\.html)[\'\"]", r
        )
        m_amdt = re.search(r"AIRAC\s+AMDT\s+(\d+/\d+)", r)
        if m_url:
            dt = m_url.group(2)
            if dt <= "2026-10-28":
                full_u = urljoin(HISTORY_URL, m_url.group(1))
                amdt = m_amdt.group(0) if m_amdt else "AIRAC AMDT"
                candidates.append((dt, amdt, full_u))

    candidates.sort(reverse=True)
    if not candidates:
        return (
            "2026-10-01",
            "AIRAC AMDT 09/2026",
            "https://aim.sloveniacontrol.si/aim/eAIP/Operations/2026-10-01-AIRAC/html/index.html",
        )
    return candidates[0]


def scrape(log):
    eff_date, amdt, index_url = current_issue()
    eaip_base = urljoin(index_url, "eAIP/")

    col = Collection(
        source="eAIP Slovenia (Slovenia Control)",
        effective_date=eff_date,
        amendment_id=amdt,
        source_url=index_url,
    )
    scrape_eaip(col, eaip_base, "LJ", "en-GB", log)
    log(f"  Slovenia: {len(col.features)} features ({col.documents} docs)")
    return col

