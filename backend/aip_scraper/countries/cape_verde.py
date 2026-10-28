"""Cape Verde - ASA eAIP (https://eaip.asa.cv/).

The eAIP portal lists published issues on the home page (history.css table).
Standard Eurocontrol eAIP format, prefix "GV", lang "en-GB".
"""
import re
from datetime import date, datetime
from urllib.parse import urljoin

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

PAGE = "https://eaip.asa.cv/"
SOURCE = "eAIP Cape Verde (ASA)"


def scrape(log):
    html = fetch_text(PAGE)
    issues = []
    for href, d, _lang in re.findall(r'href=[\'"]([^\'"]*?(\d{4}-\d{2}-\d{2})-AIRAC/html/index-([a-zA-Z-]+)\.html)[\'"]', html):
        eff_date = datetime.strptime(d, "%Y-%m-%d").date()
        issues.append((eff_date, urljoin(PAGE, href), d))
    if not issues:
        raise RuntimeError("No eAIP issues found on " + PAGE)
    eff_date, index_url, d_str = max([i for i in issues if i[0] <= date.today()] or issues)
    # Check amendment ID in index or default to AIRAC AMDT
    eaip_base = index_url.rsplit("/", 1)[0] + "/eAIP/"
    amdt_id = f"AIRAC AMDT {eff_date:%Y-%m}"
    try:
        amdt_html = fetch_text(f"{eaip_base}GV-AMDT-en-GB.html")
        m = re.search(r"AIRAC\s*AMDT\s*(\d{1,3}/\d{2,4})", amdt_html, re.I)
        if m:
            amdt_id = f"AIRAC AMDT {m.group(1)}"
        else:
            m = re.search(r'id=["\']AIRAC-(\d{4}-\d{2})', amdt_html)
            if m:
                amdt_id = f"AIRAC AMDT {m.group(1)}"
    except Exception:
        pass

    col = Collection(SOURCE, d_str, amdt_id, index_url)
    return scrape_eaip(col, eaip_base, "GV", "en-GB", log)
