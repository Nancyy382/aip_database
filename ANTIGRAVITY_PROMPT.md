# Task: scrape national AIP data (via Eurocontrol "AIS Online") into plot-ready GeoJSON, one file per country

## Goal
For a given continent and list of countries, build a Python scraper that:
1. Reads the country's entry on https://www.eurocontrol.int/articles/ais-online (the country list is grouped by continent; each country has links to its national AIS/eAIP website, plus contact e-mails).
2. Follows those links to the country's **official AIP / eAIP** (HTML pages, PDFs, JSON APIs, AIXM, archives — whatever that state publishes publicly).
3. Extracts **only these six feature types**: `aerodrome`, `runway`, `runwayDirection`, `navaid`, `waypoint`, `route`. Nothing else (no airspaces, obstacles, procedures, charts).
4. Writes **one JSON file per country** at `data/<continent_slug>/<country_slug>.json` (e.g. `data/europe/bosnia_and_herzegovina.json`), in the GeoJSON format described below. This is the same structure that the viewer at https://aip.ishu.foo loads from its `/api/features` endpoint, so the files can be plotted directly.
5. Writes **no file** for a country whose data can't be obtained. Record the reason in an `UNAVAILABLE = {slug: "reason"}` dict in the runner instead.

The data must come from the links Eurocontrol lists for that country (or the current location those links redirect or point to). Do not use third-party aggregators (OpenAIP, OurAirports, flight-sim databases, etc.).

## Hard rules (non-negotiable)
- **Never bypass access controls.** That means no logins, passwords, paywalls, CAPTCHAs, Cloudflare or other bot checks, WAF blocks, or rate limits. Also no spoofed Referer, browser User-Agent or cookies used to get past a block. If a site needs registration, returns 403 "Access blocked", has password-protected PDFs, or times out, mark the country UNAVAILABLE with the reason and move on.
- **Never disable TLS verification** (no `verify=False`, `curl -k`, unverified SSL context). If a server sends an incomplete certificate chain, download the missing intermediate from the leaf certificate's AIA "CA Issuers" URL. Then check that `openssl verify -untrusted inter.pem leaf.pem` succeeds against the system roots, and add it to a bundled `certs/intermediates.pem` that is loaded **in addition to** the system trust store.
- Identify honestly with a User-Agent like `aip-database-scraper/1.0 (+https://www.eurocontrol.int/articles/ais-online)`.
- Cache every HTTP response on disk (`.cache/`, keyed by sha1 of URL + headers + body) so reruns don't hit servers again. Retry with backoff at most 3 times.
- Never put credentials or tokens in code; keep them in a gitignored `.env`.

## Project layout (Python 3, stdlib + `pdftotext` from poppler; `tesseract` and `bsdtar` only if needed)
```
scrape_eurocontrol_ais.py      # Eurocontrol page -> per-country metadata (websites, emails)
aip_scraper/
  common.py                    # fetch (cached), fetch_text/json, pdf_text (pdftotext -layout), coordinate parsing
  parsers.py                   # shared PDF-text parsers (ENR 3, ENR 4.1, ENR 4.4, AD 2.2, AD 2.12)
  eaip_html.py                 # shared HTML table parsers for Eurocontrol-style eAIPs
  features.py                  # Collection class: builds features, issues, publications; writes the file
  validate.py                  # schema/sanity validator (see "Validation")
  run.py                       # COUNTRIES = {continent: [slugs]}, UNAVAILABLE = {...}; CLI: run.py [slugs] [--continent X]
  countries/<slug>.py          # one module per country exposing scrape(log) -> Collection
  countries/_eaip.py           # generic scraper for standard eAIP products (see below)
  certs/intermediates.pem
data/<continent>/<country>.json
```
The runner runs `countries.<slug>.scrape()` for each country and attaches Eurocontrol metadata as `meta`. It writes the file only when the result contains features.

## Which AIP sections to read (ICAO AIP structure)
| Feature | Section |
|---|---|
| waypoint | ENR 4.4 (name-code designators for significant points). Optionally add route points missing from ENR 4.4 from the ENR 3 tables. |
| navaid | ENR 4.1 (radio navigation aids en-route): ident, type, name, frequency, coordinates |
| route | ENR 3.1 (lower), 3.2 (upper), 3.3 (RNAV); 3.4/3.5 if they have routes. Ordered list of significant points. |
| aerodrome | AD 2.x of each aerodrome: AD 2.1 (name), AD 2.2 (ARP coordinates, elevation) |
| runway + runwayDirection | AD 2.12 (designations, true bearing, dimensions, surface, THR coordinates) |

