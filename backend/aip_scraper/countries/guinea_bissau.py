"""Guinea-Bissau - ASECNA eAIP, state number 17 (see _asecna.py)."""
from ._asecna import scrape_state


def scrape(log):
    return scrape_state("17", "GNB", log)
