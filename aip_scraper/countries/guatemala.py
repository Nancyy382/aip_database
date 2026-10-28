"""Guatemala - COCESNA eAIP Central America, prefix MG (see _cocesna.py)."""
from ._cocesna import scrape_state


def scrape(log):
    return scrape_state("MG", {"MGGT", "MGMM", "MGPB", "MGSJ"}, log)

