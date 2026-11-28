// Pure logic of the Damage Calculator page (#16, ADR-014): master data parsing, the request sent to the Python
// façade (python/calculations/calc_facade.py) and result labels. No DOM, no Pyodide: tested with Vitest.

export const CALC_SCHEMA_VERSION = 3;   // calc_master.json, python/analytics/calc_master.py (3: learnsets per game, #37; 2: items, #17)
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
  abilities_from: number | null;   // abilities taken from this default form (PokéAPI has none for the form itself)
  learnsets: Record<string, Learnset>;   // by PokéAPI version group (the game of a regulation)
}

/** Damaging moves a form learns in one game, and where they come from: `version_group` / `poke_id` name the game and
 * form whose learnset this is (another form or game when the data has none for this one), both null = none. */
export interface Learnset {
  moves: number[];
  version_group: string | null;
  poke_id: number | null;
}

/** A regulation of the export, newest first in CalcMaster.regulations (the first is the page default). */
export interface CalcRegulation {
  id: string;
  label: string;
  version_group: string;   // the game whose learnsets the regulation uses
  forms: number[];         // poke_ids of the forms seen in its team usage
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
  regulations: CalcRegulation[];
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
  for (const key of ["regulations", "forms", "moves", "natures", "type_chart", "items"] as const) {
    if (!Array.isArray(m[key])) throw new CalcDataError(`calc_master.json has no ${key} list`);
  }
  if (m.regulations!.length === 0) throw new CalcDataError("calc_master.json has no regulation");
  return m as CalcMaster;
}

/** PokéAPI slug -> display name, hyphens kept: "calyrex-shadow" -> "Calyrex-Shadow", "flare-blitz" -> "Flare-Blitz". */
export function displayName(slug: string): string {
  return slug.split("-").map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join("-");
}

const byName = (a: CalcMove, b: CalcMove) => a.name.localeCompare(b.name);

export const GAME_LABEL: Record<string, string> = { "scarlet-violet": "Scarlet / Violet", champions: "Champions" };
const gameLabel = (group: string) => GAME_LABEL[group] ?? displayName(group);

/** The game of the default regulation (the newest one): the learnsets the team builder uses. */
export function defaultVersionGroup(master: CalcMaster): string {
  return master.regulations[0].version_group;
}

/** Damaging moves the form learns in `versionGroup`; without a learnset (or with no damaging move in it) every
 * exported move, flagged. */
export function movesFor(master: CalcMaster, form: CalcForm, versionGroup: string): { moves: CalcMove[]; fromLearnset: boolean } {
  const own = form.learnsets[versionGroup]?.moves ?? [];
  if (own.length === 0) return { moves: [...master.moves].sort(byName), fromLearnset: false };
  const ids = new Set(own);
  return { moves: master.moves.filter((mv) => ids.has(mv.id)).sort(byName), fromLearnset: true };
}

/** Where the moves listed for `form` in `versionGroup` come from, when not from its own learnset in that game (BR-05:
 * a borrowed or fallback learnset is never shown silently); "" when they do. */
export function learnsetNote(master: CalcMaster, form: CalcForm, versionGroup: string): string {
  const ls = form.learnsets[versionGroup];
  if (!ls || ls.version_group === null) return "No learnset in the game data for this form: every exported move is listed.";
  if (!movesFor(master, form, versionGroup).fromLearnset) {
    return "This form's learnset has no damaging move: every exported move is listed.";
  }
  if (ls.version_group === versionGroup && ls.poke_id === form.poke_id) return "";
  const from = master.forms.find((f) => f.poke_id === ls.poke_id);
  const whose = ls.poke_id === form.poke_id ? "Its" : `${from ? displayName(from.form) : form.species}'s`;   // the default form may not be exported
  const lacking = ls.version_group === versionGroup ? "the game data" : `the ${gameLabel(versionGroup)} data`;
  return `Moves: ${whose} ${gameLabel(ls.version_group)} learnset (${lacking} has none for this form).`;
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
