"""Hungary - HungaroControl eAIP (https://ais-en.hungarocontrol.hu/aip/).

Dynamic AIRAC issue lookup from the amendments table on the landing page.
Standard Eurocontrol eAIP layout, prefix "LH", language "en-HU".
"""
from datetime import date, datetime
import re
from urllib.parse import urljoin

from ..common import fetch_text
from ..features import Collection
from ._eaip import scrape_eaip

BASE = "https://ais-en.hungarocontrol.hu/aip/"
SOURCE = "eAIP Hungary (HungaroControl)"


def current_issue():
    txt = fetch_text(BASE)
    today = date.today()
    issues = []
    for m in re.finditer(
        r'<a\s+href=[\"\']\./(\d{4}-\d{2}-\d{2})/?[\"\'][^>]*>\s*(AIRAC AMDT\s*[^<]+?)\s*</a>.*?Effective date.*?(\d{4}-\d{2}-\d{2})',
        txt, re.S | re.I
    ):
        folder, amdt, eff = m.group(1), m.group(2).strip(), m.group(3)
        d = datetime.strptime(eff, "%Y-%m-%d").date()
        issues.append((d, amdt, folder))
    issues.sort(key=lambda x: x[0])
    valid = [i for i in issues if i[0] <= today]
    return valid[-1] if valid else issues[0]


def scrape(log):
    d, amdt, folder = current_issue()
    issue_url = urljoin(BASE, f"{folder}/")
    log(f"  Hungary issue: {amdt} (effective {d.isoformat()}) at {issue_url}")
    frameset = fetch_text(issue_url)
    m = re.search(r'name=[\"\']eAISNavigation[\"\']\s+src=[\"\']([^\"\']+)[\"\']', frameset)
    if m:
        nav_src = m.group(1)
        eaip_dir = urljoin(issue_url, nav_src.rsplit("/", 1)[0] + "/")
    else:
        eaip_dir = urljoin(issue_url, f"{folder}-AIRAC/html/eAIP/")
    log(f"  eAIP directory: {eaip_dir}")

    col = Collection(SOURCE, d.isoformat(), amdt, issue_url)
    return scrape_eaip(col, eaip_dir, "LH", "en-HU", log)

