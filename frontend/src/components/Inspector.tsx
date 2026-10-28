import { useEffect, useState } from "react";
import { FIELD_LABELS, LAYERS, formatValue, shortKey } from "../data";
import type { CountryData, Feature } from "../types";

interface Props {
  feature: Feature;
  data: CountryData;
  byKey: Map<string, Feature>;
  onSelect: (key: string) => void;
  onClose: () => void;
}

export default function Inspector({ feature, data, byKey, onSelect, onClose }: Props) {
  const p = feature.properties;
  const layer = LAYERS.find((l) => l.type === p.featureType)!;
  const names = Object.keys(p.fields);
  const [active, setActive] = useState(names[0]);
  useEffect(() => setActive(Object.keys(feature.properties.fields)[0]), [feature]);
  const field = p.fields[active] ?? p.fields[names[0]];
  const issues = data.issues.filter((i) => i.featureKey === p.naturalKey || i.featureKey.startsWith(p.naturalKey + "/"));
  const pub = data.publications[0];

  return (
    <aside className="inspector" aria-label="Feature inspector">
      <header className="insp-head">
        <div>
          <span className="type-pill" style={{ color: layer.color }}>{p.featureType}</span>
          <h2 className="mono">{p.naturalKey}</h2>
          <div className="mono dim small">
            {p.parentKey && <>parent <button className="link mono" onClick={() => onSelect(p.parentKey!)}>{p.parentKey}</button> · </>}
            eff {p.effectiveFrom}{!feature.geometry && <span className="warn"> · no geometry</span>}
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
      </header>

      {p.featureType === "aerodrome" && <RunwayTable icao={p.naturalKey} data={data} onSelect={onSelect} />}

      <div className="fields" role="list">
        {names.map((name) => {
          const f = p.fields[name];
          const seq = name === "waypointSequence" && Array.isArray(f.value);
          return (
            <div key={name} role="listitem" className={`frow ${name === active ? "on" : ""}`} onClick={() => setActive(name)}>
              <div className="fk">{FIELD_LABELS[name] ?? name}</div>
              <div className="fv">
                {seq ? (
                  <div className="chips">
                    {(f.value as string[]).map((k, i) => (
                      <button key={i} className={`chip ${byKey.has(k) ? "" : "missing"}`} title={byKey.has(k) ? k : `${k} is not in this country's data`}
                        onClick={(e) => { e.stopPropagation(); onSelect(k); }}>{shortKey(k)}</button>
                    ))}
                  </div>
                ) : (
                  <span className="val">{formatValue(f.value, null)}{f.unit && <span className="unit"> {f.unit}</span>}</span>
                )}
                <div className="fmeta mono">{f.section} · eff {f.effective_date}</div>
              </div>
            </div>
          );
        })}
      </div>

      {field && (
        <section className="prov">
          <h3>Provenance <span className="dim">· {FIELD_LABELS[active] ?? active}</span></h3>
          <dl>
            <dt>Source</dt><dd>{field.source}</dd>
            <dt>Section</dt><dd className="mono">{field.section}</dd>
            <dt>Effective date</dt><dd className="mono">{field.effective_date}</dd>
            <dt>Retrieved at</dt><dd className="mono">{field.retrieved_at}</dd>
            <dt>Source URL</dt><dd className="break">{field.source_url
              ? <a href={field.source_url} target="_blank" rel="noopener noreferrer">{field.source_url}</a> : "—"}</dd>
            <dt>Parser version</dt><dd className="mono">{field.parser_version}</dd>
            <dt>Publication</dt><dd className="mono">{pub?.cycleId} · {pub?.amendmentId}</dd>
          </dl>
          <div className="raw-label">Raw text</div>
          <pre className="raw">{field.raw_text === null || field.raw_text === undefined || field.raw_text === "" ? "—" : String(field.raw_text)}</pre>
        </section>
      )}

      {issues.length > 0 && (
        <section>
          <h3>Issues</h3>
          {issues.map((i, n) => (
            <div key={n} className={`issue sev-${i.severity}`}>
              <div className="mono">{i.ruleId}</div>
              <div>{i.message}</div>
            </div>
          ))}
        </section>
      )}

      <div className="hash mono dim">contentHash {p.contentHash.slice(0, 16)}…</div>
    </aside>
  );
}

function RunwayTable({ icao, data, onSelect }: { icao: string; data: CountryData; onSelect: (k: string) => void }) {
  const runways = data.features.filter((f) => f.properties.featureType === "runway" && f.properties.parentKey === icao);
  if (!runways.length) return null;
  return (
    <section>
      <h3>Runways</h3>
      <table className="table compact">
        <thead><tr><th>RWY</th><th>Dimensions</th><th>Surface</th><th>Strength</th><th>Ends · true brg</th></tr></thead>
        <tbody>
          {runways.map((r) => {
            const f = r.properties.fields;
            const ends = data.features.filter((d) => d.properties.parentKey === r.properties.naturalKey);
            return (
              <tr key={r.properties.naturalKey} className="clickable" onClick={() => onSelect(r.properties.naturalKey)}>
                <td className="mono">{String(f.pairDesignator?.value ?? "")}</td>
                <td className="mono">{f.length ? `${f.length.value} × ${f.width?.value ?? "?"} m` : "—"}</td>
                <td>{String(f.surface?.value ?? "—")}</td>
                <td className="mono small">{String(f.strength?.value ?? "—")}</td>
                <td>
                  {ends.map((e) => (
                    <button key={e.properties.naturalKey} className="chip" onClick={(ev) => { ev.stopPropagation(); onSelect(e.properties.naturalKey); }}>
                      {String(e.properties.fields.designator?.value)}
                      {e.properties.fields.trueBearing?.value != null ? ` · ${e.properties.fields.trueBearing.value}°` : ""}
                    </button>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
