"""Scrape AIP features per country into data/<continent>/<state>.json.

Each file is a GeoJSON FeatureCollection in the eAIP viewer format
(see features.py), plus publications/featureTypes/issues.

    python3 -m aip_scraper.run                # every country with a public AIP
    python3 -m aip_scraper.run argentina chile
    python3 -m aip_scraper.run --continent north_central_america
    python3 -m aip_scraper.run --no-cache argentina
"""
import argparse
import importlib
import json
import os
import sys

from . import common

COUNTRIES = {
    "south_america": ["argentina", "chile", "panama", "french_guiana_france", "uruguay", "paraguay", "venezuela",
                      "ecuador", "falkland_islands_malvinas"],
    "north_central_america": ["aruba_netherlands", "bonaire_netherlands", "belize", "bahamas", "bermuda", "cayman_islands",
                              "costa_rica", "cuba", "cura_ao", "dominican_republic", "el_salvador", "french_antilles", "guatemala", "haiti",
                              "honduras", "nicaragua",
                              "saba_netherlands", "saint_eustatius_netherlands", "sint_maarten_netherlands"],
    "europe": ["albania", "armenia", "austria", "belarus", "bosnia_and_herzegovina", "czech_republic",
               "denmark_faeore_islands_greenland", "estonia", "finland", "france", "georgia", "germany",
               "hungary", "iceland", "ireland", "kazakhstan", "kosovo", "latvia", "montenegro", "netherlands",
               "north_macedonia", "norway", "poland", "romania", "serbia", "slovakia", "slovenia",
               "spain_balearic_is_canary_is", "united_kingdom", "uzbekistan", "sweden"],
    "middle_east": ["afghanistan", "bahrain", "iran", "israel", "oman", "qatar", "syria"],
    "africa": ["algeria", "benin", "burkina_faso", "cameroon", "cape_verde", "central_african_republic", "chad",
               "comoros", "congo", "equatorial_guinea", "gabon", "guinea_bissau", "ivory_coast", "libya",
               "madagascar", "mali", "mauritania", "mauritius", "namibia", "niger", "reunion_france", "rwanda",
               "senegal", "south_africa", "south_sudan", "st_helena_united_kingdom", "togo"],
}
# Countries served by a shared scraper need no module of their own: slug -> (shared module, function, args).
# Every other slug has aip_scraper/countries/<slug>.py with scrape(log).
SHARED = {
    # ASECNA eAIP: state number in its menu, ISO alpha-3 code for the border split (see _asecna.py)
    "benin": ("_asecna", "scrape_state", ("01", "BEN")),
    "burkina_faso": ("_asecna", "scrape_state", ("02", "BFA")),
    "cameroon": ("_asecna", "scrape_state", ("03", "CMR")),
    "central_african_republic": ("_asecna", "scrape_state", ("04", "CAF")),
    "chad": ("_asecna", "scrape_state", ("14", "TCD")),
    "comoros": ("_asecna", "scrape_state", ("16", "COM")),
    "congo": ("_asecna", "scrape_state", ("05", "COG")),
    "equatorial_guinea": ("_asecna", "scrape_state", ("08", "GNQ")),
    "gabon": ("_asecna", "scrape_state", ("07", "GAB")),
    # Dutch Caribbean AIXM dataset: aerodromes of the island
    "aruba_netherlands": ("_dutch_caribbean", "scrape_islands", ({"TNCA"},)),
    "bonaire_netherlands": ("_dutch_caribbean", "scrape_islands", ({"TNCB"},)),
    "cura_ao": ("_dutch_caribbean", "scrape_islands", ({"TNCC"},)),
    "saba_netherlands": ("_dutch_caribbean", "scrape_islands", ({"TNCS"},)),
    "saint_eustatius_netherlands": ("_dutch_caribbean", "scrape_islands", ({"TNCE"},)),
    "sint_maarten_netherlands": ("_dutch_caribbean", "scrape_islands", ({"TNCM"},)),
}
CONTINENT_OF = {slug: cont for cont, slugs in COUNTRIES.items() for slug in slugs}
# States whose AIP could not be fetched (checked 2026-10-26); no file is written for them.
UNAVAILABLE = {
    # Africa
    "angola": "AIP not published online; anac.ao does not host or link to an AIP/eAIP",
    "botswana": "Botswana AIP at caab.co.bw requires a registered user account (aip-login / aip-register)",
    "burundi": "AIP not published online; AACB distributes printed amendments by postal subscription",
    "gambia": "eaip.gcaa.aero returns 401 Unauthorized; gcaa.aero TLS certificate is expired",
    "ghana": "Eurocontrol links return 404; GCAA distributes AIP products only via subscription order form",
    "guinea": "Eurocontrol links to Roberts FIR (robertsfir.org); its AIP pages are empty website template shells without AIP text or PDFs",
    "kenya": "Kenya eAIP at eaip.kcaa.or.ke requires a user login; IAIP requires a paid subscription order form",
    "lesotho": "Eurocontrol host civilair.org.ls does not resolve (DNS error)",
    "liberia": "Eurocontrol links to Roberts FIR (robertsfir.org); its AIP pages are empty website template shells without AIP text or PDFs",
    "malawi": "AIP not published online; caa.gov.mw lists contact page only (contact aishq@dca.gov.mw)",
    "morocco": "siamaroc.onda.ma is behind a Cloudflare bot block (403)",
    "mozambique": "AIP not published online; iacm.gov.mz legacy AIS page redirects to home with no AIP",
    "nigeria": "AIP not published online; NAMA requires purchasing AIS products",
    "sao_tome_and_principe": "AIP not published online; enasa.st publishes general airport services only (contact ais.fpst@gmail.com)",
    "seychelles": "AIP not published online; SCAA requires purchase of PDF set for 75 USD (contact ais@saa.sc)",
    "sierra_leone": "Eurocontrol links to Roberts FIR (robertsfir.org); its AIP pages are empty website template shells without AIP text or PDFs",
    "somalia": "aip.scaa.gov.so is behind a Cloudflare bot block (403)",
    "sudan": "AIP not published online; scaa.gov.sd requires application for access to document management system",
    "tanzania": "AIP not published online; TCAA distributes AIP by subscription order form (contact ais@tcaa.go.tz)",
    "tunisia": "AIP not published online; OACA requires a subscriber account ('Espace Professionnel') and document links on the publications portal return 404",
    "uganda": "Uganda eAIP at aim.caa.co.ug/eAIP returns 401 Unauthorized; AIP requires a paid subscription order form",
    "zambia": "AIP not published online; ZACL distributes AIP via order form (contact ais.lusaka@zacl.aero)",
    "zimbabwe": "CAAZ Zimbabwe AIP at caaz.co.zw/aip/ requires an active subscriber login and password",
    # South America
    "brazil": "aisweb.decea.gov.br resets the connection from this network",
    "bolivia": "AIP digital at ais.naabol.gob.bo requires a user code and password",
    "colombia": "eaip-colombia.atnaerocivil.gov.co times out; aerocivil.gov.co downloads are blocked by its WAF (403)",
    "peru": "AIP Digital (extranet.corpac.gob.pe) requires a paid user account from CORPAC AIS",
    "guyana": "AIP not published online; GCAA asks users to contact ais.guyana@civilaviation.gy",
    "suriname": "AIP not published online (cadsur.sr lists contact details only)",
    # Eastern Caribbean eAIP (TTCAA, caa.gov.tt) is behind a login / acquisition form
    "anguilla_united_kingdom": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "antigua_and_barbuda": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "barbados": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "dominica": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "grenada": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "montserrat_united_kingdom": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "saint_kitts_and_nevis": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "saint_lucia": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "saint_vincent_and_grenadines": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "trinidad_and_tobago": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    "virgin_islands_united_kingdom": "Eastern Caribbean eAIP at caa.gov.tt requires a login (eAIP acquisition form)",
    # North & Central America
    "canada": "AIP Canada (ICAO) is not published online; NAV CANADA requires purchase or contact service@navcanada.ca",
    "puerto_rico_united_states": "Eurocontrol lists no AIS website for Puerto Rico (published by the United States)",
    "jamaica": "Jamaica AIP requires registration (aim.jcaa.aero/client/register)",
    "mexico": "AIP México at seneam.gob.mx/AIPMEXICO/aip requires a user login and password",
    "turks_and_caicos_islands_united_kingdom": "TCIAA Turks and Caicos AIP at tciairports.com/aeronautical-information-publication-aip is password-protected ('Enter Password')",
    "united_states": "faa.gov is behind an Akamai bot/WAF block (403 Access Denied)",
    "iraq": "gcaan.gov.iq is behind a Cloudflare block (403)",
    "jordan": "carc.gov.jo times out from this network",
    "kuwait": "dgca.gov.kw AIP PDFs are password-protected (subscription)",
    "lebanon": "beirutairport.gov.lb/zip asks for a password",
    "pakistan": "paa.gov.pk times out from this network",
    "saudi_arabia": "sans.com.sa AIM page has no AIP links; aim.sans.com.sa times out from this network",
    "united_arab_emirates": "GCAA UAE AIP requires a registered account (gcaa.gov.ae sign-in)",
    "yemen": "cama.gov.ye redirects to a control-panel port and times out",
    "azerbaijan": "Eurocontrol lists no AIS website for Azerbaijan",
    "belgium": "ops.skeyes.be returns 403 'Access blocked' (WAF) to this scraper",
    "bulgaria": "BULATSA eAIP APIs return 403 without a registered login",
    "croatia": "eAIP link removed 31.12.2025; access only via the AIM Portal with registration",
    "cyprus": "eAIP host airac.dca.mcw.gov.cy does not resolve (DNS)",
    "ukraine": "aisukraine.net eAIP redirects to a login (subscription to the reserved area)",
    "switzerland": "skyguide publishes the IFR AIP only via skybriefing.com, whose eAIP requires a login",
    "t_rkiye": "dhmi.gov.tr AIP content is served only after a subscriber login with captcha (aipabone@dhmi.gov.tr)",
    # caica.ru-hosted AIPs: the license forbids electronic copying/reproduction without written authorization
    "tajikistan": "caica.ru AIP license forbids electronic copying without written authorization from Tajikairnavigation",
    "turkmenistan": "caica.ru AIP license forbids electronic copying without written authorization from Turkmenhowayollary",
    "d_r_of_congo": "aacrdc.org links no DRC AIP (its 'AIP' link points to the Slovenia Control eAIP)",
    "djibouti": "djibaviationcivile.com AIP page is a JavaScript app with no public document links",
    "egypt": "nansceg.net posts only the latest AIRAC AMDT/SUP PDFs, not the full AIP",
    "eritrea": "Eurocontrol lists no AIS website for Eritrea",
    "eswatini": "eswacaa.co.sz publishes regulations only, no AIP",
    "ethiopia": "ecaa.gov.et AIM page is gone (404); its 'NOTAM & AIP Publications' card has no link",
    "greece": "aisgr.hasp.gov.gr returns 403 'Access Denied' (Akamai/WAF block)",
    "italy": "ENAV Italy AIP requires a registered user account and login ('AIP Request access')",
    "kyrgyzstan": "ansp.kg/aeronautical-information-service is an empty shell with no AIP links (available only in EAD Basic)",
    "lithuania": "ans.lt is behind a Cloudflare bot block (403 Just a moment...)",
    "luxembourg": "ops.skeyes.be (shared Belgium and Luxembourg eAIP) returns 403 'Access blocked' (WAF) to this scraper",
    "malta": "transport.gov.mt is behind a Cloudflare bot block (403 Just a moment...)",
    "moldova": "aim.moldatsa.md is behind a Cloudflare bot block (403 Just a moment...)",
    "portugal_azores_madeira": "ais.nav.pt is behind a Cloudflare bot block (503 Service Unavailable)",
    "russian_federation": "caica.ru requires a CAPTCHA and authorized account (HTTP 401 Unauthorized for AIP downloads)",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("countries", nargs="*", help="country slugs (default: all)")
    ap.add_argument("--continent", choices=sorted(COUNTRIES), help="only this continent")
    ap.add_argument("--data-dir", default=os.path.join(common.ROOT, "data"))
    ap.add_argument("--no-cache", action="store_true", help="download everything again (refreshes .cache/)")
    args = ap.parse_args()
    common.REFRESH = args.no_cache

    failed = []
    todo = args.countries or [s for c, slugs in COUNTRIES.items() if c == (args.continent or c) for s in slugs]
    for slug in todo:
        if slug in UNAVAILABLE:
            print(f"{slug}: skipped - {UNAVAILABLE[slug]}")
            continue
        if slug in SHARED:
            name, func, extra = SHARED[slug]
            module = importlib.import_module(f".countries.{name}", __package__)
            scrape = lambda log, f=getattr(module, func), a=extra: f(*a, log)
        else:
            scrape = importlib.import_module(f".countries.{slug}", __package__).scrape
        path = os.path.join(args.data_dir, CONTINENT_OF[slug], slug + ".json")
        meta = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
            meta = old.get("meta") or {k: old[k] for k in ("state", "continent", "websites", "contact_emails")
                                       if k in old}
        print(f"{slug}:", flush=True)
        try:
            col = scrape(lambda msg: print(msg, flush=True))
        except Exception as e:  # a site is down or changed layout: keep the previous file
            print(f"  !! {slug} failed: {type(e).__name__}: {e}", flush=True)
            failed.append(slug)
            continue
        counts = col.write(path, meta)
        errors = sum(i["severity"] == "error" for i in col.issues)
        print(f"  -> {path} {counts} ({len(col.issues)} issues, {errors} errors)")
    if failed:
        print(f"FAILED ({len(failed)}): {' '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
