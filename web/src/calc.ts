// Pure logic of the Damage Calculator page (#16, ADR-014): master data parsing, the request sent to the Python
// façade (python/calculations/calc_facade.py) and result labels. No DOM, no Pyodide: tested with Vitest.

export const CALC_SCHEMA_VERSION = 2;   // calc_master.json, python/analytics/calc_master.py (2: items, #17)
export const STATS = ["hp", "atk", "def", "spatk", "spdef", "spe"] as const;
export type Stat = (typeof STATS)[number];
export type Stats = Record<Stat, number>;
export const MAX_EV = 252, MAX_EV_TOTAL = 508, MAX_IV = 31;

export interface CalcForm {
  poke_id: number;
  species: string;
  form: string;
  types: string[];
  base_stats: Stats;
  abilities: string[];
  moves: number[];
  borrowed_from: number | null;   // abilities + learnset taken from this default form (no rows for the form itself)
}

export interface CalcMove {
  id: number;
  name: string;
  type: string;
  power: number;
  damage_class: "physical" | "special";
}

/** A holdable battle item (team builder; the damage engine does not model items). */
export interface CalcItem {
  name: string;
  category: string;
}

export interface Nature {
  name: string;
  increased: Stat | null;
  decreased: Stat | null;
}

export interface CalcMaster {
  schema_version: number;
  level: number;
  forms: CalcForm[];
  skipped: string[];
  moves: CalcMove[];
  natures: Nature[];
  type_chart: [string, string, number][];
  items: CalcItem[];
}

export interface SideInput {
  form: CalcForm;
  ability: string;
  nature: string;
  evs: Stats;
  ivs: Stats;
}

export interface CalcResult {
  attacker_stats: Stats;
  defender_stats: Stats;
  min_damage: number;
  max_damage: number;
  min_percent: number;
  max_percent: number;
  ohko_chance: number;
  two_hko_chance: number;
  type_modifier: number;
  stab: number;
  category: string;
}

export class CalcDataError extends Error {}

export function parseCalcMaster(json: unknown): CalcMaster {
  const m = json as Partial<CalcMaster> | null;
  if (!m || typeof m !== "object") throw new CalcDataError("calc_master.json is not an object");
  if (m.schema_version !== CALC_SCHEMA_VERSION) {
    throw new CalcDataError(`calc_master.json schema ${m.schema_version}, expected ${CALC_SCHEMA_VERSION}`);
  }
  for (const key of ["forms", "moves", "natures", "type_chart", "items"] as const) {
    if (!Array.isArray(m[key])) throw new CalcDataError(`calc_master.json has no ${key} list`);
  }
  return m as CalcMaster;
}

/** PokéAPI slug -> display name, hyphens kept: "calyrex-shadow" -> "Calyrex-Shadow", "flare-blitz" -> "Flare-Blitz". */
export function displayName(slug: string): string {
  return slug.split("-").map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join("-");
}

const byName = (a: CalcMove, b: CalcMove) => a.name.localeCompare(b.name);

/** Damaging moves the form learns; a form without a learnset in the master data gets every exported move, flagged. */
export function movesFor(master: CalcMaster, form: CalcForm): { moves: CalcMove[]; fromLearnset: boolean } {
  if (form.moves.length === 0) return { moves: [...master.moves].sort(byName), fromLearnset: false };
  const ids = new Set(form.moves);
  return { moves: master.moves.filter((mv) => ids.has(mv.id)).sort(byName), fromLearnset: true };
}

const fill = (v: number): Stats => ({ hp: v, atk: v, def: v, spatk: v, spdef: v, spe: v });

export function defaultSide(form: CalcForm): SideInput {
  return { form, ability: form.abilities[0] ?? "", nature: "hardy", evs: fill(0), ivs: fill(MAX_IV) };
}

/** Same limits as the façade (which refuses them too); null when the spread is legal. */
export function spreadError(evs: Stats, ivs: Stats): string | null {
  if (STATS.some((s) => !Number.isInteger(evs[s]) || evs[s] < 0 || evs[s] > MAX_EV)) return `Each EV must be 0–${MAX_EV}.`;
  const total = STATS.reduce((t, s) => t + evs[s], 0);
  if (total > MAX_EV_TOTAL) return `EVs total ${total}; the limit is ${MAX_EV_TOTAL}.`;
  if (STATS.some((s) => !Number.isInteger(ivs[s]) || ivs[s] < 0 || ivs[s] > MAX_IV)) return `Each IV must be 0–${MAX_IV}.`;
  return null;
}

/** One side of a façade request (calc_facade: types, ability, base stats, nature, EVs / IVs). */
export function facadeSide(master: CalcMaster, s: SideInput) {
  const n = master.natures.find((x) => x.name === s.nature);
  return { types: s.form.types, ability: s.ability, base_stats: s.form.base_stats,
    nature: { increased: n?.increased ?? null, decreased: n?.decreased ?? null }, evs: s.evs, ivs: s.ivs };
}

/** The JSON request of calc_facade.calculate. */
export function buildRequest(master: CalcMaster, attacker: SideInput, defender: SideInput, move: CalcMove) {
  return { attacker: facadeSide(master, attacker), defender: facadeSide(master, defender),
    move: { type: move.type, power: move.power, damage_class: move.damage_class }, type_chart: master.type_chart };
}

/** KO estimate from the engine's 16 rolls (one hit; "2HKO" = one hit doing at least half the HP, as the engine counts it). */
export function koLabel(r: CalcResult): string {
  if (r.max_damage === 0) return "No damage";
  if (r.ohko_chance >= 100) return "Guaranteed OHKO";
  if (r.ohko_chance > 0) return `${r.ohko_chance}% chance to OHKO`;
  if (r.two_hko_chance >= 100) return "Every roll does at least half the HP (2HKO estimate)";
  if (r.two_hko_chance > 0) return `${r.two_hko_chance}% of rolls do at least half the HP (2HKO estimate)`;
  return "No roll does half the HP";
}
