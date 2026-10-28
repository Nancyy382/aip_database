"""Mauritania - ASECNA eAIP, state number 11 (see _asecna.py)."""
from ._asecna import scrape_state


def scrape(log):
    return scrape_state("11", "MRT", log)

