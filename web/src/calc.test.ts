import { describe, expect, it } from "vitest";
import {
  buildRequest,
  CalcDataError,
  defaultSide,
  displayName,
  koLabel,
  movesFor,
  parseCalcMaster,
  spreadError,
  type CalcMaster,
  type CalcResult,
} from "./calc";

const stats = (v: number) => ({ hp: v, atk: v, def: v, spatk: v, spdef: v, spe: v });
const MASTER: CalcMaster = {
  schema_version: 2,
  level: 50,
  forms: [
    { poke_id: 6, species: "Charizard", form: "charizard", types: ["fire", "flying"], base_stats: stats(80),
      abilities: ["blaze", "solar-power"], moves: [53], borrowed_from: null },
    { poke_id: 10194, species: "Calyrex", form: "calyrex-shadow", types: ["psychic", "ghost"], base_stats: stats(100),
      abilities: ["unnerve"], moves: [], borrowed_from: 898 },
  ],
  skipped: [],
  moves: [
    { id: 247, name: "shadow-ball", type: "ghost", power: 80, damage_class: "special" },
    { id: 53, name: "flamethrower", type: "fire", power: 90, damage_class: "special" },
  ],
  natures: [
    { name: "hardy", increased: null, decreased: null },
    { name: "modest", increased: "spatk", decreased: "atk" },
  ],
  type_chart: [["fire", "grass", 2]],
  items: [{ name: "leftovers", category: "held-items" }],
};

describe("parseCalcMaster", () => {
  it("accepts the exported shape", () => {
    expect(parseCalcMaster(JSON.parse(JSON.stringify(MASTER)))).toEqual(MASTER);
  });
  it("refuses another schema version or a missing list", () => {
    expect(() => parseCalcMaster({ ...MASTER, schema_version: 1 })).toThrow(CalcDataError);
    expect(() => parseCalcMaster({ ...MASTER, items: undefined })).toThrow(CalcDataError);
    expect(() => parseCalcMaster({ ...MASTER, forms: undefined })).toThrow(CalcDataError);
  });
});

describe("displayName", () => {
  it("title-cases a PokéAPI slug", () => {
    expect(displayName("calyrex-shadow")).toBe("Calyrex-Shadow");
    expect(displayName("flamethrower")).toBe("Flamethrower");
  });
});

describe("movesFor", () => {
  it("lists the form's learnset by name", () => {
    expect(movesFor(MASTER, MASTER.forms[0])).toEqual({ moves: [MASTER.moves[1]], fromLearnset: true });
  });
  it("falls back to every exported move, flagged, when the form has no learnset", () => {
    const r = movesFor(MASTER, MASTER.forms[1]);
    expect(r.fromLearnset).toBe(false);
    expect(r.moves.map((m) => m.name)).toEqual(["flamethrower", "shadow-ball"]);
  });
});

describe("spreadError", () => {
  it("accepts a legal spread", () => {
    expect(spreadError({ ...stats(0), hp: 252, spatk: 252, spe: 4 }, stats(31))).toBeNull();
  });
  it("refuses more than 508 EVs, an EV above 252 or an IV above 31", () => {
    expect(spreadError({ ...stats(0), hp: 252, spatk: 252, spe: 8 }, stats(31))).toMatch(/508/);
    expect(spreadError({ ...stats(0), atk: 253 }, stats(31))).toMatch(/252/);
    expect(spreadError(stats(0), { ...stats(31), spe: 32 })).toMatch(/31/);
  });
});

describe("buildRequest", () => {
  it("sends the façade the picked forms, nature, spread, move and the type chart", () => {
    const attacker = { ...defaultSide(MASTER.forms[0]), nature: "modest", evs: { ...stats(0), spatk: 252 } };
    const req = buildRequest(MASTER, attacker, defaultSide(MASTER.forms[1]), MASTER.moves[1]);
    expect(req).toEqual({
      attacker: { types: ["fire", "flying"], ability: "blaze", base_stats: stats(80),
        nature: { increased: "spatk", decreased: "atk" }, evs: { ...stats(0), spatk: 252 }, ivs: stats(31) },
      defender: { types: ["psychic", "ghost"], ability: "unnerve", base_stats: stats(100),
        nature: { increased: null, decreased: null }, evs: stats(0), ivs: stats(31) },
      move: { type: "fire", power: 90, damage_class: "special" },
      type_chart: [["fire", "grass", 2]],
    });
  });
});

describe("koLabel", () => {
  const r = (ohko: number, two: number, max = 100): CalcResult => ({
    attacker_stats: stats(1), defender_stats: stats(1), min_damage: 85, max_damage: max, min_percent: 0,
    max_percent: 0, ohko_chance: ohko, two_hko_chance: two, type_modifier: 1, stab: 1, category: "special",
  });
  it("names the best KO the 16 rolls reach", () => {
    expect(koLabel(r(100, 100))).toBe("Guaranteed OHKO");
    expect(koLabel(r(37.5, 100))).toBe("37.5% chance to OHKO");
    expect(koLabel(r(0, 100))).toBe("Every roll does at least half the HP (2HKO estimate)");
    expect(koLabel(r(0, 12.5))).toBe("12.5% of rolls do at least half the HP (2HKO estimate)");
    expect(koLabel(r(0, 0))).toBe("No roll does half the HP");
    expect(koLabel(r(0, 0, 0))).toBe("No damage");
  });
});
