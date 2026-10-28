"""Falkland Islands (Malvinas) - Falkland Islands Government Civil Aviation
(https://www.gov.fk/civilaviation/aip/information/; the old falklands.gov.fk no longer resolves).

The AIP is three PDFs (GEN, ENR, AD) linked from the information page. ENR 4.4 uses
degrees + decimal minutes ("5034.60S 06033.00W", converted by common.normalize_coords); ENR 4.1 uses hemisphere-first
coordinates with a middle dot as decimal point ("S514926∙67 / W0582724.98"), which
common.normalize_coords turns into "514926.67S / 0582724.98W".
Mount Pleasant (EGYP) is military and only published by the UK MOD (AIDU).
"""
import re
from datetime import datetime

from ..common import LAT, LON, clean, fetch_text, lat_of, lon_of, pdf_text
from ..features import Collection
from ..parsers import parse_aerodrome, parse_routes, parse_waypoints, point_key

PAGE = "https://www.gov.fk/civilaviation/aip/information/"
SOURCE = "AIP Falkland Islands (FIG Civil Aviation)"
MONTHS = {m: i for i, m in enumerate(["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                                      "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], 1)}


def documents():
    page = fetch_text(PAGE)
    links = re.findall(r'href="([^"]+\.pdf)"', page)
    pick = lambda part: next(u for u in links if re.search(rf"FI_AIP_{part}_", u))
    return pick("ENR"), pick("AD")


def parse_navaids(text):
    """ENR 4.1: type/ID/frequency on (or just above) the latitude line, longitude on the next line."""
    lines = text.splitlines()
    out = []
    for i, ln in enumerate(lines[:-1]):
        la = LAT.search(ln)
        lo = None
        for j in range(i + 1, min(i + 6, len(lines))):
            if LAT.search(lines[j]):
                break  # next aid's latitude: this one has no longitude
            lo = LON.search(lines[j])
            if lo:
                break
        if not (la and lo and la.start() > 40):
            continue
        # the type/ID sit on the latitude line or the line just below/above it
        t = next((m for j in (i, i + 1, i - 1) if 0 <= j < len(lines)
                  for m in [re.search(r"\b(TACAN|DVOR|NDB|Localiser|Glidepath)\b\s+([A-Z]{2,3}\b)?", lines[j])] if m), None)
        context = " ".join(lines[max(0, i - 1): i + 2])
        if not t:
            continue  # radars (WATCHMAN, RPAR) and the UHF/VHF stations are not navaids
        kind = t.group(1)
        ident = t.group(2) or ("I-MP" if kind in ("Localiser", "Glidepath") else None)
        # frequency column only (cols ~20-50): the coordinates further right also contain "ddd.dd"
        freq_text = " ".join(l[20:52] for l in lines[max(0, i - 1): i + 3])
        f = re.search(r"(?<![\d.])(\d{3}\.\d+)\s*(MHZ|KHZ)?", freq_text, re.I)
        freq = float(f.group(1)) if f else None
        unit = "KHZ" if kind == "NDB" else "MHZ"  # NDB SA is printed "305.00MHz" in the AIP; NDBs are kHz
        out.append({"ident": ident, "type": {"Localiser": "ILS/LOC", "Glidepath": "ILS/GP"}.get(kind, kind),
                    "component": {"Localiser": "LOC", "Glidepath": "GP"}.get(kind),
                    "frequency": freq, "frequency_unit": unit if freq else None,
                    "raw_frequency": clean(f.group(0)) if f else None,
                    "lat": lat_of(la), "lon": lon_of(lo), "raw_coord": f"{la.group(0)} {lo.group(0)}"})
    return out


def scrape(log):
    enr_url, ad_url = documents()
    enr, ad = pdf_text(enr_url), pdf_text(ad_url)
    v = re.search(r"Version ([\d.]+) (" + "|".join(MONTHS) + r") (\d{4})", enr)
    eff = datetime(int(v.group(3)), MONTHS[v.group(2)], 1).date().isoformat() if v else "unknown"
    col = Collection(SOURCE, eff, f"ENR Version {v.group(1)}" if v else "unknown", PAGE)
    col.documents += 2

    # ENR 4.4 prints degrees + decimal minutes; normalize_coords has already turned them into DMS
    for w in parse_waypoints(enr[enr.find("ENR 4.4 – NAME"): enr.find("ENR 4.5 – AERONAUTICAL")]):
        col.add_waypoint(w, "ENR 4.4", enr_url)

    e41 = enr[enr.find("ENR 4.1 – RADIO"): enr.find("ENR 4.2 – SPECIAL")]
    for n in parse_navaids(e41):
        if n["component"]:  # ILS components at Mount Pleasant
            # no EGYP aerodrome feature exists (see issue below), so no parentKey either
            col.add_navaid({**n, "ident": f"EGYP/{n['ident']}/{n['component']}"}, "ENR 4.1", enr_url)
        else:
            col.add_navaid(n, "ENR 4.1", enr_url)

    for r in parse_routes(enr[enr.find("ENR 3.1 – LOWER"): enr.find("ENR 3.6 – EN-ROUTE")]):
        col.add_route(r, "ENR 3", enr_url, lambda p: point_key(p["name"]),
                      nav_spec="RNAV" if r["designator"].startswith(("UT", "T")) else None)

    a = parse_aerodrome(ad)
    if a:
        col.add_aerodrome(a, "AD 2", ad_url)
    col.issue("warning", "RULE_SOURCE_UNAVAILABLE", "EGYP", "AD 2",
              "Mount Pleasant (EGYP) is military; its AD 2 is only in the UK MOD AIP (aidu.mod.uk), "
              "which refuses connections from this network")
    return col
