// Team save (#17): a team of up to 6 Pokémon, its share link (versioned, compact, in the URL fragment) and the
// localStorage store of named teams, and the link that opens one member in the damage calculator. Pure: no DOM,
// no Pyodide; tested with Vitest. Forms, abilities, natures and moves
// are the ids / slugs of calc_master.json (calc.ts); checking them against the master data is the page's job.
import {
  displayName, movesFor, spreadError, STATS, type CalcForm, type CalcMaster, type SideInput, type Stats,
} from "./calc";

export const MAX_MEMBERS = 6, MAX_MOVES = 4, MAX_NAME = 60;

export interface TeamMember {
  poke_id: number;
  ability: string;
  item: string;      // held item name, "" = no item; at most one Pokémon per item (item clause)
  nature: string;
  evs: Stats;
  ivs: Stats;
  moves: number[];   // move ids, at most 4
}

export interface Team {
  name: string;
  members: TeamMember[];   // at most 6
}

/** Version of the share-link format; a link of another version is refused, never guessed. */
export const LINK_VERSION = 1;

// Positional on purpose (short links): [name, [[poke_id, ability, nature, evs[6], ivs[6], move ids, item], ...]].
type Packed = [string, [number, string, string, number[], number[], number[], string][]];

const toBase64Url = (text: string) => {
  let bin = "";
  for (const b of new TextEncoder().encode(text)) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};

const fromBase64Url = (data: string) => {
  const bin = atob(data.replace(/-/g, "+").replace(/_/g, "/"));
  return new TextDecoder("utf-8", { fatal: true }).decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
};

/** "<version>.<payload length>.<base64url JSON>": the length makes a truncated link detectable. */
export function encodeTeam(team: Team): string {
  const packed: Packed = [team.name, team.members.map((m) =>
    [m.poke_id, m.ability, m.nature, STATS.map((s) => m.evs[s]), STATS.map((s) => m.ivs[s]), m.moves, m.item])];
  const data = toBase64Url(JSON.stringify(packed));
  return `${LINK_VERSION}.${data.length}.${data}`;
}

/** "invalid" = not a team link at all, "truncated" = cut short (copy/paste), "version" = another link format. */
export type TeamLinkReason = "invalid" | "truncated" | "version";

export class TeamLinkError extends Error {
  constructor(readonly reason: TeamLinkReason, message: string) {
    super(message);
    this.name = "TeamLinkError";
  }
}

const isInt = (v: unknown): v is number => Number.isInteger(v);
const isSlug = (v: unknown): v is string => typeof v === "string" && v.length > 0 && v.length <= 40;
const isSpread = (v: unknown): v is number[] => Array.isArray(v) && v.length === STATS.length && v.every(isInt);
const unpack = (v: number[]) => Object.fromEntries(STATS.map((s, i) => [s, v[i]])) as Stats;

const isItem = (v: unknown): v is string => v === "" || isSlug(v);

/** "1 and 3", "1, 2 and 4". */
const listed = (n: number[]) => (n.length < 2 ? String(n[0]) : `${n.slice(0, -1).join(", ")} and ${n[n.length - 1]}`);

/**
 * Legal team shape, the same limits as the calculator (6 members, 4 moves, EV / IV rules) plus the item clause (no two
 * Pokémon hold the same item; any number may hold none); null when legal.
 */
export function teamError(team: Team): string | null {
  if (typeof team.name !== "string" || team.name.length > MAX_NAME) return `The team name must be at most ${MAX_NAME} characters.`;
  if (team.members.length > MAX_MEMBERS) return `A team has at most ${MAX_MEMBERS} Pokémon.`;
  for (const m of team.members) {
    if (!isInt(m.poke_id) || !isSlug(m.ability) || !isSlug(m.nature)) return "A team member has no valid Pokémon, ability or nature.";
    if (m.moves.length > MAX_MOVES) return `A team member has more than ${MAX_MOVES} moves.`;
    if (!m.moves.every(isInt)) return "A team member has a move that is not a move id.";
    if (!isItem(m.item)) return "A team member has an item that is not an item name.";
    const bad = spreadError(m.evs, m.ivs);
    if (bad) return bad;
  }
  return itemClauseError(team);
}

/** Item clause: the first item held by two or more members, as a message; null when every item is held once. */
export function itemClauseError(team: Team): string | null {
  const holders = new Map<string, number[]>();
  team.members.forEach((m, i) => { if (m.item) holders.set(m.item, [...(holders.get(m.item) ?? []), i + 1]); });
  for (const [item, members] of holders) {
    if (members.length > 1) {
      return `${displayName(item)} is held by more than one Pokémon (members ${listed(members)}); each item at most once per team.`;
    }
  }
  return null;
}

