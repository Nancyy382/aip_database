from ._smatsa import scrape_state


def scrape(log):
    return scrape_state("Serbia", {"LYBE", "LYBT", "LYKV", "LYNI", "LYUZ", "LYVR", "LYPR"}, log)
