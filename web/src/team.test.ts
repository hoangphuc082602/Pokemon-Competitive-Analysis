import { describe, expect, it } from "vitest";
import type { CalcMaster } from "./calc";
import { createTeamStore, decodeTeam, resolveTeam, withMember, encodeTeam, TEAMS_KEY, TeamLinkError, type Team } from "./team";

/** In-memory Storage: one instance shared by two stores stands for a browser restart. */
function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => { data.delete(k); },
    setItem: (k, v) => { data.set(k, String(v)); },
  };
}

const throwing = (): Storage => { throw new DOMException("The operation is insecure.", "SecurityError"); };

const stats = (v: number) => ({ hp: v, atk: v, def: v, spatk: v, spdef: v, spe: v });
const TEAM: Team = {
  name: "Rain · Pelipper",
  members: [
    { poke_id: 987, ability: "protosynthesis", nature: "timid", evs: { ...stats(0), hp: 4, spatk: 252, spe: 252 },
      ivs: { ...stats(31), atk: 0 }, moves: [247, 585, 94, 182] },
    { poke_id: 727, ability: "intimidate", nature: "careful", evs: { ...stats(0), hp: 252, spdef: 252, atk: 4 },
      ivs: stats(31), moves: [] },
  ],
};

describe("team share link", () => {
  it("decodes what it encodes", () => {
    expect(decodeTeam(encodeTeam(TEAM))).toEqual(TEAM);
  });

  const reason = (link: string) => {
    try {
      decodeTeam(link);
    } catch (e) {
      expect(e).toBeInstanceOf(TeamLinkError);
      return (e as TeamLinkError).reason;
    }
    throw new Error(`accepted ${link}`);
  };

  it("refuses a link of another format version", () => {
    const [, ...rest] = encodeTeam(TEAM).split(".");
    expect(reason(["2", ...rest].join("."))).toBe("version");
    expect(reason(["0", ...rest].join("."))).toBe("version");
  });

  it("refuses a truncated link", () => {
    const link = encodeTeam(TEAM);
    expect(reason(link.slice(0, -1))).toBe("truncated");
    expect(reason(link.slice(0, link.length / 2))).toBe("truncated");
    expect(reason("1.12")).toBe("truncated");   // cut inside the header
    expect(reason("1.")).toBe("truncated");
    expect(reason("2.40")).toBe("version");     // another format, even cut short
  });

  it("refuses a link that is not a team", () => {
    expect(reason("")).toBe("invalid");
    expect(reason("garbage")).toBe("invalid");
    const wrap = (value: unknown) => {
      const data = btoa(JSON.stringify(value)).replace(/=+$/, "");
      return `1.${data.length}.${data}`;
    };
    expect(reason(wrap({ name: "x" }))).toBe("invalid");
    const member = [987, "protosynthesis", "timid", [0, 0, 0, 252, 4, 252], [31, 31, 31, 31, 31, 31], [247]];
    expect(decodeTeam(wrap(["ok", [member]])).members).toHaveLength(1);
    expect(reason(wrap(["seven", Array(7).fill(member)]))).toBe("invalid");
    expect(reason(wrap(["evs", [[987, "a", "b", [252, 252, 252, 0, 0, 0], member[4], []]]]))).toBe("invalid");
    expect(reason(wrap(["iv", [[987, "a", "b", member[3], [32, 31, 31, 31, 31, 31], []]]]))).toBe("invalid");
    expect(reason(wrap(["moves", [[987, "a", "b", member[3], member[4], [1, 2, 3, 4, 5]]]]))).toBe("invalid");
    expect(reason(wrap(["id", [["987", "a", "b", member[3], member[4], []]]]))).toBe("invalid");
  });
});

describe("saved teams", () => {
  it("keeps several named teams across a browser restart, newest first", () => {
    const storage = memoryStorage();
    let t = 0;
    const store = createTeamStore(() => storage, () => new Date(Date.UTC(2026, 0, 1, 0, 0, t++)));
    const first = store.save(TEAM)!;
    const second = store.save({ name: "Trick Room", members: [] })!;
    expect(first.id).not.toBe(second.id);
    const reopened = createTeamStore(() => storage);
    expect(reopened.list().map((s) => s.name)).toEqual(["Trick Room", "Rain · Pelipper"]);
    expect(reopened.list()[1]).toMatchObject(TEAM);
  });

  it("updates a team saved under the same id and deletes a team", () => {
    const storage = memoryStorage();
    const store = createTeamStore(() => storage);
    const saved = store.save(TEAM)!;
    const other = store.save({ name: "Other", members: [] })!;
    store.save({ ...TEAM, name: "Renamed" }, saved.id);
    expect(store.list().map((s) => s.name).sort()).toEqual(["Other", "Renamed"]);
    expect(store.remove(saved.id)).toBe(true);
    expect(store.list().map((s) => s.id)).toEqual([other.id]);
  });

  it("works without storage: nothing saved, no exception", () => {
    for (const storage of [throwing, () => null, () => ({ ...memoryStorage(),
      getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("QuotaExceededError"); } })]) {
      const store = createTeamStore(storage);
      expect(store.list()).toEqual([]);
      expect(store.save(TEAM)).toBeNull();
      expect(store.remove("x")).toBe(false);
    }
  });

  it("keeps the saved teams when writing fails (quota) and skips unreadable entries", () => {
    const storage = memoryStorage();
    const store = createTeamStore(() => storage);
    const saved = store.save(TEAM)!;
    storage.setItem(TEAMS_KEY, JSON.stringify([...JSON.parse(storage.getItem(TEAMS_KEY)!), { id: "bad" }, 42]));
    expect(store.list().map((s) => s.id)).toEqual([saved.id]);
    const full = createTeamStore(() => ({ ...storage, getItem: storage.getItem, setItem: () => { throw new Error("quota"); } }));
    expect(full.save({ name: "New", members: [] })).toBeNull();
    expect(store.list().map((s) => s.id)).toEqual([saved.id]);
    storage.setItem(TEAMS_KEY, "{not json");
    expect(store.list()).toEqual([]);
    expect(store.save(TEAM)).not.toBeNull();   // unreadable data does not block saving for ever
    expect(store.list()).toHaveLength(1);
  });
});

