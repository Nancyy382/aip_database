from ._cocesna import scrape_state


def scrape(log):
    return scrape_state("MH", {"MHLC", "MHLM", "MHPR", "MHRO", "MHTG"}, log)
