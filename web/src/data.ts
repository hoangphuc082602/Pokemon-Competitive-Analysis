// Typed loaders and selectors for the static data written by python/analytics/export_web.py.
// The browser only displays already-correct rows: one regulation x one rating band at a time, never combined.

export const SCHEMA_VERSION = 4;   // v4: trend + tera (#14); v3: partners + matchups (#13); v2: one row per form (#24); v1 was species level

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
  datasets: {
    team_usage: FileEntry[];
    species_forms: { path: string; rows: number; bytes: number };
    partners: FileEntry[];
    matchups: FileEntry[];
    trend: FileEntry[];
    tera: FileEntry[];
  };
}

/** A species seen on the same team as the selected one (species level, all forms together). */
export interface Partner {
  species_id: number;
  species: string;
  n: number;              // teams with both
  share: number;          // P(partner | selected species)
  lift: number;           // co-occurrence vs chance, not synergy
  win_rate: number;
  win_ci_low: number;
  win_ci_high: number;
  win_rate_delta: number; // vs the band baseline
}

/** Teams with the selected species against teams with this one (team level, not on the field). */
export interface Opponent {
  species_id: number;
  species: string;
  n: number;              // battles
  win_rate: number;
  win_ci_low: number;
  win_ci_high: number;
  win_rate_delta: number; // vs the selected species' own win rate
  expected_win_rate: number;     // log5 of both teams' overall win rates
  win_rate_vs_expected: number;
  z_vs_expected: number;
}

export interface SpeciesEntry {
  species_id: number;
  species: string;
  partners?: Partner[];
  opponents?: Opponent[];
}

export type PairDataset = "partners" | "matchups";

/** An upload month of the regulation x band; tail = below 5% of the busiest month (the format is ending). */
export interface TrendMonth {
  month: string;          // YYYY-MM, UTC month of the replay upload
  player_battles: number;
  tail: boolean;
}

export interface TrendPoint {
  month: string;
  n: number;              // teams with the species that month (points with n < min_n are not exported)
  usage_share: number;
  win_rate: number;
  win_ci_low: number;
  win_ci_high: number;
}

export interface TrendFile {
  regulation: string;
  rating_band: string;
  min_n: number;
  months: TrendMonth[];
  rows: { species_id: number; species: string; points: TrendPoint[] }[];
}

export interface TeraType {
  tera_type: string;
  events: number;
  type_share: number;     // of the species' Tera events
}

/** Tera of a species. Win rates with and without Tera are not comparable (survivorship); null when n < min_n. */
export interface TeraRow {
  species_id: number;
  species: string;
  n: number;              // sent-out appearances (denominator of the Tera rate)
  tera_events: number;
  tera_rate: number;
  tera_rate_ci_low: number;
  tera_rate_ci_high: number;
  win_rate_tera: number | null;
  win_rate_no_tera: number | null;
  types: TeraType[];      // empty when tera_events < min_n
}

export interface TeraFile {
  regulation: string;
  rating_band: string;
  min_n: number;
  rows: TeraRow[];
}

export interface PairFile {
  regulation: string;
  rating_band: string;
  min_n: number;
  rows: SpeciesEntry[];
}

/** How the form of a row is known (pokemon_usage_stats.form_basis). */
export type FormBasis = "listed" | "observed" | "unobserved" | "species_only";

