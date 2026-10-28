"""Check country files against the eAIP viewer's response validators.

Port of the checks in https://aip.ishu.foo/assets/index-*.js (Fh/wi/Jh/Kh/Lh for
/api/features, $h for /api/feature-types, Wh for /api/publications).

    python3 -m aip_scraper.validate data/south_america/*.json
"""
import json
import math
import sys


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _pos(v):
    return isinstance(v, list) and len(v) == 2 and all(_num(x) for x in v)


def _str_or_null(v):
    return v is None or isinstance(v, str)


def geometry_ok(g):
    if g is None:
        return True
    if not isinstance(g, dict):
        return False
    if g.get("type") == "Point":
        return _pos(g.get("coordinates"))
    if g.get("type") == "LineString":
        return isinstance(g.get("coordinates"), list) and all(_pos(c) for c in g["coordinates"])
    return False


def field_ok(f):
    return (isinstance(f, dict) and "value" in f and _str_or_null(f.get("unit"))
            and all(isinstance(f.get(k), str) for k in ("source", "section", "effective_date",
                                                        "retrieved_at", "parser_version", "raw_text"))
            and _str_or_null(f.get("source_url")))


def properties_ok(p):
    return (isinstance(p, dict)
            and all(isinstance(p.get(k), str) for k in ("naturalKey", "featureType", "publicationId",
                                                        "effectiveFrom", "sourceClass", "temporality",
                                                        "contentHash"))
            and _str_or_null(p.get("parentKey")) and _str_or_null(p.get("effectiveTo"))
            and isinstance(p.get("fields"), dict) and all(field_ok(f) for f in p["fields"].values()))


def validate(data):
    errors = []
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        return ["not a FeatureCollection"]
    keys = set()
    for i, f in enumerate(data["features"]):
        key = (f.get("properties") or {}).get("naturalKey", f"#{i}")
        if f.get("type") != "Feature":
            errors.append(f"{key}: type is not Feature")
        if not geometry_ok(f.get("geometry")):
            errors.append(f"{key}: bad geometry")
        if not properties_ok(f.get("properties")):
            errors.append(f"{key}: bad properties/fields")
        keys.add(key)
    for f in data["features"]:
        parent = f["properties"].get("parentKey")
        if parent and parent not in keys:
            errors.append(f"{f['properties']['naturalKey']}: parentKey {parent} not found")
    for t in data.get("featureTypes", []):
        if not (isinstance(t.get("featureType"), str) and _num(t.get("count")) and t["count"] >= 0):
            errors.append(f"bad featureTypes entry {t}")
    for p in data.get("publications", []):
        if not all(isinstance(p.get(k), str) for k in ("cycleId", "amendmentId", "effectiveDate", "status")):
            errors.append(f"bad publication entry {p}")
    return errors


def main(paths):
    bad = 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if "features" not in data:
            print(f"{path}: no features (not scraped yet)")
            continue
        errors = validate(data)
        bad += bool(errors)
        print(f"{path}: {len(data['features'])} features, "
              + ("OK" if not errors else f"{len(errors)} errors: " + "; ".join(errors[:5])))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
