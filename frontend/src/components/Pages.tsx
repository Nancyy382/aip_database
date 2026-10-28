import { useMemo, useState } from "react";
import { CONTINENT_NAMES, LAYERS } from "../data";
import type { CountryData, CountryEntry, Index } from "../types";

interface CountryProps {
  country: CountryEntry;
  data: CountryData;
  onSelect: (key: string) => void;
}

export function Overview({ country, data, index, onPickCountry }: CountryProps & { index: Index; onPickCountry: (slug: string) => void }) {
  const pub = data.publications[0];
  const noGeom = data.features.filter((f) => !f.geometry).length;
  const siblings = index.countries.filter((c) => c.continent === country.continent);
  const totals = LAYERS.map((l) => siblings.reduce((s, c) => s + (c.counts[l.type] ?? 0), 0));
  return (
    <div className="page">
      <header className="page-head">
        <div className="eyebrow">{CONTINENT_NAMES[country.continent] ?? country.continent}</div>
        <h1>{country.state}</h1>
        <p className="dim">
          {pub?.amendmentId} · effective {pub?.effectiveDate} · ingested {pub?.ingestedAt?.slice(0, 16).replace("T", " ")} UTC
        </p>
      </header>

      <div className="stat-grid">
        {LAYERS.map((l) => (
          <div className="stat" key={l.type}>
            <span className="dot" style={{ background: l.color }} />
            <div className="stat-n">{(country.counts[l.type] ?? 0).toLocaleString()}</div>
            <div className="stat-l">{l.label}</div>
          </div>
        ))}
        <div className="stat"><div className="stat-n">{pub?.stats.total_documents ?? "—"}</div><div className="stat-l">Source documents</div></div>
        <div className="stat"><div className="stat-n">{noGeom}</div><div className="stat-l">Without geometry</div></div>
        <div className="stat"><div className={`stat-n ${data.issues.length ? "warn" : ""}`}>{data.issues.length}</div><div className="stat-l">Issues</div></div>
      </div>

      {data.meta && (
        <section className="card">
          <h3>Publisher</h3>
          <ul className="plain">
            {data.meta.websites.map((w) => <li key={w.url}><a href={w.url} target="_blank" rel="noopener noreferrer">{w.name}</a> <span className="dim mono">{w.url}</span></li>)}
            {data.meta.contact_emails.map((e) => <li key={e} className="dim">{e}</li>)}
          </ul>
        </section>
      )}

      <section className="card">
        <h3>{CONTINENT_NAMES[country.continent] ?? country.continent}: {siblings.length} countries</h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Country</th>{LAYERS.map((l) => <th key={l.type} className="num">{l.label}</th>)}<th className="num">Issues</th><th>Effective</th></tr>
            </thead>
            <tbody>
              {siblings.map((c) => (
                <tr key={c.slug} className={`clickable ${c.slug === country.slug ? "current" : ""}`} onClick={() => onPickCountry(c.slug)}>
                  <td>{c.state}</td>
                  {LAYERS.map((l) => <td key={l.type} className="num">{(c.counts[l.type] ?? 0).toLocaleString()}</td>)}
                  <td className="num">{c.issues}</td>
                  <td className="mono dim">{c.effectiveDate}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr><td>Total</td>{totals.map((t, i) => <td key={i} className="num">{t.toLocaleString()}</td>)}<td className="num">{siblings.reduce((s, c) => s + c.issues, 0)}</td><td /></tr>
            </tfoot>
          </table>
        </div>
      </section>
    </div>
  );
}

export function Validation({ data, onSelect }: CountryProps) {
  const [rule, setRule] = useState<string | null>(null);
  const byRule = useMemo(() => {
    const m = new Map<string, number>();
    data.issues.forEach((i) => m.set(i.ruleId, (m.get(i.ruleId) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [data]);
  const shown = data.issues.filter((i) => !rule || i.ruleId === rule);
  return (
    <div className="page">
      <header className="page-head">
        <h1>Validation</h1>
        <p className="dim">Checks run while parsing: coordinates, runway geometry (threshold order, bearing vs designator, distance from the ARP), route points resolved against the national index, duplicates.</p>
      </header>
      {data.issues.length === 0 ? <div className="card ok">No issues for this publication.</div> : (
        <>
          <div className="chips big">
            <button className={`chip ${rule ? "" : "on"}`} onClick={() => setRule(null)}>All · {data.issues.length}</button>
            {byRule.map(([r, n]) => <button key={r} className={`chip ${rule === r ? "on" : ""}`} onClick={() => setRule(r)}>{r} · {n}</button>)}
          </div>
          <div className="card table-wrap">
            <table className="table">
              <thead><tr><th>Severity</th><th>Rule</th><th>Feature</th><th>Section</th><th>Message</th></tr></thead>
              <tbody>
                {shown.map((i, n) => (
                  <tr key={n} className="clickable" onClick={() => onSelect(i.featureKey)}>
                    <td className={`sev-${i.severity}`}>{i.severity}</td>
                    <td className="mono">{i.ruleId}</td>
                    <td className="mono">{i.featureKey}</td>
                    <td className="dim">{i.section}</td>
                    <td>{i.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export function Sources({ data }: CountryProps) {
  // every source document, with the sections and number of fields taken from it
  const docs = useMemo(() => {
    const m = new Map<string, { sections: Set<string>; fields: number; types: Set<string> }>();
    for (const f of data.features) {
      for (const fl of Object.values(f.properties.fields)) {
        if (!fl.source_url) continue;
        const d = m.get(fl.source_url) ?? { sections: new Set(), fields: 0, types: new Set() };
        d.sections.add(fl.section); d.fields++; d.types.add(f.properties.featureType);
        m.set(fl.source_url, d);
      }
    }
    return [...m.entries()].sort((a, b) => b[1].fields - a[1].fields);
  }, [data]);
  const pub = data.publications[0];
  return (
    <div className="page">
      <header className="page-head">
        <h1>Sources</h1>
        <p className="dim">Every value keeps the URL of the AIP page or PDF it was read from, the AIP section and the text as published. Publication: <a href={pub?.sourceUrl} target="_blank" rel="noopener noreferrer">{pub?.sourceUrl}</a></p>
      </header>
      <div className="card table-wrap">
        <table className="table">
          <thead><tr><th>Document</th><th>Sections</th><th>Layers</th><th className="num">Values</th></tr></thead>
          <tbody>
            {docs.map(([url, d]) => (
              <tr key={url}>
                <td className="break"><a href={url} target="_blank" rel="noopener noreferrer">{decodeURIComponent(url.split("/").pop() || url)}</a></td>
                <td className="dim">{[...d.sections].slice(0, 4).join(", ")}{d.sections.size > 4 ? ` +${d.sections.size - 4}` : ""}</td>
                <td className="dim">{[...d.types].join(", ")}</td>
                <td className="num">{d.fields.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function About({ index }: { index: Index }) {
  const total = index.countries.length;
  return (
    <div className="page prose">
      <header className="page-head">
        <h1>About this data</h1>
        <p className="dim">{total} countries · {index.continents.map((c) => CONTINENT_NAMES[c] ?? c).join(", ")}</p>
      </header>
      <section className="card">
        <h3>Where it comes from</h3>
        <p>Each country starts from its entry on EUROCONTROL's “AIS online” list. The scraper follows that link to the state's official AIP or eAIP, picks the issue in force today, and reads the sections below. Nothing is taken from third-party databases.</p>
        <ul>
          <li><b>Waypoints</b> — ENR 4.4 significant points</li>
          <li><b>Navaids</b> — ENR 4.1 radio navigation aids</li>
          <li><b>Routes</b> — ENR 3 ATS routes, as ordered point sequences</li>
          <li><b>Aerodromes</b> — AD 2.1 / 2.2 name, reference point, elevation</li>
          <li><b>Runways and thresholds</b> — AD 2.12 designators, dimensions, surface, bearings, threshold coordinates</li>
        </ul>
      </section>
      <section className="card">
        <h3>How it is checked</h3>
        <p>Coordinates are normalised from the many formats AIPs use (DMS, decimal minutes, hemisphere-first, comma decimals) and rejected when out of range. Runway ends must match their designator and published bearing; thresholds far from the reference point are dropped. Route points must resolve to a published waypoint or navaid. Anything that fails is listed under Validation rather than silently fixed.</p>
      </section>
      <section className="card">
        <h3>Not for navigation</h3>
        <p>This is a parsed copy for analysis and visualisation. Always use the official AIP and current NOTAM for flight planning.</p>
      </section>
    </div>
  );
}

export function Register({ data, onSelect }: CountryProps) {
  const [type, setType] = useState<string>("all");
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const needle = q.trim().toUpperCase();
    return data.features.filter((f) =>
      (type === "all" || f.properties.featureType === type) &&
      (!needle || f.properties.naturalKey.toUpperCase().includes(needle) ||
        String(f.properties.fields.airportName?.value ?? f.properties.fields.stationName?.value ?? "").toUpperCase().includes(needle)));
  }, [data, type, q]);
  const shown = rows.slice(0, 500);
  return (
    <div className="page">
      <header className="page-head">
        <h1>Register</h1>
        <p className="dim">Every feature in this publication, keyed by its natural key. Click a row to open it on the map.</p>
      </header>
      <div className="toolbar">
        <div className="chips big">
          <button className={`chip ${type === "all" ? "on" : ""}`} onClick={() => setType("all")}>all · {data.features.length}</button>
          {data.featureTypes.map((t) => (
            <button key={t.featureType} className={`chip ${type === t.featureType ? "on" : ""}`} onClick={() => setType(t.featureType)}>
              {t.featureType} · {t.count}
            </button>
          ))}
        </div>
        <input type="search" placeholder="Filter by key or name…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="card table-wrap">
        <table className="table">
          <thead><tr><th>naturalKey</th><th>featureType</th><th>parentKey</th><th>Name / designator</th><th>Geometry</th><th>Effective</th></tr></thead>
          <tbody>
            {shown.map((f) => {
              const p = f.properties, fl = p.fields;
              const name = fl.airportName?.value ?? fl.stationName?.value ?? fl.designator?.value ?? fl.pairDesignator?.value ?? "";
              return (
                <tr key={p.naturalKey} className="clickable" onClick={() => onSelect(p.naturalKey)}>
                  <td className="mono">{p.naturalKey}</td>
                  <td className="mono dim">{p.featureType}</td>
                  <td className="mono dim">{p.parentKey ?? "—"}</td>
                  <td>{String(name)}</td>
                  <td className={`mono ${f.geometry ? "dim" : "warn"}`}>{f.geometry?.type ?? "null"}</td>
                  <td className="mono dim">{p.effectiveFrom}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length > shown.length && <p className="dim small">Showing 500 of {rows.length.toLocaleString()} — narrow the filter to see more.</p>}
      </div>
    </div>
  );
}
