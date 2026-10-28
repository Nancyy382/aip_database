# AIP database scraper

Scrapes national AIPs, starting from the links on
<https://www.eurocontrol.int/articles/ais-online>, into one GeoJSON file per country:
`data/<continent>/<country>.json`. The files use the same format as the viewer at
<https://aip.ishu.foo>. Only six layers are kept: aerodrome, runway, runwayDirection,
navaid, waypoint and route.

Requirements: Python 3, plus `pdftotext` (poppler). Some countries also need
`tesseract` (Ecuador) or `bsdtar` (Paraguay).

## Update the data (e.g. every AIRAC cycle, 28 days)

```sh
python3 -m aip_scraper.run --no-cache          # every country, fresh downloads
python3 -m aip_scraper.validate data/*/*.json   # format check
python3 -m aip_scraper.rwycheck data/*/*.json   # runway threshold/bearing check
```

- Without `--no-cache`, pages already downloaded are reused from `.cache/`. This is fast and good for re-parsing.
- `python3 -m aip_scraper.run belarus armenia` runs only those countries.
- `python3 -m aip_scraper.run --continent europe` runs one continent.
- If a site is down or has changed its layout, that country is reported as `FAILED` and its previous file is kept. The run continues and exits with code 1.

Example cron entry (03:00 on the 1st and 15th of each month):

```cron
0 3 1,15 * * cd /path/to/aip_database && python3 -m aip_scraper.run --no-cache >> scrape.log 2>&1
```

## Add a new country

1. Get its official links and contacts from Eurocontrol (always pass `--countries`, so other files are not overwritten):
   `python3 scrape_eurocontrol_ais.py --continent "Europe" --countries "Croatia"`
2. If an existing shared scraper covers it as-is (e.g. another ASECNA state), add one line to `SHARED` in
   `aip_scraper/run.py`, e.g. `"cameroon": ("_asecna", "scrape_state", ("03", "CMR"))`, and skip to step 3.
   Otherwise write `aip_scraper/countries/<slug>.py` with `scrape(log) -> Collection`. Reuse what fits:
   - `_eaip.py`: standard Eurocontrol HTML eAIPs (most of Europe and the Middle East).
   - `_asecna.py`: the 17 ASECNA states in Africa.
   - `parsers.py`: PDF AIPs (ENR 3, ENR 4.1, ENR 4.4, AD 2).
   - `eaip_html.py`: HTML tables.
   - `aixm.py`: AIXM 5.1.
3. Add the slug to `COUNTRIES` in `aip_scraper/run.py`, run it, then validate.
4. If the AIP is not publicly available (login, paywall, WAF block, site down), add the slug to `UNAVAILABLE` in
   `run.py` with the reason and delete its JSON file. Access controls and TLS checks are never bypassed.

## Layout

| Path | Purpose |
|---|---|
| `scrape_eurocontrol_ais.py` | Eurocontrol page → per-country websites and contacts |
| `aip_scraper/run.py` | runner; `COUNTRIES`, `SHARED` (countries handled by a shared scraper), `UNAVAILABLE` |
| `aip_scraper/countries/` | one module per country that needs its own logic, plus the shared `_eaip.py`, `_asecna.py` and `_dutch_caribbean.py` |
| `aip_scraper/common.py` | cached HTTP, PDF text, coordinate parsing |
| `aip_scraper/features.py` | builds features, issues and publications in the viewer format |
| `aip_scraper/validate.py`, `rwycheck.py` | quality checks |
| `aip_scraper/borders.py` | country borders, used only to split ASECNA's shared ENR 3 / 4.4 |
| `aip_scraper/certs/` | intermediate certificates some AIS servers omit (verified against system roots) |
