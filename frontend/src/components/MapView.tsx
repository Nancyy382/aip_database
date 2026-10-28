import { useEffect, useRef } from "react";
import maplibregl, { type GeoJSONSource, type MapLayerMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { LAYERS, featureLabel } from "../data";
import type { CountryData, CountryEntry, Feature, FeatureType } from "../types";

// Basemap: OpenFreeMap's free "dark" vector style (no key, no limits), unless frontend/.env sets
// VITE_BASEMAP_URL to another raster tile service (see .env.example).
const TILE_URL: string | undefined = import.meta.env.VITE_BASEMAP_URL;
const FONTS = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf";
const BASEMAP: string | maplibregl.StyleSpecification = TILE_URL
  ? {
      version: 8,
      glyphs: FONTS,
      sources: {
        base: { type: "raster", tileSize: 256, maxzoom: 19,
                tiles: TILE_URL.includes("{s}") ? ["a", "b", "c", "d"].map((s) => TILE_URL.replace("{s}", s)) : [TILE_URL],
                attribution: import.meta.env.VITE_BASEMAP_ATTRIBUTION ?? "© OpenStreetMap contributors" },
      },
      layers: [{ id: "base", type: "raster", source: "base" }],
    }
  : "https://tiles.openfreemap.org/styles/dark";

const color = (t: FeatureType) => LAYERS.find((l) => l.type === t)!.color;
const POINT_RADIUS: Record<string, number> = { aerodrome: 6, navaid: 6, waypoint: 3, runwayDirection: 3 };
const ACCENT = "#c8f031";

function toCollection(data: CountryData, type: FeatureType): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: data.features
      .filter((f) => f.properties.featureType === type && f.geometry)
      .map((f) => ({
        type: "Feature",
        geometry: f.geometry as GeoJSON.Geometry,
        properties: { key: f.properties.naturalKey, label: featureLabel(f).split(" · ")[0] },
      })),
  };
}

interface Props {
  country: CountryEntry | null;
  data: CountryData | null;
  visible: Record<FeatureType, boolean>;
  selected: Feature | null;
  onSelect: (key: string) => void;
  focusToken: number;
}

export default function MapView({ country, data, visible, selected, onSelect, focusToken }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef<Promise<void>>();
  const popup = useRef(new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, className: "hover-pop" }));

  // create the map once, with an empty source + layers per feature type
  useEffect(() => {
    const m = new maplibregl.Map({ container: el.current!, style: BASEMAP, center: [15, 30], zoom: 2.5, attributionControl: { compact: true } });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "nautical" }), "bottom-right");
    map.current = m;
    // add our layers as soon as the style is parsed; "load" would also wait for basemap tiles
    ready.current = new Promise((resolve) => m.once("style.load", () => {
      const empty: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
      for (const t of ["route", "runway", "waypoint", "runwayDirection", "navaid", "aerodrome"] as FeatureType[]) {
        m.addSource(t, { type: "geojson", data: empty });
        if (t === "route" || t === "runway") {
          m.addLayer({
            id: t, type: "line", source: t,
            paint: t === "route"
              ? { "line-color": color(t), "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1, 9, 2], "line-opacity": 0.8, "line-dasharray": [3, 2] }
              : { "line-color": color(t), "line-width": ["interpolate", ["linear"], ["zoom"], 6, 2, 14, 8] },
          });
        } else {
          m.addLayer({
            id: t, type: "circle", source: t,
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, POINT_RADIUS[t] * 0.7, 10, POINT_RADIUS[t] * 1.4],
              // navaids are hollow rings, everything else filled dots
              "circle-color": t === "navaid" ? "rgba(0,0,0,0)" : color(t),
              "circle-stroke-color": t === "navaid" ? color(t) : "#000000",
              "circle-stroke-width": t === "navaid" ? 2 : t === "aerodrome" ? 1.5 : 0.5,
            },
          });
        }
        m.addLayer({
          id: `${t}-label`, type: "symbol", source: t, minzoom: t === "aerodrome" ? 5 : t === "route" ? 7 : 8,
          layout: {
            "text-field": ["get", "label"], "text-size": 11, "text-font": ["Noto Sans Regular"],
            "text-offset": [0, 1.1], "text-anchor": "top", "symbol-placement": t === "route" ? "line" : "point",
            "text-optional": true,
          },
          paint: { "text-color": color(t === "runway" ? "aerodrome" : t), "text-halo-color": "#000000", "text-halo-width": 1.4 },
        });
        m.on("click", t, (e: MapLayerMouseEvent) => onSelectRef.current(e.features![0].properties!.key as string));
        m.on("mouseenter", t, (e: MapLayerMouseEvent) => {
          m.getCanvas().style.cursor = "pointer";
          popup.current.setLngLat(e.lngLat).setText(e.features![0].properties!.label as string).addTo(m);
        });
        m.on("mousemove", t, (e: MapLayerMouseEvent) => popup.current.setLngLat(e.lngLat).setText(e.features![0].properties!.label as string));
        m.on("mouseleave", t, () => { m.getCanvas().style.cursor = ""; popup.current.remove(); });
      }
      m.addSource("selected", { type: "geojson", data: empty });
      m.addLayer({ id: "selected-line", type: "line", source: "selected", filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": ACCENT, "line-width": 6, "line-opacity": 0.55 } });
      m.addLayer({ id: "selected-point", type: "circle", source: "selected", filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 14, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": ACCENT, "circle-stroke-width": 2.5 } });
      resolve();
    }));
    return () => m.remove();
  }, []);

  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // new country: replace the sources and fit its extent
  useEffect(() => {
    if (!data) return;
    ready.current!.then(() => {
      const m = map.current!;
      for (const { type } of LAYERS) (m.getSource(type) as GeoJSONSource).setData(toCollection(data, type));
      if (country?.bbox && !selected) m.fitBounds(country.bbox, { padding: 40, duration: 0, maxZoom: 9 });
    });
  }, [data]);

  useEffect(() => {
    ready.current!.then(() => {
      for (const { type } of LAYERS) {
        for (const id of [type, `${type}-label`]) map.current!.setLayoutProperty(id, "visibility", visible[type] ? "visible" : "none");
      }
    });
  }, [visible]);

  // highlight (and on request, fly to) the selected feature
  useEffect(() => {
    ready.current!.then(() => {
      const m = map.current!;
      const geom = selected?.geometry;
      (m.getSource("selected") as GeoJSONSource).setData({
        type: "FeatureCollection", features: geom ? [{ type: "Feature", geometry: geom as GeoJSON.Geometry, properties: {} }] : [],
      });
      if (!geom || !focusToken) return;
      const duration = focusToken === 1 ? 0 : 600;  // opening a shared link: jump, don't animate
      if (geom.type === "Point") m.flyTo({ center: geom.coordinates, zoom: Math.max(m.getZoom(), 10), duration });
      else {
        const b = new maplibregl.LngLatBounds();
        geom.coordinates.forEach((c) => b.extend(c));
        m.fitBounds(b, { padding: 60, duration, maxZoom: 14 });
      }
    });
  }, [selected, focusToken]);

  return <div ref={el} className="map" />;
}
