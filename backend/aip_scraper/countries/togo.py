"""Togo - ASECNA eAIP, state number 15 (see _asecna.py)."""
from ._asecna import scrape_state


def scrape(log):
    return scrape_state("15", "TGO", log)

