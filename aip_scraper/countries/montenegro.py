from ._smatsa import scrape_state


def scrape(log):
    return scrape_state("Montenegro", {"LYPG", "LYTV"}, log)
