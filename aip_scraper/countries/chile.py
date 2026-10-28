"""Chile - DGAC IFIS (https://aipchile.dgac.gob.cl/).

The IFIS interactive map (/symfony/map) reads three JSON endpoints that cover
aerodromes, ATS routes and significant points for the whole country:

    POST /api/aerodrome      452 aerodromes/heliports (ICAO, name, ARP, elevation, AIP link)
    POST /api/localAirways   ATS routes with their ordered points
    POST /api/localPoints    significant points (waypoints and navaid positions)

Navaid type/frequency come from AIP GEN 2.5 and runways from the AD 2 PDFs
(the API has neither).
"""
import re
from datetime import datetime

from ..common import LATLON, clean, dms, fetch_json, fetch_text, pdf_text
from ..features import Collection
from ..parsers import freq_unit, parse_aerodrome

BASE = "https://aipchile.dgac.gob.cl"
AIP = BASE + "/dasa/aip_chile_con_contenido/ais/"
GEN_2_5 = AIP + "1 GEN Parte 1/GEN 2 Tablas y Codigos/iGEN 2.5-1 GEN 2.5-4 Radioayudas para la navegacion.pdf"
SOURCE = "AIP Chile (DGAC)"
AD_TYPES = {1: "aerodrome", 3: "aerodrome (military/private)", 7: "heliport"}
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def api(name):
    return fetch_json(f"{BASE}/api/{name}", data=b"")


def ad2_links():
    """AD 2 PDF per international airport, from the AIP Vol I AD index page."""
    page = fetch_text(BASE + "/aip/vol1/seccion/ad")
    links = {}
    for href in re.findall(r'href="([^"]*AD 2a Aeropuertos/[^"]+\.pdf)"', page):
        m = re.search(r"AD 2 ([A-Z]{4})\.pdf$", href)
        if m:
            links[m.group(1)] = href if href.startswith("http") else BASE + href
    return links


# --- GEN 2.5 radio navigation aids ----------------------------------------

TYPE_TOKEN = re.compile(r"\b(T?D?VOR|DME|NDB|ILS|LOC|GP|TACAN)\b")
FREQ = re.compile(r"(\d{3}[.,]\d{1,3}|\d{3,4})\s?(MHZ|KHZ)", re.I)
_UP = "A-ZÀ-ÖØ-Þ"
# city heading in the first column: "PUNTA ARENAS", "SANTIAGO /" (not an ICAO code "SCEL")
CITY = re.compile(rf"^(?!SC[A-Z]{{2}}\b)([{_UP}]{{2,}}(?: [{_UP}]+)*)\s*/?(?:\s{{2,}}|$)")
ICAO = re.compile(r"^\s{0,2}(SC[A-Z]{2})\b\.?")


def parse_gen25(text):
    lines = text.replace("\f", "\n").splitlines()
    out, last_loc = [], {}

    def nearest(regex, i, span=4):
        for d in range(span + 1):
            for j in (i - d, i + d):
                if 0 <= j < len(lines):
                    m = regex.match(lines[j])
                    if m and len(m.group(1)) > 3 and m.group(1) not in (
                            "AIP", "AIS", "VOLUMEN", "AMDT", "GEN", "ESTACION", "STATION", "AIS-CHILE"):
                        return clean(m.group(1))
        return None

    def ident_in(ln, end):
        for m in re.finditer(r"(?<!\S)([A-Z]{2,4}|-)(?!\S)", ln[:end]):
            if m.start() >= 18:
                return m
        return None

    for i, ln in enumerate(lines):
        c = LATLON.search(ln)
        if not c:
            continue
        lat, lon = dms(*c.groups()[0:4]), dms(*c.groups()[4:8])
        id_line, idm = i, ident_in(ln, c.start())
        if not idm and i > 0 and not LATLON.search(lines[i - 1]):
            id_line, idm = i - 1, ident_in(lines[i - 1], len(lines[i - 1]))
        if not idm:
            continue
        col = idm.end()

        def region(j):
            if not 0 <= j < len(lines) or (j != i and LATLON.search(lines[j])):
                return ""
            return lines[j][col: c.start() + 12]

        own = TYPE_TOKEN.findall(region(id_line))
        window = [id_line] if own else [i - 1, i, i + 1]
        # "VOR/" on this line continues with "DME" on the next one
        if own and re.search(r"[A-Z]/(?!\w)", region(id_line)):
            window.append(id_line + 1)
        if own and id_line != i:
            window.append(i)
        types, freq = [], None
        for j in window:
            r = region(j)
            types += [t for t in TYPE_TOKEN.findall(r) if t not in types]
            f = FREQ.search(r)
            if f and not freq:
                freq = f
        if not types:
            continue
        ntype = "/".join(types)
        icao = nearest(ICAO, i)
        ident = idm.group(1)
        name = nearest(CITY, i)
        if "ILS" in types or "LOC" in types or "GP" in types:
            if ident == "-":  # glide path: same ILS as the localizer listed just before it
                ident, name = last_loc.get(icao, (None, None))
                if not ident:
                    continue
            elif icao:
                last_loc[icao] = (ident, name)
            component = "GP" if "GP" in types else "LOC"
            rec_ident, parent = ident, icao
        else:
            component, rec_ident, parent = None, ident, None
        val = freq.group(1).replace(",", ".") if freq else None
        out.append({"ident": rec_ident, "type": ntype, "component": component, "parent": parent,
                    "name": name, "airport": icao,
                    "frequency": float(val) if val else None,
                    "frequency_unit": freq_unit(val, freq.group(2)) if freq else None,
                    "raw_frequency": clean(freq.group(0)) if freq else None,
                    "lat": lat, "lon": lon, "raw_coord": clean(c.group(0))})
    return out