export function decodeTeam(link: string): Team {
  const version = /^(\d+)(\.|$)/.exec(link)?.[1];
  if (version === undefined) throw new TeamLinkError("invalid", "This is not a team link.");
  if (Number(version) !== LINK_VERSION) {
    throw new TeamLinkError("version", `This link uses team format ${version}; this site reads format ${LINK_VERSION}.`);
  }
  const match = /^\d+\.(\d+)\.([A-Za-z0-9_-]*)$/.exec(link);
  if (!match) {
    if (/^\d+(\.\d*)?$/.test(link)) throw new TeamLinkError("truncated", "This team link is incomplete (cut short when copied).");
    throw new TeamLinkError("invalid", "This team link is damaged.");
  }
  const [, length, data] = match;
  if (data.length < Number(length)) throw new TeamLinkError("truncated", "This team link is incomplete (cut short when copied).");
  if (data.length > Number(length)) throw new TeamLinkError("invalid", "This team link is damaged.");
  let packed: unknown;
  try {
    packed = JSON.parse(fromBase64Url(data));
  } catch {
    throw new TeamLinkError("invalid", "This team link is damaged.");
  }
  if (!Array.isArray(packed) || packed.length !== 2 || typeof packed[0] !== "string" || !Array.isArray(packed[1])) {
    throw new TeamLinkError("invalid", "This link does not contain a team.");
  }
  const [name, rows] = packed as [string, unknown[]];
  const members: TeamMember[] = [];
  for (const row of rows) {
    if (!Array.isArray(row) || row.length !== 7 || !isInt(row[0]) || !isSlug(row[1]) || !isSlug(row[2]) ||
      !isSpread(row[3]) || !isSpread(row[4]) || !Array.isArray(row[5]) || !isItem(row[6])) {
      throw new TeamLinkError("invalid", "This link contains a Pokémon it cannot read.");
    }
    members.push({ poke_id: row[0], ability: row[1], item: row[6], nature: row[2], evs: unpack(row[3]), ivs: unpack(row[4]),
      moves: row[5] });
  }
  const team = { name, members };
  const bad = teamError(team);
  if (bad) throw new TeamLinkError("invalid", `This link contains an illegal team: ${bad}`);
  return team;
}

/** localStorage key of the saved teams (one JSON list); bump the suffix if the stored shape ever changes. */
export const TEAMS_KEY = "vgc-teams-v1";

export interface SavedTeam extends Team {
  id: string;
  saved_at: string;   // ISO time of the last save
}

export interface TeamStore {
  /** Saved teams, newest first; [] when storage is unavailable or unreadable. */
  list(): SavedTeam[];
  /** Saves a new team, or replaces the team with this id; null when the team is illegal (teamError) or the browser
   *  refused to store it. */
  save(team: Team, id?: string): SavedTeam | null;
  /** False when nothing was deleted (unknown id or storage unavailable). */
  remove(id: string): boolean;
}

const isSaved = (v: unknown): v is SavedTeam => {
  const s = v as SavedTeam | null;
  if (!s || typeof s !== "object" || typeof s.id !== "string" || typeof s.saved_at !== "string" ||
    !Array.isArray(s.members)) return false;
  try {
    return teamError(s) === null;
  } catch {
    return false;   // a member with missing fields
  }
};

/**
 * Named teams in the browser. Every storage access is guarded: `storage()` itself may throw (blocked site data,
 * some private windows), reads may find foreign or corrupt data, writes may hit the quota. The page keeps working;
 * failures are logged and reported through the return values.
 */
