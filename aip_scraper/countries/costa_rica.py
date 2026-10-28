"""Costa Rica - COCESNA eAIP Central America, prefix MR (see _cocesna.py)."""
from ._cocesna import scrape_state


def scrape(log):
    return scrape_state("MR", {"MRLB", "MRLM", "MROC", "MRPV"}, log)

