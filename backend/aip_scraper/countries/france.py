"""France - French SIA eAIP (https://www.sia.aviation-civile.gouv.fr/).

HTML eAIP at /media/dvd/eAIP_<DD_MON_YYYY>/FRANCE/AIRAC-<date>/html/.
Standard eAIP layout, prefix "FR", language "fr-FR".
Only Metropolitan French aerodromes (LF**) and en-route items are published in this package.
"""
from datetime import date, timedelta

from ..common import fetch
from ..features import Collection
from ._eaip import scrape_eaip

SIA = "https://www.sia.aviation-civile.gouv.fr/media/dvd/"
SOURCE = "eAIP France (SIA)"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
AIRAC_EPOCH = date(2026, 1, 22)


def current_base():
    today = date.today()
    cycle = AIRAC_EPOCH + timedelta(days=28 * ((today - AIRAC_EPOCH).days // 28))
    for d in (cycle, cycle - timedelta(days=28), cycle - timedelta(days=56)):
        base = f"{SIA}eAIP_{d.day:02d}_{MONTHS[d.month - 1]}_{d.year}/FRANCE/AIRAC-{d.isoformat()}/html/"
        try:
            fetch(base + "index-fr-FR.html")
            return base, d
        except Exception:
            continue
    raise RuntimeError("no FRANCE eAIP found for the last three AIRAC cycles")


def scrape(log):
    base, cycle = current_base()
    eff = cycle.isoformat()
    col = Collection(SOURCE, eff, f"AIRAC {cycle.month:02d}/{cycle.year % 100:02d}", base + "index-fr-FR.html")
    return scrape_eaip(col, base + "eAIP/", "FR", "fr-FR", log)

