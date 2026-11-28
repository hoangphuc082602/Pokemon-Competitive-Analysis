import "./style.css";
import {
  buildRequest,
  displayName,
  koLabel,
  parseCalcMaster,
  spreadError,
  STATS,
  type CalcMaster,
  type CalcMove,
  type CalcRegulation,
  type CalcResult,
  type SideInput,
  type Stats,
} from "./calc";
import { loadEngine, pythonErrorMessage, type Engine } from "./engine";
import { createPokemonEditor, el, options, type PokemonEditor } from "./pokemon-editor";
import {
  browserStorage,
  createTeamStore,
  readCalcLink,
  resolveTeam,
  sideFromMember,
  TeamLinkError,
  type CalcSide,
  type TeamMember,
} from "./team";

const BASE = `${import.meta.env.BASE_URL}data/`;
const DEFAULTS = { attacker: "flutter-mane", defender: "incineroar" };   // fall back to the first form when absent

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const status = $<HTMLParagraphElement>("engine-status");
const teamNote = $<HTMLParagraphElement>("team-note");

function render(r: CalcResult, a: SideInput, d: SideInput, mv: CalcMove) {
  $("result-main").replaceChildren(
    el("strong", { textContent: `${r.min_damage}–${r.max_damage} damage` }),
    ` (${r.min_percent}–${r.max_percent}% of ${displayName(d.form.form)}'s ${r.defender_stats.hp} HP) · `,
    el("strong", { textContent: koLabel(r) }));
  $("result-detail").textContent = `${displayName(a.form.form)} ${displayName(mv.name)} (${displayName(mv.type)}, ` +
    `power ${mv.power}, ${r.category}) · type ×${r.type_modifier} · STAB ×${r.stab}`;
  const row = (who: string, s: Stats) =>
    el("tr", {}, el("th", { scope: "row", textContent: who }), ...STATS.map((k) => el("td", { className: "num", textContent: String(s[k]) })));
  $("result-stats").querySelector("tbody")!.replaceChildren(
    row(`Attacker: ${displayName(a.form.form)}`, r.attacker_stats), row(`Defender: ${displayName(d.form.form)}`, r.defender_stats));
  $("result").hidden = false;
}

function showError(text: string) {
  $("result-main").replaceChildren(el("span", { className: "down", textContent: text }));
  $("result-detail").textContent = "";
  $("result-stats").querySelector("tbody")!.replaceChildren();
  $("result").hidden = false;
}

/** Puts a team member (from a saved team or a team-builder link) on one side, checked against the learnsets of the
 * selected regulation's game; null when the data or that regulation lacks the form. */
function loadMember(master: CalcMaster, editor: PokemonEditor, member: TeamMember, reg: CalcRegulation): string[] | null {
  if (!reg.forms.includes(member.poke_id)) return null;
  const { team, notes } = resolveTeam(master, { name: "", members: [member] }, reg.version_group);
  if (team.members.length === 0) return null;
  const m = team.members[0];
  editor.load(sideFromMember(master.forms.find((f) => f.poke_id === m.poke_id)!, m), m.moves);
  return notes;
}

/** "From a saved team" picker at the top of a side; hidden when this browser has no saved team. */
function savedTeamPicker(root: HTMLElement, master: CalcMaster, editor: PokemonEditor, reg: () => CalcRegulation,
  onLoad: () => void) {
  const teams = createTeamStore(browserStorage).list();
  if (teams.every((t) => t.members.length === 0)) return;
  const pick = el("select");
  const members = new Map<string, TeamMember>();
  options(pick, [["", "—"]]);
  for (const t of teams) {
    const group = el("optgroup", { label: t.name || "Untitled team" });
    t.members.forEach((m, i) => {
      const key = `${t.id}:${i}`;
      members.set(key, m);
      const form = master.forms.find((f) => f.poke_id === m.poke_id);
      group.append(el("option", { value: key, textContent: form ? displayName(form.form) : `Pokémon #${m.poke_id}` }));
    });
    pick.append(group);
  }
  pick.addEventListener("change", (e) => {
    e.stopPropagation();   // not an edit of the side itself
    const m = members.get(pick.value);
    if (!m) return;
    const notes = loadMember(master, editor, m, reg());
    teamNote.textContent = notes === null ? notInData(reg()) : notes.join(" ");
    onLoad();
  });
  root.insertBefore(el("div", { className: "filters" }, el("label", {}, "From a saved team", pick)), root.children[1] ?? null);
}

