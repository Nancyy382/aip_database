"""Germany - DFS Deutsche Flugsicherung AIXM 5.1/5.1.1 Datasets (https://aip.dfs.de/datasets/).

The DFS datasets REST API at https://aip.dfs.de/datasets/rest/ lists available AIRAC
amendments and their associated AIXM 5.1 datasets. The current amendment valid today
is located dynamically, and the AIXM datasets for airports, runways, navaids, waypoints,
and routes are loaded and parsed.
"""
from datetime import date, datetime

from .. import aixm
from ..common import fetch, fetch_json
from ..features import Collection

REST_INDEX = "https://aip.dfs.de/datasets/rest/"
SOURCE = "AIP Germany (DFS)"


def _find_leaves(d):
    leaves = []
    if d.get("type") == "leaf":
        leaves.append(d)
    for it in d.get("items", []):
        leaves.extend(_find_leaves(it))
    return leaves


def current_amendment():
    meta = fetch_json(REST_INDEX)
    today = date.today()
    candidates = []
    for amdt in meta.get("Amdts", []):
        airac = amdt.get("Metadata", {}).get("airac")
        if not airac:
            continue
        try:
            d = datetime.strptime(airac, "%Y-%m-%d").date()
        except ValueError:
            continue
        candidates.append((d, amdt))
    candidates.sort(key=lambda x: x[0])
    valid = [c for c in candidates if c[0] <= today]
    return valid[-1] if valid else candidates[0]


def scrape(log):
    dt, amdt = current_amendment()
    airac_date = amdt.get("Metadata", {}).get("airac") or dt.isoformat()
    amdt_id = f"AIRAC AMDT {amdt.get('AmdtDate', dt.strftime('%d %b %Y'))}"
    amdt_idx = amdt.get("Amdt", 0)
    base_url = f"https://aip.dfs.de/datasets/rest/{amdt_idx}/"
    log(f"  DFS Amendment: {amdt_id} (effective {airac_date})")

    file_map = {}
    for grp in amdt.get("Metadata", {}).get("datasets", []):
        for leaf in _find_leaves(grp):
            name = leaf.get("name", "")
            for rel in leaf.get("releases", []):
                if rel.get("type") == "AIXM 5.1":
                    file_map[name] = rel.get("filename")

    target_keys = {
        "airports": "ED AirportHeliport",
        "runways": "ED Runway",
        "navaids": "ED Navaids",
        "waypoints": "ED Waypoints",
        "routes": "ED Routes",
    }

    col = Collection(SOURCE, airac_date, amdt_id, base_url)
    db = {}
    for key, dataset_name in target_keys.items():
        fname = file_map.get(dataset_name)
        if not fname:
            log(f"  Warning: dataset {dataset_name} not found in metadata")
            continue
        url = base_url + fname
        log(f"  Loading {dataset_name} ({fname})...")
        data = fetch(url)
        col.documents += 1
        cur = aixm.load(data)
        for tag, items in cur.items():
            db.setdefault(tag, {}).update(items)

    aps = aixm.airports(db)
    for a in aps:
        col.add_aerodrome(a, "AD 2", base_url + file_map[target_keys["airports"]])

    navs = aixm.navaids(db)
    for n in navs:
        col.add_navaid(n, "ENR 4.1", base_url + file_map[target_keys["navaids"]])

    wpts = aixm.designated_points(db)
    for w in wpts:
        col.add_waypoint(w, "ENR 4.4", base_url + file_map[target_keys["waypoints"]])

    pts_by_uuid = {}
    for w in wpts:
        pts_by_uuid[w["uuid"]] = {**w, "key": f"WPT/{w['ident']}"}
    for n in navs:
        pts_by_uuid[n["uuid"]] = {**n, "key": f"NAV/{n['ident']}"}

    rtes = aixm.routes(db, pts_by_uuid)
    for r in rtes:
        col.add_route(r, "ENR 3", base_url + file_map[target_keys["routes"]], lambda p: p.get("key"))

    log(f"  Parsed {len(col.features)} features ({len(col.issues)} issues)")
    return col