# --- scrape ---------------------------------------------------------------

def scrape(log):
    gen25 = pdf_text(GEN_2_5)
    dates = [datetime(int(y), MONTHS[m], int(d)).date().isoformat()
             for d, m, y in re.findall(r"\b(\d{2}) (JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC) (\d{4})\b", gen25)]
    amdt = max((int(n) for n in re.findall(r"AMDT NR (\d+)", gen25)), default=None)
    col = Collection(SOURCE, max(dates), f"AMDT NR {amdt}" if amdt else "unknown", BASE + "/aip/vol1")

    # navaids (GEN 2.5)
    col.documents += 1
    navaids, seen = [], set()
    for n in parse_gen25(gen25):
        key = (n["parent"], n["ident"], n["component"])
        if key not in seen:
            seen.add(key)
            navaids.append(n)
    for n in navaids:
        if n["component"]:
            key_parent = n["parent"]
            n = {**n, "ident": f"{n['ident']}/{n['component']}"}
            col.add_navaid(n, "GEN 2.5", GEN_2_5, parent=key_parent)
        else:
            col.add_navaid(n, "GEN 2.5", GEN_2_5)
    log(f"  GEN 2.5: {len(navaids)} navaids")

    # significant points
    points = api("localPoints")
    col.documents += 1
    nav_idents = {n["ident"] for n in navaids if not n["component"]}
    for p in points:
        name = p["Punto"].strip()
        if not name or p["Latitud"] is None:
            continue
        if re.fullmatch(r"[A-Z]{2,3}", name):
            if name not in nav_idents:  # navaid known only from the map
                col.add_navaid({"ident": name, "lat": p["Latitud"], "lon": p["Longitud"],
                                "frequency": p["Frecuencia"], "raw_frequency": p["Frecuencia"],
                                "frequency_unit": freq_unit(str(p["Frecuencia"])) if p["Frecuencia"] else None},
                               "ENR 4.1", BASE + "/api/localPoints")
            continue
        col.add_waypoint({"ident": name, "lat": p["Latitud"], "lon": p["Longitud"],
                          "raw_coord": f"{p['Latitud']} {p['Longitud']}"}, "ENR 4.4", BASE + "/api/localPoints")
    log(f"  points: {len(points)}")

    # routes
    airways = api("localAirways")
    col.documents += 1
    for a in airways:
        pts = sorted(a["points"], key=lambda p: p["number"])
        rec = {"designator": a["airway"],
               "points": [{"name": p["point"], "lat": p["latitude"], "lon": p["longitude"]} for p in pts]}
        if len(rec["points"]) < 2:
            continue
        col.add_route(rec, "ENR 3", BASE + "/api/localAirways",
                      lambda p: ("NAV/" if re.fullmatch(r"[A-Z]{2,3}", p["name"]) else "WPT/") + p["name"],
                      nav_spec="RNAV 5" if re.match(r"U?[LMNPQTYZ]\d", a["airway"]) else None)
    log(f"  airways: {len(airways)}")

    # aerodromes (API) + runways (AD 2 PDFs)
    links = ad2_links()
    for a in api("aerodrome"):
        icao = (a["DesignadorOaci"] or "").strip()
        if not icao or a["Latitud"] is None:
            continue
        elev = re.search(r"/\s*(\d+)", a["Elevacion"] or "")
        rec = {"icao": icao, "name": clean(a["Aerodromo"]), "raw_name": a["Aerodromo"],
               "lat": a["Latitud"], "lon": a["Longitud"], "raw_coord": f"{a['Latitud']} {a['Longitud']}",
               "elevation_ft": int(elev.group(1)) if elev else None, "raw_elevation": a["Elevacion"],
               "extra": {"aerodromeType": ("AD 1.3", AD_TYPES.get(a["AerodromoTipoId"])),
                         "iataCode": ("AD 2.1", a["DesignadorIata"] or None),
                         "hoursOperator": ("AD 2.3", a["HorasOperacion"] or None),
                         "trafficPermitted": ("AD 2.2", "IFR / VFR" if a["ProcedimientoPublicado"] else None),
                         "remarks": ("AD 2.2", clean(a["Observaciones"] or "") or None)},
               "runways": []}
        url = a["AipLink"] or BASE + "/api/aerodrome"
        if icao in links:
            col.documents += 1
            try:
                ad2 = parse_aerodrome(pdf_text(links[icao]), icao=icao)
                rec["runways"] = ad2["runways"] if ad2 else []
                url = links[icao]
            except Exception as e:
                col.issue("error", "RULE_SOURCE_UNAVAILABLE", icao, f"{icao} AD 2", str(e))
        col.add_aerodrome(rec, "AD 2", url)
    log(f"  aerodromes: {sum(1 for f in col.features.values() if f['properties']['featureType'] == 'aerodrome')}")
    return col
