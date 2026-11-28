import { describe, expect, it } from "vitest";
import type { CalcMaster } from "./calc";
import type { Team } from "./team";
import { buildTeamSummaryRequest, multiplierLabel, roleLabel } from "./team-analysis";

const stats = (v: number) => ({ hp: v, atk: v, def: v, spatk: v, spdef: v, spe: v });
const form = (poke_id: number, name: string, types: string[]) => ({
  poke_id, species: name, form: name, types, base_stats: stats(100), abilities: ["none"], abilities_from: null, learnsets: {},
});
const MASTER: CalcMaster = {
  schema_version: 3, level: 50, regulations: [{ id: "gen9vgc2025regi", label: "Reg I 2025", version_group: "scarlet-violet", forms: [] }], skipped: [], moves: [], items: [{ name: "choice-scarf", category: "choice" }],
  forms: [form(1, "flutter-mane", ["ghost", "fairy"]), form(2, "incineroar", ["fire", "dark"])],
  natures: [{ name: "timid", increased: "spe", decreased: "atk" }, { name: "hardy", increased: null, decreased: null }],
  type_chart: [["fire", "grass", 2]],
};
const TEAM: Team = {
  name: "t",
  members: [
    { poke_id: 2, ability: "intimidate", item: "", tera: "", nature: "hardy", evs: stats(0), ivs: stats(31), moves: [] },
    { poke_id: 1, ability: "protosynthesis", item: "choice-scarf", tera: "", nature: "timid", evs: { ...stats(0), spe: 252 },
      ivs: stats(31), moves: [5] },
  ],
};

describe("team summary request", () => {
  it("sends each member as a façade side with its display name and held item, plus the type chart", () => {
    expect(buildTeamSummaryRequest(MASTER, TEAM)).toEqual({
      members: [
        { name: "Incineroar", item: "", types: ["fire", "dark"], ability: "intimidate", base_stats: stats(100),
          nature: { increased: null, decreased: null }, evs: stats(0), ivs: stats(31) },
        { name: "Flutter-Mane", item: "choice-scarf", types: ["ghost", "fairy"], ability: "protosynthesis",
          base_stats: stats(100), nature: { increased: "spe", decreased: "atk" }, evs: { ...stats(0), spe: 252 }, ivs: stats(31) },
      ],
      type_chart: [["fire", "grass", 2]],
    });
  });

  it("refuses a member whose form is not in the game data", () => {
    expect(() => buildTeamSummaryRequest(MASTER, { name: "", members: [{ ...TEAM.members[0], poke_id: 99 }] }))
      .toThrow(/99/);
  });
});

describe("labels", () => {
  it("names the engine's roles", () => {
    expect(roleLabel("physical_sweeper")).toBe("Physical sweeper");
    expect(roleLabel("special_sweeper")).toBe("Special sweeper");
    expect(roleLabel("wall")).toBe("Wall");
    expect(roleLabel("balanced")).toBe("Balanced");
  });

  it("shows multipliers as fractions and leaves neutral blank", () => {
    expect([4, 2, 1, 0.5, 0.25, 0].map(multiplierLabel)).toEqual(["×4", "×2", "", "×½", "×¼", "×0"]);
  });
});
