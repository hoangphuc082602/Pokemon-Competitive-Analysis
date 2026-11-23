// Pure selectors for the Insights page (#15). Every number they return comes from the exported web data
// (python/analytics/export_web.py); the page adds only hand-written interpretation and figures quoted from the
// generated EDA report, each labelled with its source.

import { writeFilters, type TeamUsage, type TeraFile, type TeraRow, type UsageRow } from "./data";

export interface ShiftRow {
  species_id: number;
  label: string;
  low: number;      // usage share in the lower band
  high: number;     // usage share in the higher band
  nLow: number;
  nHigh: number;
  shift: number;    // high - low, as a fraction (x100 = percentage points)
}

/** species_id -> its row, for the species whose only row in the band is a form listed at team preview. */
function soleListedRow(rows: UsageRow[]): Map<number, UsageRow> {
  const bySpecies = new Map<number, UsageRow[]>();
  for (const r of rows) bySpecies.set(r.species_id, [...(bySpecies.get(r.species_id) ?? []), r]);
  const out = new Map<number, UsageRow>();
  for (const [id, list] of bySpecies) if (list.length === 1 && list[0].form_basis === "listed") out.set(id, list[0]);
  return out;
}

/** Usage of the same form in two rating bands of one regulation (each against its own band's teams).
 *  Only species with a single listed form in both bands are compared, so forms are never summed and masked
 *  forms (whose n depends on being sent out) are left out; n must reach minN in both bands. Sorted by shift. */
export function bandShift(low: TeamUsage, high: TeamUsage, minN: number): ShiftRow[] {
  const lo = soleListedRow(low.rows);
  const hi = soleListedRow(high.rows);
  const out: ShiftRow[] = [];
  for (const [id, a] of lo) {
    const b = hi.get(id);
    if (!b || a.n < minN || b.n < minN || a.label !== b.label) continue;
    out.push({ species_id: id, label: a.label, low: a.usage_share, high: b.usage_share, nLow: a.n, nHigh: b.n,
      shift: b.usage_share - a.usage_share });
  }
  return out.sort((x, y) => x.shift - y.shift);
}

export interface TeraSummary {
  appearances: number;   // sent-out appearances of the exported species (n >= min_n)
  events: number;
  rate: number;          // events / appearances, pooled (never a mean of species rates)
  species: number;
  top: TeraRow[];        // species with the most Tera events that have a type split
}

export function teraSummary(file: TeraFile, k: number): TeraSummary {
  const appearances = file.rows.reduce((s, r) => s + r.n, 0);
  const events = file.rows.reduce((s, r) => s + r.tera_events, 0);
  const top = file.rows.filter((r) => r.types.length).sort((a, b) => b.tera_events - a.tera_events).slice(0, k);
  return { appearances, events, rate: appearances ? events / appearances : 0, species: file.rows.length, top };
}

export interface PopularityPoint {
  species_id: number;
  label: string;
  n: number;
  usage: number;    // usage share in the band
  delta: number;    // win rate minus the band baseline
}

/** One point per form listed at team preview with n >= minN (masked forms have a selection-biased win rate). */
export function popularityPoints(data: TeamUsage, minN: number): PopularityPoint[] {
  return data.rows.filter((r) => r.form_basis === "listed" && r.n >= minN)
    .map((r) => ({ species_id: r.species_id, label: r.label, n: r.n, usage: r.usage_share, delta: r.win_rate_delta }));
}

/** Link to the Meta Overview view that reproduces a figure: regulation x band, and the species detail if given. */
export function overviewLink(regulation: string, band: string, species: number | null = null): string {
  const q = writeFilters({ regulation, band, query: "", page: 1, species });
  return `./${q}${species === null ? "" : "#detail"}`;
}

/** Forms strictly above the band baseline among the more used half and the less used half (by usage share). */
export function aboveBaselineByHalf(points: PopularityPoint[]): { upper: { above: number; of: number };
                                                                   lower: { above: number; of: number } } {
  const sorted = [...points].sort((a, b) => b.usage - a.usage);
  const cut = Math.floor(sorted.length / 2);
  const count = (xs: PopularityPoint[]) => ({ above: xs.filter((x) => x.delta > 0).length, of: xs.length });
  return { upper: count(sorted.slice(0, cut)), lower: count(sorted.slice(cut)) };
}
