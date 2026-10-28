export type FeatureType = "aerodrome" | "runway" | "runwayDirection" | "navaid" | "waypoint" | "route";

export interface Field {
  value: unknown;
  unit: string | null;
  source: string;
  section: string;
  effective_date: string;
  retrieved_at: string;
  source_url: string;
  parser_version: string;
  raw_text: unknown;
}

export interface Feature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] } | { type: "LineString"; coordinates: [number, number][] } | null;
  properties: {
    naturalKey: string;
    parentKey: string | null;
    featureType: FeatureType;
    publicationId: string;
    effectiveFrom: string;
    effectiveTo: string | null;
    sourceClass: string;
    temporality: string;
    contentHash: string;
    fields: Record<string, Field>;
  };
}

export interface Issue {
  publicationId: string;
  severity: "warning" | "error";
  ruleId: string;
  featureKey: string;
  section: string;
  message: string;
  rawSnippet: string;
}

export interface Publication {
  cycleId: string;
  effectiveDate: string;
  amendmentId: string;
  sourceKind: string;
  ingestedAt: string;
  status: string;
  stats: { total_documents: number; parsed_features: number; issue_count: number; error_count: number; warning_count: number };
  sourceUrl: string;
  notes: string | null;
}

export interface CountryData {
  type: "FeatureCollection";
  features: Feature[];
  featureTypes: { featureType: FeatureType; count: number }[];
  publications: Publication[];
  issues: Issue[];
  meta?: { state: string; continent: string; websites: { name: string; url: string }[]; contact_emails: string[] };
}

export interface CountryEntry {
  slug: string;
  continent: string;
  state: string;
  path: string;
  counts: Partial<Record<FeatureType, number>>;
  issues: number;
  effectiveDate?: string;
  amendmentId?: string;
  sourceUrl?: string;
  bbox: [number, number, number, number] | null;
}

export interface Index {
  continents: string[];
  countries: CountryEntry[];
}
