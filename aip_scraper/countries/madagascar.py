"""Madagascar - ASECNA eAIP, state number 09 (see _asecna.py)."""
from ._asecna import scrape_state


def scrape(log):
    return scrape_state("09", "MDG", log)