## Finding the current issue (do this dynamically, never hard-code a date)
eAIPs are published per AIRAC issue. Locate the issue **in force today** from the site's own index: a history/amendment page, `updates.json`, an issue table with "valid from/until", or a menu. Use the newest one whose effective date is ≤ today. Record the effective date and amendment id (e.g. "AIRAC AMDT 009/2026") in the publication.

### Standard Eurocontrol eAIP (most European/Middle-East states)
- Pages are `<eAIP folder>/<PREFIX>-<SECTION>-<lang>.html`, e.g. `LQ-ENR-4.4-en-GB.html` and `LQ-AD-2.LQBK-en-GB.html`. They are listed in `<PREFIX>-menu-<lang>.html`. PREFIX is the 2-letter ICAO nationality prefix (LA Albania, LO Austria, LQ Bosnia, UD Armenia, UM Belarus...); some products use no prefix.
- Resolve section URLs from the menu's own `href`s with `urljoin`. Some products point into another issue folder.
- Tolerate menu links that 404: log an issue and continue.
- Strip hidden content (`display:none` spans, which hold amendment-diff text) before reading cells.
- Some eAIPs (e.g. Belarus) have HTML pages that only list charts, with the text in PDFs (`../pdf/UM_ENR_4_4_en.pdf`, `UM_AD_2_UMMS_en.pdf`). In that case parse the PDFs.

### Other formats seen in practice
- One PDF per section or per aerodrome (Austria: `PART_3/AD_2/.../LO_AD_2_LOWW_en.pdf`, linked from `ad_2.htm`).
- WordPress posts per AIRAC linking an uploaded eAIP (Armenia).
- Liferay document libraries with paginated folders (Iran).
- JSON APIs, AIXM 5.1 XML, RAR/ZIP archives, scanned images needing OCR.

Inspect each site and write a small country module; reuse the shared parsers wherever possible.

## Parsing PDFs
- Use `pdftotext -layout`; columns line up by character position.
- Tables are often bilingual (English + national language); ignore non-Latin lines.
- Values may be split across lines. For example, Belarus ENR 4.4 prints the latitude on the line **above** the name and the longitude on the line **below** it. Look ±1–2 lines around an anchor (ident or point name).
- Skip table-of-contents lines, page headers and footers ("AIP XXX", "ENR 4.4 - 2", "AIRAC AMDT ..."), and "THIS PAGE INTENTIONALLY LEFT BLANK".
- In route tables, a designator alone at the start of a line (`L23`, `UM860`, `H83`) opens a route. Each point row ("C LOVIK 520500N 0310054E"; C/R or ▲/△ = compulsory/on request) adds a point. Navaid points may print the name above and "(IDENT)" below.

## Coordinates — normalise everything to decimal degrees (WGS-84)
Formats you'll meet, all of which must parse:
- `445629.03N 0171750.91E`
- `44 56 29.03 N`
- `44°56'29.03"N`
- `N44°56'29"`
- `N445629.03`
- `S25°14’39”`
- degrees + decimal minutes, like `2555.950N` or `34°24.36’N`
- `52∙123` (middle-dot decimal)
- `36,99` (comma decimal)

Tell compact longitude degrees apart by digit count: `0582454W` is 058°, `705113W` is 70°.

Reject minutes > 59 and seconds > 60; treat 60 as rounding and accept it. Reject a coordinate if it's invalid instead of guessing, and log an issue. GeoJSON order is `[lon, lat]`.

## Output format (must match exactly)
Top level:
```json
{
  "type": "FeatureCollection",
  "features": [ ... ],
  "featureTypes": [{"featureType": "aerodrome", "count": 4}, ...],
  "publications": [{
    "cycleId": "2026-10-01-current", "effectiveDate": "2026-10-01",
    "amendmentId": "AIRAC AMDT 009/2026", "sourceKind": "LIVE",
    "ingestedAt": "<ISO-8601 UTC>", "status": "promoted",
    "stats": {"total_documents": 10, "parsed_features": 153, "issue_count": 0, "error_count": 0, "warning_count": 0},
    "sourceUrl": "<eAIP index URL>", "notes": null
  }],
  "issues": [{"publicationId": "...", "severity": "warning|error", "ruleId": "RULE_...", "featureKey": "LOXA/RWY/06-24",
              "section": "LOXA AD 2.12", "message": "...", "rawSnippet": ""}],
  "meta": {"state": "Bosnia and Herzegovina", "continent": "Europe", "websites": [{"name": "...", "url": "..."}], "contact_emails": ["..."]}
}
```
Each feature:
```json
{"type": "Feature",
 "geometry": {"type": "Point", "coordinates": [17.297475, 44.9413972]},
 "properties": {
   "naturalKey": "LQBK", "parentKey": null, "featureType": "aerodrome",
   "publicationId": "2026-10-01-current", "effectiveFrom": "2026-10-01", "effectiveTo": null,
   "sourceClass": "AIP", "temporality": "permanent",
   "contentHash": "<sha256 of the canonical JSON of geometry + field values>",
   "fields": {
     "airportName": {"value": "BANJA LUKA", "unit": null, "source": "eAIP Bosnia and Herzegovina (BHANSA)",
                     "section": "LQBK AD 2.1", "effective_date": "2026-10-01", "retrieved_at": "<ISO UTC>",
                     "source_url": "<exact page/PDF URL>", "parser_version": "1.0", "raw_text": "BANJA LUKA"}
   }}}
```
Every field uses that same envelope `{value, unit, source, section, effective_date, retrieved_at, source_url, parser_version, raw_text}`. `raw_text` is the original text the value was parsed from.

