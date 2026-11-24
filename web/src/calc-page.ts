import "./style.css";
import {
  buildRequest,
  defaultSide,
  displayName,
  koLabel,
  movesFor,
  parseCalcMaster,
  spreadError,
  STATS,
  type CalcForm,
  type CalcMaster,
  type CalcMove,
  type CalcResult,
  type SideInput,
  type Stats,
} from "./calc";
import { loadEngine, pythonErrorMessage, type Engine } from "./engine";
import { browserStorage, createTeamStore } from "./team";
import { mountTeamPanel, type SideControl } from "./team-panel";

const BASE = `${import.meta.env.BASE_URL}data/`;
const STAT_LABEL: Record<string, string> = { hp: "HP", atk: "Atk", def: "Def", spatk: "SpA", spdef: "SpD", spe: "Spe" };
const DEFAULTS = { attacker: "flutter-mane", defender: "incineroar" };   // fall back to the first form when absent

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const status = $<HTMLParagraphElement>("engine-status");

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {},
  ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function options(select: HTMLSelectElement, items: [string, string][], selected?: string) {
  select.replaceChildren(...items.map(([value, label]) => el("option", { value, label, textContent: label })));
  if (selected !== undefined && items.some(([v]) => v === selected)) select.value = selected;
}

function natureLabel(n: CalcMaster["natures"][number]): string {
  const name = displayName(n.name);
  return n.increased && n.decreased && n.increased !== n.decreased
    ? `${name} (+${STAT_LABEL[n.increased]} −${STAT_LABEL[n.decreased]})` : `${name} (neutral)`;
}

function spreadInputs(legend: string, value: number, max: number):
  { box: HTMLFieldSetElement; read: () => Stats; write: (v: Stats) => void } {
  const inputs = STATS.map((s) => el("input", { type: "number", min: "0", max: String(max), step: "1", value: String(value),
    inputMode: "numeric", ariaLabel: `${legend} ${STAT_LABEL[s]}` }));
  const box = el("fieldset", { className: "spread" }, el("legend", { textContent: legend }),
    ...STATS.map((s, i) => el("label", {}, STAT_LABEL[s], inputs[i])));
  const read = () => Object.fromEntries(STATS.map((s, i) => [s, Number(inputs[i].value)])) as Stats;
  const write = (v: Stats) => STATS.forEach((s, i) => { inputs[i].value = String(v[s]); });
  return { box, read, write };
}

function buildSide(root: HTMLFieldSetElement, master: CalcMaster, preferred: string, attacker: boolean,
  onChange: () => void): SideControl {
  const forms = [...master.forms].sort((a, b) => displayName(a.form).localeCompare(displayName(b.form)));
  const byId = new Map(forms.map((f) => [String(f.poke_id), f]));
  const start = forms.find((f) => f.form === preferred) ?? forms[0];
  const pokemon = el("select"), ability = el("select"), nature = el("select"), move = el("select");
  const note = el("p", { className: "note" });
  const moveNote = el("p", { className: "note" });
  options(pokemon, forms.map((f) => [String(f.poke_id), displayName(f.form)]), String(start.poke_id));
  options(nature, master.natures.map((n) => [n.name, natureLabel(n)]), "hardy");
  const evs = spreadInputs("EVs", 0, 252), ivs = spreadInputs("IVs", 31, 31);
  const types = el("span", { className: "muted" });

  const form = (): CalcForm => byId.get(pokemon.value) ?? start;
  const refreshForm = () => {
    const f = form();
    const side = defaultSide(f);
    options(ability, f.abilities.map((a) => [a, displayName(a)]), side.ability);
    types.textContent = f.types.map(displayName).join(" / ");
    const borrowed = master.forms.find((x) => x.poke_id === f.borrowed_from);
    note.textContent = f.borrowed_from === null ? ""
      : `Abilities and moves of ${displayName(borrowed?.form ?? String(f.borrowed_from))}: the game data has none for this form.`;
    if (attacker) {
      const { moves, fromLearnset } = movesFor(master, f);
      const keep = move.value;
      options(move, moves.map((m) => [String(m.id), `${displayName(m.name)} (${displayName(m.type)}, ${m.power}, ${m.damage_class})`]), keep);
      moveNote.textContent = fromLearnset ? "" : "No learnset in the game data for this form: every exported move is listed.";
    }
  };
  pokemon.addEventListener("change", refreshForm);
  refreshForm();

  root.append(
    el("div", { className: "filters" },
      el("label", {}, "Pokémon", pokemon), el("label", {}, "Ability", ability), el("label", {}, "Nature", nature)),
    el("p", { className: "context" }, "Type: ", types),
    note,
    ...(attacker ? [el("div", { className: "filters" }, el("label", {}, "Move", move)), moveNote] : []),
    evs.box,
    el("details", {}, el("summary", { textContent: "IVs (31 by default)" }), ivs.box),
  );
  root.addEventListener("input", onChange);
  root.addEventListener("change", onChange);

  const moveById = new Map(master.moves.map((m) => [String(m.id), m]));
  return {
    root,
    read: () => ({ form: form(), ability: ability.value, nature: nature.value, evs: evs.read(), ivs: ivs.read() }),
    move: attacker ? () => moveById.get(move.value) : undefined,
    load(s, moveId) {
      pokemon.value = String(s.form.poke_id);
      refreshForm();
      ability.value = s.ability;
      nature.value = s.nature;
      evs.write(s.evs);
      ivs.write(s.ivs);
      if (attacker && moveId !== undefined && moveById.has(String(moveId))) move.value = String(moveId);
      onChange();
    },
  };
}

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
    const a = attacker.read(), d = defender.read(), mv = attacker.move?.();
    const bad = spreadError(a.evs, a.ivs) ?? spreadError(d.evs, d.ivs);
    if (bad) return showError(bad);
    if (!mv) return showError("Pick a move.");
    try {
      render(engine.calculate(buildRequest(master, a, d, mv)), a, d, mv);
    } catch (e) {
      showError(`The engine refused this input: ${pythonErrorMessage(e)}`);
    }
  };
  const attacker = buildSide($("attacker"), master, DEFAULTS.attacker, true, calculate);
  const defender = buildSide($("defender"), master, DEFAULTS.defender, false, calculate);
  $("calc").hidden = false;
  mountTeamPanel($("team"), master, createTeamStore(browserStorage), { attacker, defender });

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
