import type { CountryData, Feature, FeatureType, Index } from "./types";

// labels are the feature types of the data model, as the eAIP viewer format names them
export const LAYERS: { type: FeatureType; label: string; color: string }[] = [
  { type: "aerodrome", label: "aerodrome", color: "#c8f031" },
  { type: "navaid", label: "navaid", color: "#38c6f4" },
  { type: "route", label: "route", color: "#38a8f4" },
  { type: "runway", label: "runway", color: "#f4f4f4" },
  { type: "runwayDirection", label: "runwayDirection", color: "#dcdcdc" },
  { type: "waypoint", label: "waypoint", color: "#b77cf6" },
];

export const CONTINENT_NAMES: Record<string, string> = {
  europe: "Europe", africa: "Africa", middle_east: "Middle East",
  north_central_america: "North & Central America", south_america: "South America",
};

export const FIELD_LABELS: Record<string, string> = {
  airportName: "Name", arpCoordinates: "ARP coordinates", elevation: "Elevation", pairDesignator: "Runway",
  length: "Length", width: "Width", surface: "Surface", designator: "Designator", trueBearing: "True bearing",
  magneticBearing: "Magnetic bearing", thresholdCoordinates: "Threshold coordinates", stationName: "Station",
  navaidType: "Type", frequency: "Frequency", frequencyUnit: "Frequency unit", frequencyRaw: "Frequency (as published)",
  coordinates: "Coordinates", atsRoutes: "ATS routes", routeClass: "Section", waypointSequence: "Points",
  navigationSpecification: "Navigation specification", strength: "Strength",
};

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export const loadIndex = () => getJSON<Index>("index.json");

const cache = new Map<string, Promise<CountryData>>();
export function loadCountry(path: string) {
  if (!cache.has(path)) cache.set(path, getJSON<CountryData>(path));
  return cache.get(path)!;
}

export function shortKey(key: string) {
  return key.replace(/^(WPT|NAV|RTE)\//, "");
}

export function featureLabel(f: Feature) {
  const fl = f.properties.fields;
  const name = (fl.airportName?.value ?? fl.stationName?.value) as string | undefined;
  const key = shortKey(f.properties.naturalKey);
  return name ? `${key} · ${name}` : key;
}

export function formatValue(value: unknown, unit: string | null) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value) && value.length === 2 && typeof value[0] === "number") {
    const [lon, lat] = value as number[];
    return `${Math.abs(lat).toFixed(6)}° ${lat < 0 ? "S" : "N"}, ${Math.abs(lon).toFixed(6)}° ${lon < 0 ? "W" : "E"}`;
  }
  if (Array.isArray(value)) return value.join(", ");
  return unit ? `${value} ${unit}` : String(value);
}

function dms(v: number) {
  const a = Math.abs(v), d = Math.floor(a), m = Math.floor((a - d) * 60), s = ((a - d) * 60 - m) * 60;
  return { d, m, s };
}
export function formatLat(v: number) {
  const { d, m, s } = dms(v);
  return `${String(d).padStart(2, "0")}°${String(m).padStart(2, "0")}′${s.toFixed(1).padStart(4, "0")}″${v < 0 ? "S" : "N"}`;
}
export function formatLon(v: number) {
  const { d, m, s } = dms(v);
  return `${String(d).padStart(3, "0")}°${String(m).padStart(2, "0")}′${s.toFixed(1).padStart(4, "0")}″${v < 0 ? "W" : "E"}`;
}

// app state that lives in the URL hash: #/map?c=sweden&f=ESSA
export interface Route { view: "map" | "overview" | "register" | "validation" | "sources" | "about"; country?: string; feature?: string }

export function readHash(): Route {
  const [view, query] = location.hash.replace(/^#\/?/, "").split("?");
  const q = new URLSearchParams(query);
  const v = (["map", "overview", "register", "validation", "sources", "about"].includes(view) ? view : "map") as Route["view"];
  return { view: v, country: q.get("c") ?? undefined, feature: q.get("f") ?? undefined };
}

export function writeHash(r: Route) {
  const q = new URLSearchParams();
  if (r.country) q.set("c", r.country);
  if (r.feature) q.set("f", r.feature);
  const h = `#/${r.view}${q.size ? "?" + q : ""}`;
  if (location.hash !== h) history.replaceState(null, "", h);
}
