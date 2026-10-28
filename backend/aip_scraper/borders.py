"""Country borders (Natural Earth 1:50m admin-0) for states that share one AIP.

Only used to decide which country a shared waypoint lies in (ASECNA publishes one
ENR 3 / ENR 4.4 for 17 states); no aeronautical data comes from here.
"""
import json

from .common import fetch

URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/"
       "geojson/ne_50m_admin_0_countries.geojson")


def _rings(geometry):
    polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    return [poly for poly in polys]


def country(iso3):
    """List of polygons (outer ring + holes) for an ISO 3166-1 alpha-3 code."""
    for f in json.loads(fetch(URL))["features"]:
        if iso3 in (f["properties"].get("ADM0_A3"), f["properties"].get("ISO_A3")):
            return _rings(f["geometry"])
    raise KeyError(iso3)


def _in_ring(lon, lat, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def contains(polygons, lon, lat):
    return any(_in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:])
               for poly in polygons)
