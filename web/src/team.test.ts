import { describe, expect, it } from "vitest";
import type { CalcMaster } from "./calc";
import { calcLink, createTeamStore, decodeTeam, readCalcLink, resolveTeam, teamError, encodeTeam, TEAMS_KEY, TeamLinkError, type Team } from "./team";

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
    { poke_id: 987, ability: "protosynthesis", item: "booster-energy", tera: "fairy", nature: "timid",
      evs: { ...stats(0), hp: 4, spatk: 252, spe: 252 }, ivs: { ...stats(31), atk: 0 }, moves: [247, 585, 94, 182] },
    { poke_id: 727, ability: "intimidate", item: "", tera: "", nature: "careful", evs: { ...stats(0), hp: 252, spdef: 252, atk: 4 },
      ivs: stats(31), moves: [] },
  ],
};

describe("team share link", () => {
  it("decodes what it encodes, Tera type included", () => {
    expect(decodeTeam(encodeTeam(TEAM))).toEqual(TEAM);
    expect(encodeTeam(TEAM)).toMatch(/^2\./);
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
    expect(reason(["3", ...rest].join("."))).toBe("version");
    expect(reason(["0", ...rest].join("."))).toBe("version");
  });

  it("refuses a format-1 link (before Tera types) and asks for a new one", () => {
    const data = btoa(JSON.stringify(["old", []])).replace(/=+$/, "");
    expect(() => decodeTeam(`1.${data.length}.${data}`)).toThrow(
      "This link uses team format 1, made before Tera types were stored; this site reads format 2. " +
      "Ask for a new link.");
  });

  it("refuses a truncated link", () => {
    const link = encodeTeam(TEAM);
    expect(reason(link.slice(0, -1))).toBe("truncated");
    expect(reason(link.slice(0, link.length / 2))).toBe("truncated");
    expect(reason("2.12")).toBe("truncated");   // cut inside the header
    expect(reason("2.")).toBe("truncated");
    expect(reason("3.40")).toBe("version");     // another format, even cut short
  });

  it("refuses a link that is not a team", () => {
    expect(reason("")).toBe("invalid");
    expect(reason("garbage")).toBe("invalid");
    const wrap = (value: unknown) => {
      const data = btoa(JSON.stringify(value)).replace(/=+$/, "");
      return `2.${data.length}.${data}`;
    };
    expect(reason(wrap({ name: "x" }))).toBe("invalid");
    const member = [987, "protosynthesis", "timid", [0, 0, 0, 252, 4, 252], [31, 31, 31, 31, 31, 31], [247], "focus-sash", "fairy"];
    expect(decodeTeam(wrap(["ok", [member]])).members).toHaveLength(1);
    expect(reason(wrap(["seven", Array(7).fill(member)]))).toBe("invalid");
    expect(reason(wrap(["evs", [[987, "a", "b", [252, 252, 252, 0, 0, 0], member[4], [], "", ""]]]))).toBe("invalid");
    expect(reason(wrap(["iv", [[987, "a", "b", member[3], [32, 31, 31, 31, 31, 31], [], "", ""]]]))).toBe("invalid");
    expect(reason(wrap(["moves", [[987, "a", "b", member[3], member[4], [1, 2, 3, 4, 5], "", ""]]]))).toBe("invalid");
    expect(reason(wrap(["item", [[987, "a", "b", member[3], member[4], [], 7, ""]]]))).toBe("invalid");
    expect(reason(wrap(["two sashes", [member, member]]))).toBe("invalid");
    expect(reason(wrap(["tera", [[...member.slice(0, 7), "shadow"]]]))).toBe("invalid");
    expect(reason(wrap(["no tera", [member.slice(0, 7)]]))).toBe("invalid");
    expect(reason(wrap(["id", [["987", "a", "b", member[3], member[4], [], "", ""]]]))).toBe("invalid");
  });
});

describe("item clause", () => {
  const m = (item: string) => ({ ...TEAM.members[1], item });
  it("refuses two Pokémon holding the same item, names it", () => {
    expect(teamError({ name: "", members: [m("focus-sash"), m("leftovers"), m("focus-sash")] }))
      .toBe("Focus-Sash is held by more than one Pokémon (members 1 and 3); each item at most once per team.");
  });
  it("allows any number of Pokémon without an item", () => {
    expect(teamError({ name: "", members: [m(""), m(""), m("leftovers")] })).toBeNull();
  });
  it("does not let a team with a repeated item be saved", () => {
    const storage = memoryStorage();
    expect(createTeamStore(() => storage).save({ name: "", members: [m("leftovers"), m("leftovers")] })).toBeNull();
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

  it("reads teams saved before Tera types (vgc-teams-v1) with no Tera type, and leaves them in place", () => {
    const storage = memoryStorage();
    const old = { id: "a1", saved_at: "2026-01-01T00:00:00.000Z", name: "Old",
      members: TEAM.members.map(({ tera: _, ...m }) => m) };
    storage.setItem("vgc-teams-v1", JSON.stringify([old]));
    const store = createTeamStore(() => storage);
    expect(TEAMS_KEY).toBe("vgc-teams-v2");
    expect(store.list()).toEqual([{ ...old, members: TEAM.members.map((m) => ({ ...m, tera: "" })) }]);
    store.save({ name: "New", members: [] });
    expect(store.list().map((t) => t.name)).toEqual(["New", "Old"]);
    expect(JSON.parse(storage.getItem("vgc-teams-v1")!)).toEqual([old]);
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
    schema_version: 2, level: 50, items: [{ name: "focus-sash", category: "held-items" }], skipped: [], type_chart: [],
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
    const team = { name: "ok", members: [{ ...TEAM.members[0], item: "focus-sash", moves: [247, 585] }] };
    expect(resolveTeam(MASTER, team)).toEqual({ team, notes: [] });
  });

  it("drops unknown Pokémon and moves, resets an unknown ability or nature, and says so", () => {
    const team = { name: "old", members: [
      { ...TEAM.members[0], ability: "cloud-nine", nature: "brave" },   // 94 is not in its learnset, 182 not exported
      TEAM.members[1],   // 727 is not in the data
    ] };
    const r = resolveTeam(MASTER, team);
    expect(r.team).toEqual({ name: "old", members: [
      { ...TEAM.members[0], ability: "protosynthesis", nature: "hardy", item: "", moves: [247, 585] }] });
    expect(r.notes).toEqual([
      "Flutter-Mane: ability cloud-nine replaced by Protosynthesis.",
      "Flutter-Mane: nature brave replaced by Hardy.",
      "Flutter-Mane: item booster-energy is not in the item list: removed.",
      "Flutter-Mane: 2 moves not in its damaging-move list left out.",
      "Pokémon #727 is not in the calculator data: left out.",
    ]);
  });
});

describe("calculator link (one member as attacker or defender)", () => {
  it("opens the member on the chosen side", () => {
    const m = TEAM.members[0];
    expect(readCalcLink(calcLink("attacker", m))).toEqual({ side: "attacker", member: m });
    expect(readCalcLink(calcLink("defender", m))).toEqual({ side: "defender", member: m });
  });
  it("ignores another fragment and refuses a damaged one", () => {
    expect(readCalcLink("")).toBeNull();
    expect(readCalcLink("#detail")).toBeNull();
    expect(() => readCalcLink(calcLink("attacker", TEAM.members[0]).slice(0, -3))).toThrow(TeamLinkError);
  });
});