export interface UsageRow {
  species_id: number;
  species: string;
  poke_id: number | null;
  form: string | null;
  form_basis: FormBasis;
  label: string;
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
      || !Array.isArray(datasets.team_usage) || !Array.isArray(datasets.partners) || !Array.isArray(datasets.matchups)
      || !Array.isArray(datasets.trend) || !Array.isArray(datasets.tera)) {
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

type BandDataset = PairDataset | "trend" | "tera";

/** The file of exactly this regulation x band in a per-band dataset; never another band. */
async function loadBandFile(m: Manifest, dataset: BandDataset, regulation: string, band: string,
                            fetchJson: FetchJson, base: string): Promise<Record<string, unknown>> {
  const entry = m.datasets[dataset].find((f) => f.regulation === regulation && f.rating_band === band);
  if (!entry) throw new DataError("not-found", `no ${dataset} for ${regulation} / ${band}`);
  const data = await fetchJson(base + entry.path);
  if (!isObject(data) || !Array.isArray(data.rows)) throw new DataError("invalid", `${entry.path} is not a ${dataset} file`);
  if (data.regulation !== regulation || data.rating_band !== band) {
    throw new DataError("mismatch", `${entry.path} holds ${String(data.regulation)} / ${String(data.rating_band)}`);
  }
  return data;
}

/** The partners or matchups file of exactly this regulation x band; never another band. */
export async function loadPairFile(m: Manifest, dataset: PairDataset, regulation: string, band: string,
                                   fetchJson: FetchJson, base: string): Promise<PairFile> {
  return (await loadBandFile(m, dataset, regulation, band, fetchJson, base)) as unknown as PairFile;
}

export async function loadTrendFile(m: Manifest, regulation: string, band: string, fetchJson: FetchJson,
                                    base: string): Promise<TrendFile> {
  const data = await loadBandFile(m, "trend", regulation, band, fetchJson, base);
  if (!Array.isArray(data.months)) throw new DataError("invalid", `trend file of ${regulation} / ${band} has no months`);
  return data as unknown as TrendFile;
}

export async function loadTeraFile(m: Manifest, regulation: string, band: string, fetchJson: FetchJson,
                                   base: string): Promise<TeraFile> {
  return (await loadBandFile(m, "tera", regulation, band, fetchJson, base)) as unknown as TeraFile;
}

export function speciesEntry(file: PairFile, speciesId: number): SpeciesEntry | undefined {
  return file.rows.find((r) => r.species_id === speciesId);
}

export function teraEntry(file: TeraFile, speciesId: number): TeraRow | undefined {
  return file.rows.find((r) => r.species_id === speciesId);
}

export interface ChartSeries {
  months: string[];           // x axis: every non-tail month of the file, in order (gaps where n < min_n)
  points: TrendPoint[];       // the species' points in those months
  tailMonths: string[];       // months left out of the chart, disclosed under it
  hiddenTailPoints: number;   // points of the species in tail months (exported, not charted)
}

/** Chart data of one species: tail months are excluded from the chart and listed for disclosure. */
export function chartPoints(file: TrendFile, speciesId: number): ChartSeries {
  const months = [...file.months].sort((a, b) => a.month.localeCompare(b.month));
  const tail = new Set(months.filter((x) => x.tail).map((x) => x.month));
  const all = file.rows.find((r) => r.species_id === speciesId)?.points ?? [];
  return {
    months: months.filter((x) => !x.tail).map((x) => x.month),
    points: all.filter((p) => !tail.has(p.month)).sort((a, b) => a.month.localeCompare(b.month)),
    tailMonths: [...tail],
    hiddenTailPoints: all.filter((p) => tail.has(p.month)).length,
  };
}

export function filterRows(rows: UsageRow[], query: string): UsageRow[] {
  const q = query.trim().toLowerCase();
  return q ? rows.filter((r) => r.label.toLowerCase().includes(q) || r.species.toLowerCase().includes(q)) : rows;
}

const FORM_NOTES: Record<FormBasis, string> = {
  listed: "",
  observed: "Form hidden at team preview, seen in battle: n counts only teams where this form was sent out.",
  unobserved: "Form hidden at team preview and never sent out: form unknown, not guessed.",
  species_only: "Form not in the master data (e.g. Arceus type forms): species level.",
};

/** Why a row is masked or species level ("" for a form listed at team preview). */
export function formNote(r: UsageRow): string {
  return FORM_NOTES[r.form_basis] ?? "";
}

export interface Filters {
  regulation: string;
  band: string;
  query: string;
  species: number | null;   // species_id of the species detail view
}

/** Filters from a query string, falling back to the first regulation and its 'all' band (or first band). */
export function readFilters(search: string, m: Manifest): Filters {
  const p = new URLSearchParams(search);
  const reg = m.regulations.find((r) => r.id === p.get("reg")) ?? m.regulations[0];
  const bands = reg?.bands ?? [];
  const wanted = p.get("band") ?? "";
  const band = bands.includes(wanted) ? wanted : bands.includes("all") ? "all" : bands[0] ?? "";
  const sp = Number(p.get("sp"));
  const species = p.get("sp") && Number.isInteger(sp) && sp > 0 ? sp : null;
  return { regulation: reg?.id ?? "", band, query: p.get("q") ?? "", species };
}

export function writeFilters(f: Filters): string {
  const p = new URLSearchParams({ reg: f.regulation, band: f.band });
  if (f.query.trim()) p.set("q", f.query.trim());
  if (f.species !== null) p.set("sp", String(f.species));
  return `?${p.toString()}`;
}