const notInData = (reg: CalcRegulation) =>
  `This Pokémon is not in the calculator data for ${reg.label} (not seen in its team usage): pick another regulation.`;

/** Regulation picker (#37), newest first: it sets the forms listed and the game whose learnsets are used. */
function regulationPicker(master: CalcMaster, onPick: (reg: CalcRegulation) => void) {
  const pick = el("select");
  options(pick, master.regulations.map((r) => [r.id, r.label]), master.regulations[0].id);
  pick.addEventListener("change", (e) => {
    e.stopPropagation();   // not an edit of a side
    onPick(master.regulations.find((r) => r.id === pick.value) ?? master.regulations[0]);
  });
  $("calc").prepend(el("div", { className: "filters calc-regulation" }, el("label", {}, "Regulation", pick),
    el("span", { className: "muted", textContent: "Pokémon seen in its team usage; learnsets of its game (PokéAPI)." })));
}

async function main() {
  let master: CalcMaster;
  try {
    const res = await fetch(`${BASE}calc_master.json`);
    if (!res.ok) throw new Error(`calc_master.json: HTTP ${res.status}`);
    master = parseCalcMaster(await res.json());
  } catch (e) {
    status.textContent = `Could not load the game data (${e instanceof Error ? e.message : e}). Reload the page to retry.`;
    return;
  }

  let engine: Engine | null = null;
  const calculate = () => {
    if (!engine) return;
    const a = attacker.read(), d = defender.read(), mv = master.moves.find((m) => m.id === attacker.moves()[0]);
    const bad = spreadError(a.evs, a.ivs) ?? spreadError(d.evs, d.ivs);
    if (bad) return showError(bad);
    if (!mv) return showError("Pick a move.");
    try {
      render(engine.calculate(buildRequest(master, a, d, mv)), a, d, mv);
    } catch (e) {
      showError(`The engine refused this input: ${pythonErrorMessage(e)}`);
    }
  };
  let reg = master.regulations[0];
  const scoped = { versionGroup: reg.version_group, onChange: calculate };
  const attacker = createPokemonEditor($("attacker"), master, { ...scoped, preferred: DEFAULTS.attacker, moveSlots: 1 });
  const defender = createPokemonEditor($("defender"), master, { ...scoped, preferred: DEFAULTS.defender, moveSlots: 0 });
  const editors: Record<CalcSide, PokemonEditor> = { attacker, defender };
  const scope = () => Object.values(editors).forEach((ed) => ed.setScope(reg.version_group, reg.forms));
  scope();
  regulationPicker(master, (r) => {
    reg = r;
    scope();
    teamNote.textContent = "";
    calculate();
  });
  savedTeamPicker($("attacker"), master, attacker, () => reg, calculate);
  savedTeamPicker($("defender"), master, defender, () => reg, calculate);

  // A team-builder link (#attacker=… / #defender=…) puts that member on its side.
  const openLink = () => {
    let link;
    try {
      link = readCalcLink(location.hash);
    } catch (e) {
      if (!(e instanceof TeamLinkError)) throw e;
      teamNote.textContent = `The team link could not be opened: ${e.message}`;
      return;
    }
    if (!link) return;
    history.replaceState(null, "", location.pathname + location.search);
    const notes = loadMember(master, editors[link.side], link.member, reg);
    teamNote.textContent = notes === null ? notInData(reg)
      : [`Team member loaded as ${link.side}.`, ...notes].join(" ");
    calculate();
  };
  openLink();
  window.addEventListener("hashchange", openLink);
  $("calc").hidden = false;

  status.textContent = "Loading the Python engine (Pyodide, about 5.6 MB on the first visit, then cached)…";
  try {
    engine = await loadEngine();
    const size = engine.bytes > 0 ? `, ${(engine.bytes / 2 ** 20).toFixed(1)} MiB downloaded` : "";
    status.textContent = `Python engine ready (Pyodide, loaded in ${engine.seconds.toFixed(1)} s${size}).`;
    calculate();
  } catch (e) {
    status.textContent = `The Python engine could not be loaded (${e instanceof Error ? e.message : e}). ` +
      "Check your connection or try another browser, then reload the page.";
  }
}

void main();
