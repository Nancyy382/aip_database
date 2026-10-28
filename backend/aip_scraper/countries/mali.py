"""Mali - ASECNA eAIP, state number 10 (see _asecna.py)."""
from ._asecna import scrape_state


def scrape(log):
    return scrape_state("10", "MLI", log)