describe("resolveTeam (a link made with another data snapshot)", () => {
  const MASTER: CalcMaster = {
    schema_version: 1, level: 50, skipped: [], type_chart: [],
    forms: [{ poke_id: 987, species: "Flutter Mane", form: "flutter-mane", types: ["ghost", "fairy"], base_stats: stats(100),
      abilities: ["protosynthesis"], moves: [247, 585], borrowed_from: null }],
    moves: [
      { id: 247, name: "shadow-ball", type: "ghost", power: 80, damage_class: "special" },
      { id: 585, name: "moonblast", type: "fairy", power: 95, damage_class: "special" },
      { id: 94, name: "psychic", type: "psychic", power: 90, damage_class: "special" },
    ],
    natures: [{ name: "hardy", increased: null, decreased: null }, { name: "timid", increased: "spe", decreased: "atk" }],
  };

  it("keeps a team the data knows unchanged", () => {
    const team = { name: "ok", members: [{ ...TEAM.members[0], moves: [247, 585] }] };
    expect(resolveTeam(MASTER, team)).toEqual({ team, notes: [] });
  });

  it("drops unknown Pokémon and moves, resets an unknown ability or nature, and says so", () => {
    const team = { name: "old", members: [
      { ...TEAM.members[0], ability: "cloud-nine", nature: "brave" },   // 94 is not in its learnset, 182 not exported
      TEAM.members[1],   // 727 is not in the data
    ] };
    const r = resolveTeam(MASTER, team);
    expect(r.team).toEqual({ name: "old", members: [
      { ...TEAM.members[0], ability: "protosynthesis", nature: "hardy", moves: [247, 585] }] });
    expect(r.notes).toEqual([
      "Flutter-Mane: ability cloud-nine replaced by Protosynthesis.",
      "Flutter-Mane: nature brave replaced by Hardy.",
      "Flutter-Mane: 2 moves not in its damaging-move list left out.",
      "Pokémon #727 is not in the calculator data: left out.",
    ]);
  });
});

describe("withMember (calculator side -> team)", () => {
  const MASTER: CalcMaster = {
    schema_version: 1, level: 50, skipped: [], type_chart: [], natures: [],
    forms: [
      { poke_id: 987, species: "Flutter Mane", form: "flutter-mane", types: ["ghost", "fairy"], base_stats: stats(100),
        abilities: ["protosynthesis"], moves: [247, 585], borrowed_from: null },
      { poke_id: 727, species: "Incineroar", form: "incineroar", types: ["fire", "dark"], base_stats: stats(90),
        abilities: ["intimidate"], moves: [53, 247], borrowed_from: null },
    ],
    moves: [
      { id: 247, name: "shadow-ball", type: "ghost", power: 80, damage_class: "special" },
      { id: 585, name: "moonblast", type: "fairy", power: 95, damage_class: "special" },
      { id: 53, name: "flamethrower", type: "fire", power: 90, damage_class: "special" },
    ],
  };
  const side = (form: CalcMaster["forms"][number]) =>
    ({ form, ability: form.abilities[0], nature: "timid", evs: { ...stats(0), spe: 252 }, ivs: stats(31) });
  const flutter = { poke_id: 987, ability: "protosynthesis", nature: "timid", evs: { ...stats(0), spe: 252 }, ivs: stats(31) };

  it("adds a new member with the side's move, every time it is asked", () => {
    let team: Team = { name: "", members: [] };
    team = withMember(MASTER, team, side(MASTER.forms[0]), null, 585);
    team = withMember(MASTER, team, side(MASTER.forms[0]), null);
    expect(team.members).toEqual([{ ...flutter, moves: [585] }, { ...flutter, moves: [] }]);
  });

  it("updates a member, keeping only the moves the new Pokémon can use", () => {
    const team = { name: "", members: [{ ...flutter, moves: [585, 247] }] };
    const next = withMember(MASTER, team, side(MASTER.forms[1]), 0);
    expect(next.members).toEqual([{ ...flutter, poke_id: 727, ability: "intimidate", moves: [247] }]);
    expect(team.members[0].poke_id).toBe(987);   // the old team is not changed
  });

  it("refuses a seventh member", () => {
    const full = { name: "", members: Array.from({ length: 6 }, () => ({ ...flutter, moves: [] })) };
    expect(() => withMember(MASTER, full, side(MASTER.forms[0]), null)).toThrow(/at most 6/);
  });
});
