import fs from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Country files live in ../data/<continent>/<country>.json (written by the scraper).
const DATA = path.resolve(__dirname, "../data");
const CONTINENTS = (process.env.AIP_CONTINENTS ?? "europe").split(",");

type Entry = {
  slug: string; continent: string; state: string; path: string;
  counts: Record<string, number>; issues: number; effectiveDate?: string; amendmentId?: string;
  sourceUrl?: string; bbox: [number, number, number, number] | null;
};

function buildIndex() {
  const countries: Entry[] = [];
  for (const continent of CONTINENTS) {
    const dir = path.join(DATA, continent);
    if (!fs.existsSync(dir)) continue;
    for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".json")).sort()) {
      const d = JSON.parse(fs.readFileSync(path.join(dir, file), "utf8"));
      if (!d.features?.length) continue;
      const pub = d.publications?.[0] ?? {};
      let bbox: Entry["bbox"] = null;
      for (const f of d.features) {
        if (f.geometry?.type !== "Point") continue;
        const [x, y] = f.geometry.coordinates;
        bbox = bbox ? [Math.min(bbox[0], x), Math.min(bbox[1], y), Math.max(bbox[2], x), Math.max(bbox[3], y)] : [x, y, x, y];
      }
      countries.push({
        slug: file.slice(0, -5), continent,
        state: d.meta?.state ?? file.slice(0, -5).replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase()),
        path: `data/${continent}/${file}`,
        counts: Object.fromEntries((d.featureTypes ?? []).map((t: { featureType: string; count: number }) => [t.featureType, t.count])),
        issues: d.issues?.length ?? 0,
        effectiveDate: pub.effectiveDate, amendmentId: pub.amendmentId, sourceUrl: pub.sourceUrl, bbox,
      });
    }
  }
  return { continents: CONTINENTS, countries };
}

// Dev: serve /index.json and /data/** from ../data. Build: emit them into dist/.
function aipData(): Plugin {
  return {
    name: "aip-data",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = decodeURIComponent((req.url ?? "").split("?")[0]);
        if (url === "/index.json") {
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify(buildIndex()));
          return;
        }
        if (url.startsWith("/data/")) {
          const file = path.resolve(DATA, url.slice("/data/".length));
          if (file.startsWith(DATA + path.sep) && fs.existsSync(file)) {
            res.setHeader("Content-Type", "application/json");
            fs.createReadStream(file).pipe(res);
            return;
          }
        }
        next();
      });
    },
    generateBundle() {
      const index = buildIndex();
      this.emitFile({ type: "asset", fileName: "index.json", source: JSON.stringify(index) });
      for (const c of index.countries) {
        this.emitFile({ type: "asset", fileName: c.path, source: fs.readFileSync(path.join(DATA, "..", c.path)) });
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), aipData()],
  base: "./",
});
