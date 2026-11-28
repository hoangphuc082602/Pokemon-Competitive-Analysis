import { describe, expect, it } from "vitest";
import {
  buildRequest,
  CalcDataError,
  defaultSide,
  displayName,
  koLabel,
  learnsetNote,
  movesFor,
  parseCalcMaster,
  spreadError,
  type CalcMaster,
  type CalcResult,
} from "./calc";

const stats = (v: number) => ({ hp: v, atk: v, def: v, spatk: v, spdef: v, spe: v });
const MASTER: CalcMaster = {
  schema_version: 3,
  level: 50,
  regulations: [
    { id: "gen9championsvgc2026regm-a", label: "Champions Reg M-A 2026", version_group: "champions", forms: [6, 10034] },
    { id: "gen9vgc2025regi", label: "Reg I 2025", version_group: "scarlet-violet", forms: [6, 10194] },
  ],
  forms: [
    { poke_id: 6, species: "Charizard", form: "charizard", types: ["fire", "flying"], base_stats: stats(80),
      abilities: ["blaze", "solar-power"], abilities_from: null,
      learnsets: { "scarlet-violet": { moves: [53], version_group: "scarlet-violet", poke_id: 6 },
        champions: { moves: [53, 394], version_group: "champions", poke_id: 6 } } },
    { poke_id: 10034, species: "Charizard", form: "charizard-mega-x", types: ["fire", "dragon"], base_stats: stats(100),
      abilities: ["tough-claws"], abilities_from: null,
      learnsets: { "scarlet-violet": { moves: [53], version_group: "scarlet-violet", poke_id: 6 },
        champions: { moves: [394], version_group: "champions", poke_id: 10034 } } },
    { poke_id: 10194, species: "Calyrex", form: "calyrex-shadow", types: ["psychic", "ghost"], base_stats: stats(100),
      abilities: ["unnerve"], abilities_from: 898,
      learnsets: { "scarlet-violet": { moves: [], version_group: null, poke_id: null },
        champions: { moves: [247], version_group: "scarlet-violet", poke_id: 898 } } },
  ],
  skipped: [],
  moves: [
    { id: 247, name: "shadow-ball", type: "ghost", power: 80, damage_class: "special" },
    { id: 53, name: "flamethrower", type: "fire", power: 90, damage_class: "special" },
    { id: 394, name: "flare-blitz", type: "fire", power: 120, damage_class: "physical" },
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
    expect(() => parseCalcMaster({ ...MASTER, regulations: [] })).toThrow(/regulation/);
  });
});

describe("displayName", () => {
  it("title-cases a PokéAPI slug", () => {
    expect(displayName("calyrex-shadow")).toBe("Calyrex-Shadow");
    expect(displayName("flamethrower")).toBe("Flamethrower");
  });
});

const [charizard, megaX, shadow] = MASTER.forms;
const names = (r: { moves: { name: string }[] }) => r.moves.map((m) => m.name);

describe("movesFor", () => {
  it("lists the learnset of the selected regulation's game, by name", () => {
    expect(names(movesFor(MASTER, charizard, "champions"))).toEqual(["flamethrower", "flare-blitz"]);
    expect(names(movesFor(MASTER, charizard, "scarlet-violet"))).toEqual(["flamethrower"]);
    expect(movesFor(MASTER, charizard, "champions").fromLearnset).toBe(true);
  });
  it("falls back to every exported move, flagged, when no game has a learnset for the form", () => {
    const r = movesFor(MASTER, shadow, "scarlet-violet");
    expect(r.fromLearnset).toBe(false);
    expect(names(r)).toEqual(["flamethrower", "flare-blitz", "shadow-ball"]);
  });
  it("treats a game missing from the form's learnsets as no learnset", () => {
    expect(movesFor(MASTER, charizard, "sword-shield").fromLearnset).toBe(false);
  });
});

describe("learnsetNote", () => {
  it("says nothing when the form has its own learnset in the regulation's game", () => {
    expect(learnsetNote(MASTER, charizard, "champions")).toBe("");
    expect(learnsetNote(MASTER, megaX, "champions")).toBe("");
  });
  it("names the default form whose learnset of the same game is used", () => {
    expect(learnsetNote(MASTER, megaX, "scarlet-violet"))
      .toBe("Moves: Charizard's Scarlet / Violet learnset (the game data has none for this form).");
  });
  it("names the other game a fallback learnset comes from", () => {
    expect(learnsetNote(MASTER, shadow, "champions"))
      .toBe("Moves: Calyrex's Scarlet / Violet learnset (the Champions data has none for this form).");
  });
  it("names the form's own learnset of the other game", () => {
    const own = { ...megaX, learnsets: { champions: { moves: [394], version_group: "scarlet-violet", poke_id: 10034 } } };
    expect(learnsetNote(MASTER, own, "champions"))
      .toBe("Moves: Its Scarlet / Violet learnset (the Champions data has none for this form).");
  });
  it("tells a learnset without a damaging move apart from no learnset", () => {
    const statusOnly = { ...megaX, learnsets: { champions: { moves: [], version_group: "champions", poke_id: 10034 } } };
    expect(learnsetNote(MASTER, statusOnly, "champions"))
      .toBe("This form's learnset has no damaging move: every exported move is listed.");
  });
  it("says every move is listed when there is no learnset", () => {
    expect(learnsetNote(MASTER, shadow, "scarlet-violet")).toBe("No learnset in the game data for this form: every exported move is listed.");
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
    const attacker = { ...defaultSide(charizard), nature: "modest", evs: { ...stats(0), spatk: 252 } };
    const req = buildRequest(MASTER, attacker, defaultSide(shadow), MASTER.moves[1]);
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