export function createTeamStore(storage: () => Storage | null, now: () => Date = () => new Date()): TeamStore {
  /** null = storage unavailable; unreadable stored data counts as no saved team (it could never be loaded). */
  const read = (): SavedTeam[] | null => {
    let raw: string | null | undefined;
    try {
      raw = storage()?.getItem(TEAMS_KEY);
    } catch (e) {
      console.warn("Saved teams could not be read:", e);
      return null;
    }
    if (raw === undefined) return null;
    if (raw === null) return [];
    try {
      const parsed: unknown = JSON.parse(raw);
      const teams = Array.isArray(parsed) ? parsed.filter(isSaved) : [];
      if (!Array.isArray(parsed) || teams.length < parsed.length) {
        console.warn(`Saved teams: ${Array.isArray(parsed) ? parsed.length - teams.length : "all"} unreadable entries skipped.`);
      }
      return teams;
    } catch (e) {
      console.warn("Saved teams are unreadable and will be replaced on the next save:", e);
      return [];
    }
  };
  const write = (teams: SavedTeam[]): boolean => {
    try {
      const s = storage();
      if (!s) return false;
      s.setItem(TEAMS_KEY, JSON.stringify(teams));
      return true;
    } catch (e) {
      console.warn("Saved teams could not be written:", e);
      return false;
    }
  };
  const newId = () => `${now().getTime().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

  return {
    list: () => (read() ?? []).sort((a, b) => b.saved_at.localeCompare(a.saved_at)),
    save(team, id) {
      const bad = teamError(team);
      if (bad) {
        console.warn("Team not saved:", bad);
        return null;
      }
      const teams = read();
      if (teams === null) return null;
      const saved: SavedTeam = { id: id ?? newId(), saved_at: now().toISOString(), name: team.name, members: team.members };
      return write([...teams.filter((t) => t.id !== saved.id), saved]) ? saved : null;
    },
    remove(id) {
      const teams = read();
      if (teams === null || !teams.some((t) => t.id === id)) return false;
      return write(teams.filter((t) => t.id !== id));
    },
  };
}

/** window.localStorage, or null when the browser denies it (the property access itself can throw). */
export function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch (e) {
    console.warn("localStorage is not available; teams cannot be saved:", e);
    return null;
  }
}

/**
 * Checks a team (from a link or storage) against the calculator data: Pokémon not in the data are left out, an
 * unknown ability / nature is replaced by the form's first ability / Hardy, moves outside the form's damaging-move
 * list are dropped, an item not in the item list is removed. Each change gets a note for the page to show; nothing
 * is changed silently. The item clause is not repaired here: teamError reports it.
 */
export function resolveTeam(master: CalcMaster, team: Team): { team: Team; notes: string[] } {
  const forms = new Map(master.forms.map((f) => [f.poke_id, f]));
  const natures = new Set(master.natures.map((n) => n.name));
  const items = new Set(master.items.map((i) => i.name));
  const notes: string[] = [];
  const members: TeamMember[] = [];
  for (const m of team.members) {
    const form = forms.get(m.poke_id);
    if (!form) {
      notes.push(`Pokémon #${m.poke_id} is not in the calculator data: left out.`);
      continue;
    }
    const who = displayName(form.form);
    let { ability, nature, item } = m;
    if (!form.abilities.includes(ability) && form.abilities.length > 0) {
      notes.push(`${who}: ability ${ability} replaced by ${displayName(form.abilities[0])}.`);
      ability = form.abilities[0];
    }
    if (!natures.has(nature)) {
      notes.push(`${who}: nature ${nature} replaced by Hardy.`);
      nature = "hardy";
    }
    if (item && !items.has(item)) {
      notes.push(`${who}: item ${item} is not in the item list: removed.`);
      item = "";
    }
    const known = new Set(movesFor(master, form).moves.map((mv) => mv.id));
    const moves = m.moves.filter((id) => known.has(id));
    if (moves.length < m.moves.length) {
      const n = m.moves.length - moves.length;
      notes.push(`${who}: ${n} move${n === 1 ? "" : "s"} not in its damaging-move list left out.`);
    }
    members.push({ ...m, ability, nature, item, moves });
  }
  return { team: { name: team.name, members }, notes };
}

/** A calculator side (or a member editor) as a team member. */
export function memberFromSide(side: SideInput, moves: number[], item = ""): TeamMember {
  return { poke_id: side.form.poke_id, ability: side.ability, item, nature: side.nature, evs: { ...side.evs },
    ivs: { ...side.ivs }, moves: [...moves] };
}

export type CalcSide = "attacker" | "defender";

/** URL fragment that opens one team member on a side of the damage calculator (same codec as a share link). */
export function calcLink(side: CalcSide, member: TeamMember): string {
  return `#${side}=${encodeTeam({ name: "", members: [member] })}`;
}

/** The member a calculator fragment carries; null when the fragment is not one. Throws TeamLinkError when damaged. */
export function readCalcLink(hash: string): { side: CalcSide; member: TeamMember } | null {
  const m = /^#(attacker|defender)=(.*)$/.exec(hash);
  if (!m) return null;
  const team = decodeTeam(m[2]);
  if (team.members.length !== 1) throw new TeamLinkError("invalid", "This calculator link does not hold one Pokémon.");
  return { side: m[1] as CalcSide, member: team.members[0] };
}

/** A resolved team member as a calculator side (its form must be in the master data). */
export function sideFromMember(form: CalcForm, m: TeamMember): SideInput {
  return { form, ability: m.ability, nature: m.nature, evs: { ...m.evs }, ivs: { ...m.ivs } };
}