| featureType | geometry | naturalKey / parentKey | fields (value, unit) |
|---|---|---|---|
| aerodrome | Point (ARP) | `LQBK` / null | airportName; arpCoordinates `[lon,lat]`; elevation (401, `FT`) |
| runway | LineString (THR→THR) | `LQBK/RWY/16-34` / `LQBK` | pairDesignator `16-34`; length (`M`); width (`M`); surface (`ASPH`, `CONC`, `GRASS`...) |
| runwayDirection | Point (THR) | `LQBK/RWY/16` / `LQBK/RWY/16-34` | designator; trueBearing (170.01, `DEG`); length; width; surface; thresholdCoordinates |
| navaid | Point | `NAV/DER` (ILS: `NAV/<ICAO>/<IDENT>/ILS`) / null | designator; stationName; navaidType (`VOR/DME`, `NDB`, `DME`...); frequency (112.4); frequencyUnit (`MHZ`/`KHZ`); frequencyRaw; coordinates |
| waypoint | Point | `WPT/ADNAN` / null | designator; coordinates; atsRoutes |
| route | LineString through the points in order | `RTE/L172` / null | designator; routeClass (`ENR 3.2`); waypointSequence (`["WPT/KOMAR","NAV/DER",...]`, raw_text `"WPT/KOMAR -> WPT/DEVUL"`); navigationSpecification (`RNAV` or null) |

Further rules:
- If a runway's thresholds are missing (e.g. a small aerodrome with only a summary sheet), still emit the runway and its directions without geometry, plus a `RULE_RUNWAY_GEOMETRY` warning.
- If a MAG-only bearing is MAG, put it in a separate field; never label it as true.
- Convert feet to metres for runway length/width when the table is in FT.
- A route point must resolve to a waypoint or navaid key that exists in the file. 5-letter names map to `WPT/`; navaid points use their ident in brackets, `NAV/<IDENT>`. Otherwise log `RULE_UNRESOLVED_WAYPOINT`.
- Deduplicate on naturalKey; keep the first and log the duplicate.

## Validation (run after every change, for every file)
- Every feature has all required properties, a valid geometry type for its featureType, `-90≤lat≤90` and `-180≤lon≤180`, and the full field envelope.
- `featureTypes` counts match the features; the publication `stats` match.
- **Runway sanity:**
  - A threshold's true bearing must lie within ±35° of `designator × 10`.
  - The bearing from THR to the opposite THR must match the designator. If it is ~180° off, the thresholds are swapped: log `RULE_THRESHOLD_ORDER`.
  - The THR-to-THR distance must be roughly the published length.
  - Thresholds more than 15 km from the ARP: drop the geometry and log `RULE_THRESHOLD_IMPLAUSIBLE`.
  - ARP more than ~10 km from consistent thresholds: `RULE_ARP_IMPLAUSIBLE`.
- Spot-check a few features per country against the source page by hand (coordinates, frequency, runway length).
- After changing any shared parser, rerun **all** countries and confirm counts didn't drop or regress.

## Workflow per country
1. Run `scrape_eurocontrol_ais.py --continent "<Continent>" --countries "<A>" "<B>"` to get the official links. Always pass `--countries` so other files aren't overwritten.
2. Open the link with curl or a browser. Follow redirects and "eAIP"/"current version" links to the issue in force, and identify the format.
3. If access is blocked by any of the cases in the hard rules: add the country to `UNAVAILABLE` with a precise reason, delete any data file for it, and move on.
4. Otherwise, write `countries/<slug>.py`, reusing `_eaip.py` and the shared parsers where possible. Add the slug to `COUNTRIES[<continent>]` and run `python3 -m aip_scraper.run <slug>`.
5. Validate. Fix parser problems in a generic way, not with per-feature hacks, and log genuine errors in the source as issues.
6. Report a table per country (aerodromes, navaids, routes, runways, waypoints, issues) and list unavailable countries with reasons.

## Countries to do now
Continent: **<fill in>**
Countries: **<fill in list>**
