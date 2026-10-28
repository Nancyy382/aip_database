"""El Salvador - COCESNA eAIP Central America, prefix MS (see _cocesna.py)."""
from ._cocesna import scrape_state


def scrape(log):
    return scrape_state("MS", {"MSLP", "MSSS"}, log)

