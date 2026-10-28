"""Ivory Coast (Côte d'Ivoire) - ASECNA eAIP, state number 06 (see _asecna.py)."""
from ._asecna import scrape_state


def scrape(log):
    return scrape_state("06", "CIV", log)
