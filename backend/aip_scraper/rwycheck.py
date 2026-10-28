"""Runway threshold alignment check: python3 -m aip_scraper.rwycheck data/*/*.json

For every runway end, the bearing from its threshold to the opposite threshold must
match the designator (within 35°) and the published bearing (within 25°). Misaligned
ends usually mean swapped or mis-assigned threshold coordinates.
"""
import json
import math
import sys


def bearing(a, b):
    (lon1, lat1), (lon2, lat2) = (map(math.radians, p) for p in (a, b))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.degrees(math.atan2(y, x)) % 360


def diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def check(path):
    ends = {}  # naturalKey -> (runway key, threshold, published bearing)
    for f in json.load(open(path)).get("features", []):
        p = f["properties"]
        if p["featureType"] == "runwayDirection":
            fields = p["fields"]
            published = (fields.get("trueBearing") or fields.get("magneticBearing") or {}).get("value")
            ends[p["naturalKey"]] = (p["parentKey"], f["geometry"] and f["geometry"]["coordinates"], published)
    bad = []
    for key, (runway, thr, published) in ends.items():
        other = next((v[1] for k, v in ends.items() if v[0] == runway and k != key), None)
        if not (thr and other):
            continue
        b = bearing(thr, other)
        if diff(b, int(key.split("/")[-1][:2]) * 10) > 35 or (published is not None and diff(b, published) > 25):
            bad.append((key, published, round(b)))
    return len(ends), sum(1 for v in ends.values() if not v[1]), bad


if __name__ == "__main__":
    for path in sys.argv[1:]:
        n, missing, bad = check(path)
        print(f"{path}: {n} runway ends, {missing} without geometry, misaligned: {bad or 'none'}")
