"""Senegal - ASECNA eAIP, state number 13 (see _asecna.py)."""
from ._asecna import scrape_state


def scrape(log):
    return scrape_state("13", "SEN", log)

