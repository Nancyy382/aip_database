import { useCallback, useEffect, useMemo, useState } from "react";
import MapView from "./components/MapView";
import Inspector from "./components/Inspector";
import { About, Overview, Register, Sources, Validation } from "./components/Pages";
import { CONTINENT_NAMES, LAYERS, featureLabel, loadCountry, loadIndex, readHash, shortKey, writeHash, type Route } from "./data";
import type { CountryData, CountryEntry, Feature, FeatureType, Index } from "./types";

const VIEWS: { id: Route["view"]; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "map", label: "Map" },
  { id: "register", label: "Register" },
  { id: "validation", label: "Validation" },
  { id: "sources", label: "Sources" },
  { id: "about", label: "About" },
];

export default function App() {
  const [index, setIndex] = useState<Index | null>(null);
  const [route, setRoute] = useState<Route>(readHash);
  const [data, setData] = useState<CountryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState<Record<FeatureType, boolean>>(
    { aerodrome: true, runway: true, runwayDirection: true, navaid: true, waypoint: true, route: true });
  const [focusToken, setFocusToken] = useState(route.feature ? 1 : 0);
  const [query, setQuery] = useState("");
  const [panelOpen, setPanelOpen] = useState(true);

  useEffect(() => { loadIndex().then(setIndex).catch((e) => setError(String(e))); }, []);
  useEffect(() => writeHash(route), [route]);

  const country: CountryEntry | null = useMemo(() => {
    if (!index) return null;
    return index.countries.find((c) => c.slug === route.country) ?? index.countries[0] ?? null;
  }, [index, route.country]);

  useEffect(() => {
    if (!country) return;
    setLoading(true);
    loadCountry(country.path)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [country]);

  const byKey = useMemo(() => new Map((data?.features ?? []).map((f) => [f.properties.naturalKey, f])), [data]);
  const selected: Feature | null = (route.feature && byKey.get(route.feature)) || null;

  const select = useCallback((key: string) => {
    setRoute((r) => ({ ...r, view: "map", feature: key }));
    setFocusToken((t) => t + 1);
  }, []);
  const pickCountry = (slug: string) => setRoute((r) => ({ ...r, country: slug, feature: undefined }));

  const results = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (q.length < 2 || !data) return [];
    const hits: Feature[] = [];
    for (const f of data.features) {
      if (shortKey(f.properties.naturalKey).toUpperCase().startsWith(q) || featureLabel(f).toUpperCase().includes(q)) hits.push(f);
      if (hits.length >= 40) break;
    }
    return hits.sort((a, b) => Number(shortKey(b.properties.naturalKey) === q) - Number(shortKey(a.properties.naturalKey) === q));
  }, [query, data]);

  if (!index) return <div className="splash">{error ?? "Loading…"}</div>;
  const continents = index.continents.filter((c) => index.countries.some((x) => x.continent === c));
  const pub = data?.publications[0];
  const unmapped = data ? data.features.filter((f) => !f.geometry).length : 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-name">eAIP <b>{country?.state.toUpperCase()}</b></span>
          {pub && <span className="pubmeta mono">{pub.cycleId} · {pub.amendmentId} · eff {pub.effectiveDate}</span>}
        </div>
        <div className="pickers">
          <select value={country?.continent} aria-label="Continent"
            onChange={(e) => pickCountry(index.countries.find((c) => c.continent === e.target.value)!.slug)}>
            {continents.map((c) => <option key={c} value={c}>{CONTINENT_NAMES[c] ?? c}</option>)}
          </select>
          <select value={country?.slug} aria-label="Country" onChange={(e) => pickCountry(e.target.value)}>
            {index.countries.filter((c) => c.continent === country?.continent).map((c) =>
              <option key={c.slug} value={c.slug}>{c.state}</option>)}
          </select>
        </div>
        <nav className="tabs" role="tablist">
          {VIEWS.map((v) => (
            <button key={v.id} role="tab" aria-selected={route.view === v.id} className={`tab ${route.view === v.id ? "on" : ""}`}
              onClick={() => setRoute((r) => ({ ...r, view: v.id }))}>
              {v.label}
              {v.id === "register" && data && <span className="tab-count mono">{data.features.length}</span>}
              {v.id === "validation" && data && data.issues.length > 0 && <span className="tab-count mono warn">{data.issues.length}</span>}
            </button>
          ))}
        </nav>
      </header>

      <main className="main">
        <div className={`map-wrap ${route.view === "map" ? "" : "hidden"}`}>
          <MapView country={country} data={data} visible={visible} selected={selected} onSelect={select} focusToken={focusToken} />

          <div className={`float-panel ${panelOpen ? "" : "collapsed"}`}>
            <div className="search">
              <input type="search" placeholder="Search key, ident, name…" value={query} onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && results[0]) { select(results[0].properties.naturalKey); setQuery(""); } }} />
              {results.length > 0 && (
                <ul className="results">
                  {results.map((f) => (
                    <li key={f.properties.naturalKey}>
                      <button onClick={() => { select(f.properties.naturalKey); setQuery(""); }}>
                        <span className="sq" style={{ background: LAYERS.find((l) => l.type === f.properties.featureType)!.color }} />
                        <span className="mono">{f.properties.naturalKey}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <button className="panel-head" onClick={() => setPanelOpen((o) => !o)} aria-expanded={panelOpen}>
              <span>Layers</span><span className="dim">{panelOpen ? "−" : "+"}</span>
            </button>
            {panelOpen && (
              <>
                {LAYERS.map((l) => (
                  <label key={l.type} className="layer">
                    <input type="checkbox" checked={visible[l.type]} onChange={(e) => setVisible((v) => ({ ...v, [l.type]: e.target.checked }))} />
                    <span className="sq" style={{ background: l.color }} />
                    <span className="grow mono">{l.label}</span>
                    <span className="num dim mono">{(country?.counts[l.type] ?? 0).toLocaleString()}</span>
                  </label>
                ))}
                {unmapped > 0 && (
                  <div className="unmapped">
                    <div className="panel-sub">Unmapped · geometry null</div>
                    <button className="link mono" onClick={() => setRoute((r) => ({ ...r, view: "register" }))}>{unmapped} features</button>
                  </div>
                )}
              </>
            )}
          </div>

          {selected && data && route.view === "map" && (
            <Inspector feature={selected} data={data} byKey={byKey} onSelect={select}
              onClose={() => setRoute((r) => ({ ...r, feature: undefined }))} />
          )}
        </div>

        {route.view !== "map" && country && data && (
          <div className="scroll">
            {route.view === "overview" && <Overview country={country} data={data} index={index} onSelect={select} onPickCountry={pickCountry} />}
            {route.view === "register" && <Register country={country} data={data} onSelect={select} />}
            {route.view === "validation" && <Validation country={country} data={data} onSelect={select} />}
            {route.view === "sources" && <Sources country={country} data={data} onSelect={select} />}
            {route.view === "about" && <About index={index} />}
          </div>
        )}
        {loading && <div className="toast">Loading {country?.state}…</div>}
        {error && <div className="toast err">{error}</div>}
      </main>
    </div>
  );
}
