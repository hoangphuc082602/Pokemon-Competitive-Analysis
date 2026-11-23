// Typed loaders and selectors for the static data written by python/analytics/export_web.py.
// The browser only displays already-correct rows: one regulation x one rating band at a time, never combined.

export const SCHEMA_VERSION = 1;

export interface FileEntry {
  regulation: string;
  rating_band: string;
  path: string;
  rows: number;
  bytes: number;
}

export interface Regulation {
  id: string;
  battles: number | null;
  player_battles: number | null;
  bands: string[];
}

export interface Manifest {
  schema_version: number;
  snapshot_date: string;
  min_n: number;
  population: string;
  totals: { battles: number; player_battles: number };
  regulations: Regulation[];
  bands: string[];
  datasets: { team_usage: FileEntry[] };
}

export interface UsageRow {
  species_id: number;
  species: string;
  n: number;
  usage_share: number;
  win_rate: number;
  win_ci_low: number;
  win_ci_high: number;
  win_rate_delta: number;
  lead_rate: number;
}

export interface TeamUsage {
  regulation: string;
  rating_band: string;
  player_battles: number;
  baseline_win_rate: number;
  min_n: number;
  rows: UsageRow[];
}

export type DataErrorCode = "schema-version" | "invalid" | "not-found" | "mismatch";

export class DataError extends Error {
  constructor(public readonly code: DataErrorCode, message: string) {
    super(message);
    this.name = "DataError";
  }
}

export type FetchJson = (url: string) => Promise<unknown>;

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;

export function parseManifest(json: unknown): Manifest {
  if (!isObject(json) || typeof json.schema_version !== "number") {
    throw new DataError("invalid", "manifest.json is not a data manifest");
  }
  if (json.schema_version !== SCHEMA_VERSION) {
    throw new DataError("schema-version",
      `data schema v${json.schema_version} does not match app schema v${SCHEMA_VERSION}; re-run the export`);
  }
  const datasets = json.datasets;
  if (!Array.isArray(json.regulations) || !Array.isArray(json.bands) || !isObject(datasets)
      || !Array.isArray(datasets.team_usage)) {
    throw new DataError("invalid", "manifest.json is missing regulations, bands or datasets");
  }
  return json as unknown as Manifest;
}

/** The one file of a regulation x band, or undefined. Never substitutes or combines bands. */
export function selectFile(m: Manifest, regulation: string, band: string): FileEntry | undefined {
  return m.datasets.team_usage.find((f) => f.regulation === regulation && f.rating_band === band);
}

export async function loadTeamUsage(m: Manifest, regulation: string, band: string, fetchJson: FetchJson,
                                    base: string): Promise<TeamUsage> {
  const entry = selectFile(m, regulation, band);
  if (!entry) throw new DataError("not-found", `no team usage for ${regulation} / ${band}`);
  const data = await fetchJson(base + entry.path);
  if (!isObject(data) || !Array.isArray(data.rows)) throw new DataError("invalid", `${entry.path} is not a usage file`);
  if (data.regulation !== regulation || data.rating_band !== band) {
    throw new DataError("mismatch", `${entry.path} holds ${String(data.regulation)} / ${String(data.rating_band)}`);
  }
  return data as unknown as TeamUsage;
}

export function filterRows(rows: UsageRow[], query: string): UsageRow[] {
  const q = query.trim().toLowerCase();
  return q ? rows.filter((r) => r.species.toLowerCase().includes(q)) : rows;
}

export interface Filters {
  regulation: string;
  band: string;
  query: string;
}

/** Filters from a query string, falling back to the first regulation and its 'all' band (or first band). */
export function readFilters(search: string, m: Manifest): Filters {
  const p = new URLSearchParams(search);
  const reg = m.regulations.find((r) => r.id === p.get("reg")) ?? m.regulations[0];
  const bands = reg?.bands ?? [];
  const wanted = p.get("band") ?? "";
  const band = bands.includes(wanted) ? wanted : bands.includes("all") ? "all" : bands[0] ?? "";
  return { regulation: reg?.id ?? "", band, query: p.get("q") ?? "" };
}

export function writeFilters(f: Filters): string {
  const p = new URLSearchParams({ reg: f.regulation, band: f.band });
  if (f.query.trim()) p.set("q", f.query.trim());
  return `?${p.toString()}`;
}
