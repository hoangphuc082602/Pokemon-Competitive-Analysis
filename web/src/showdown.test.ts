import { describe, expect, it } from "vitest";
import overridesCsv from "../../python/data_quality/showdown_overrides.csv?raw";
import masterJson from "../public/data/calc_master.json?raw";
import { parseCalcMaster, type CalcForm, type CalcMaster } from "./calc";
import { normalizeName, parseOverrides, showdownName, showdownPaste } from "./showdown";
import type { Team } from "./team";

const stats = (v: number) => ({ hp: v, atk: v, def: v, spatk: v, spdef: v, spe: v });
const form = (poke_id: number, species: string, slug: string): CalcForm => ({
  poke_id, species, form: slug, types: ["normal"], base_stats: stats(100), abilities: [], moves: [], borrowed_from: null,
});
const MASTER: CalcMaster = {
  schema_version: 2, level: 50, skipped: [], natures: [], type_chart: [], items: [],
  forms: [form(987, "Flutter Mane", "flutter-mane"), form(892, "Urshifu", "urshifu-rapid-strike"),
    form(645, "Landorus", "landorus-incarnate")],
  moves: [
    { id: 585, name: "moonblast", type: "fairy", power: 95, damage_class: "special" },
    { id: 247, name: "shadow-ball", type: "ghost", power: 80, damage_class: "special" },
    { id: 369, name: "u-turn", type: "bug", power: 70, damage_class: "physical" },
    { id: 503, name: "surging-strikes", type: "water", power: 25, damage_class: "physical" },
  ],
};

const TEAM: Team = {
  name: "Rain",
  members: [
    { poke_id: 987, ability: "protosynthesis", item: "booster-energy", tera: "fairy", nature: "timid",
      evs: { ...stats(0), hp: 4, spatk: 252, spe: 252 }, ivs: { ...stats(31), atk: 0 }, moves: [585, 247] },
    { poke_id: 892, ability: "unseen-fist", item: "choice-scarf", tera: "", nature: "jolly",
      evs: { ...stats(0), atk: 252, spe: 252, hp: 4 }, ivs: stats(31), moves: [503, 369] },
    { poke_id: 645, ability: "sheer-force", item: "", tera: "stellar", nature: "hardy", evs: stats(0), ivs: stats(31), moves: [] },
  ],
};

describe("Showdown paste", () => {
  it("exports a known team as the expected text", () => {
    expect(showdownPaste(MASTER, TEAM)).toBe(
      `Flutter Mane @ Booster Energy
Ability: Protosynthesis
Level: 50
Tera Type: Fairy
EVs: 4 HP / 252 SpA / 252 Spe
Timid Nature
IVs: 0 Atk
- Moonblast
- Shadow Ball

Urshifu-Rapid-Strike @ Choice Scarf
Ability: Unseen Fist
Level: 50
EVs: 4 HP / 252 Atk / 252 Spe
Jolly Nature
- Surging Strikes
- U-turn

Landorus
Ability: Sheer Force
Level: 50
Tera Type: Stellar
Hardy Nature
`);
  });

  it("spells item, ability and move names the Showdown way", () => {
    const m = { ...TEAM.members[2], item: "kings-rock", ability: "beads-of-ruin" };
    expect(showdownPaste(MASTER, { name: "", members: [m] }).split("\n").slice(0, 2))
      .toEqual(["Landorus @ King's Rock", "Ability: Beads of Ruin"]);
    const name = (item: string, ability: string) => showdownPaste(MASTER, { name: "", members: [{ ...m, item, ability }] })
      .split("\n").slice(0, 2).join(" | ");
    expect(name("heavy-duty-boots", "good-as-gold")).toBe("Landorus @ Heavy-Duty Boots | Ability: Good as Gold");
    expect(name("", "zero-to-hero")).toBe("Landorus | Ability: Zero to Hero");
    expect(name("", "dragons-maw")).toBe("Landorus | Ability: Dragon's Maw");
    const vise = { ...TEAM.members[2], moves: [11] };
    expect(showdownPaste({ ...MASTER, moves: [{ id: 11, name: "vice-grip", type: "normal", power: 55, damage_class: "physical" }] },
      { name: "", members: [vise] })).toMatch(/^- Vise Grip$/m);
  });

  it("refuses a move id that is not in the data instead of writing a bare number", () => {
    expect(() => showdownPaste(MASTER, { name: "", members: [{ ...TEAM.members[2], moves: [123] }] })).toThrow(/move #123/);
  });

  it("is empty for an empty team", () => {
    expect(showdownPaste(MASTER, { name: "", members: [] })).toBe("");
  });

  it("refuses a member whose form is not in the data", () => {
    expect(() => showdownPaste(MASTER, { name: "", members: [{ ...TEAM.members[0], poke_id: 1 }] })).toThrow(/#1/);
  });
});

/** The parser's rules (pokemon_name_mapping.py): an override first, then exact match after normalisation. */
const overrides = new Map(parseOverrides(overridesCsv).map(([name, slug]) => [name, slug]));
const parserForm = (name: string) => overrides.get(name) ?? normalizeName(name);

describe("Showdown form names", () => {
  const master = parseCalcMaster(JSON.parse(masterJson));

  it("normalise like the Python parser", () => {
    expect(normalizeName("Flutter Mane")).toBe("flutter-mane");
    expect(normalizeName("Farfetch’d")).toBe("farfetchd");
    expect(normalizeName("Type: Null")).toBe("type-null");
    expect(normalizeName("Flabébé")).toBe("flabebe");
  });

  it("map back to the same form under the parser's name rules, for every form of the calculator data", () => {
    const wrong = master.forms.filter((f) => parserForm(showdownName(f)) !== f.form)
      .map((f) => `${f.form} -> ${showdownName(f)}`);
    expect(wrong).toEqual([]);
  });

  it("use an override name for a form the parser maps by override (Showdown has no 'Landorus-Incarnate')", () => {
    const missed = master.forms.filter((f) => f.form !== normalizeName(f.species) &&
      [...overrides.values()].includes(f.form) && !overrides.has(showdownName(f))).map((f) => f.form);
    expect(missed).toEqual([]);
    expect(showdownName(form(645, "Landorus", "landorus-incarnate"))).toBe("Landorus");
    expect(showdownName(form(10186, "Indeedee", "indeedee-female"))).toBe("Indeedee-F");
    expect(showdownName(form(10251, "Tauros", "tauros-paldea-blaze-breed"))).toBe("Tauros-Paldea-Blaze");   // not "-Fire"
    expect(showdownName(form(774, "Minior", "minior-red-meteor"))).toBe("Minior");                         // not "-Meteor"
    expect(showdownName(form(10, "Squawkabilly", "squawkabilly-green-plumage"))).toBe("Squawkabilly");
    expect(showdownName(form(10, "Gastrodon", "gastrodon"))).toBe("Gastrodon");                              // not "-East"
  });

  it("keep the species spelling of a plain form and title-case other forms", () => {
    expect(showdownName(form(1, "Mr. Rime", "mr-rime"))).toBe("Mr. Rime");
    expect(showdownName(form(1, "Ho-Oh", "ho-oh"))).toBe("Ho-Oh");
    expect(showdownName(form(1, "Calyrex", "calyrex-shadow"))).toBe("Calyrex-Shadow");
  });
});
