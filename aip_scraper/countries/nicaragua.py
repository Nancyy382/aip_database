from ._cocesna import scrape_state


def scrape(log):
    return scrape_state("MN", {"MNMG"}, log)
