"""Niger - ASECNA eAIP, state number 12 (see _asecna.py)."""
from ._asecna import scrape_state


def scrape(log):
    return scrape_state("12", "NER", log)

