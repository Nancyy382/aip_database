"""Belize - COCESNA eAIP Central America, prefix MZ (see _cocesna.py)."""
from ._cocesna import scrape_state


def scrape(log):
    return scrape_state("MZ", {"MZBZ"}, log)
