// One Pokémon's set (form, ability, nature, EVs / IVs, moves) as form controls. Shared by the damage calculator
// (calc-page.ts: attacker with one move, defender with none) and the team builder (team-panel.ts: four moves, item).
// DOM only; the rules (spread limits, learnsets) are in calc.ts.
import { defaultSide, displayName, movesFor, STATS, type CalcForm, type CalcMaster, type SideInput, type Stats } from "./calc";

export const STAT_LABEL: Record<string, string> = { hp: "HP", atk: "Atk", def: "Def", spatk: "SpA", spdef: "SpD", spe: "Spe" };

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {},
  ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

export function options(select: HTMLSelectElement, items: [string, string][], selected?: string) {
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

export interface PokemonEditor {
  read(): SideInput;
  /** Picked move ids, in slot order, without blanks or repeats. */
  moves(): number[];
  /** Held item name, "" = none (always "" without the item control). */
  item(): string;
  /** Shows this set; moves the form cannot use are left blank. Fires no change event. */
  load(side: SideInput, moves: number[], item?: string): void;
}

export interface EditorOptions {
  /** Form slug shown first; the first form (by name) when absent from the data. */
  preferred?: string;
  /** 0 = no move (defender), 1 = one required move (attacker), more = optional slots with a blank (team). */
  moveSlots: number;
  /** Shows an item control (team builder); the damage engine does not model items. */
  withItem?: boolean;
  /** Called on every edit made by the user. */
  onChange: () => void;
}

export function createPokemonEditor(root: HTMLElement, master: CalcMaster, opts: EditorOptions): PokemonEditor {
  const forms = [...master.forms].sort((a, b) => displayName(a.form).localeCompare(displayName(b.form)));
  const byId = new Map(forms.map((f) => [String(f.poke_id), f]));
  const start = forms.find((f) => f.form === opts.preferred) ?? forms[0];
  const pokemon = el("select"), ability = el("select"), nature = el("select"), item = el("select");
  const moveSelects = Array.from({ length: opts.moveSlots }, () => el("select"));
  const note = el("p", { className: "note" });
  const moveNote = el("p", { className: "note" });
  options(pokemon, forms.map((f) => [String(f.poke_id), displayName(f.form)]), String(start.poke_id));
  options(nature, master.natures.map((n) => [n.name, natureLabel(n)]), "hardy");
  const evs = spreadInputs("EVs", 0, 252), ivs = spreadInputs("IVs", 31, 31);
  const types = el("span", { className: "muted" });
  const optional = opts.moveSlots > 1;
  if (opts.withItem) {
    item.append(el("option", { value: "", textContent: "— no item —" }));
    const groups = new Map<string, HTMLOptGroupElement>();
    for (const it of master.items) {
      if (!groups.has(it.category)) groups.set(it.category, el("optgroup", { label: displayName(it.category) }));
      groups.get(it.category)!.append(el("option", { value: it.name, textContent: displayName(it.name) }));
    }
    item.append(...[...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, g]) => g));
  }

  const form = (): CalcForm => byId.get(pokemon.value) ?? start;
  const refreshForm = () => {
    const f = form();
    options(ability, f.abilities.map((a) => [a, displayName(a)]), defaultSide(f).ability);
    types.textContent = f.types.map(displayName).join(" / ");
    const borrowed = master.forms.find((x) => x.poke_id === f.borrowed_from);
    note.textContent = f.borrowed_from === null ? ""
      : `Abilities and moves of ${displayName(borrowed?.form ?? String(f.borrowed_from))}: the game data has none for this form.`;
    if (opts.moveSlots === 0) return;
    const { moves, fromLearnset } = movesFor(master, f);
    const items: [string, string][] = moves.map((m) =>
      [String(m.id), `${displayName(m.name)} (${displayName(m.type)}, ${m.power}, ${m.damage_class})`]);
    for (const sel of moveSelects) options(sel, optional ? [["", "—"], ...items] : items, sel.value);
    moveNote.textContent = fromLearnset ? "" : "No learnset in the game data for this form: every exported move is listed.";
  };
  pokemon.addEventListener("change", refreshForm);
  refreshForm();

  const moveRow = opts.moveSlots === 0 ? [] : [
    el("div", { className: optional ? "member-moves" : "filters" },
      ...moveSelects.map((sel, i) => el("label", {}, optional ? `Move ${i + 1}` : "Move", sel))),
    moveNote,
  ];
  root.append(
    el("div", { className: "filters" },
      el("label", {}, "Pokémon", pokemon), el("label", {}, "Ability", ability), el("label", {}, "Nature", nature),
      ...(opts.withItem ? [el("label", {}, "Item", item)] : [])),
    el("p", { className: "context" }, "Type: ", types),
    note,
    ...moveRow,
    evs.box,
    el("details", {}, el("summary", { textContent: "IVs (31 by default)" }), ivs.box),
  );
  root.addEventListener("input", opts.onChange);
  root.addEventListener("change", opts.onChange);

  return {
    read: () => ({ form: form(), ability: ability.value, nature: nature.value, evs: evs.read(), ivs: ivs.read() }),
    moves: () => [...new Set(moveSelects.map((s) => Number(s.value)).filter((v) => v > 0))],
    item: () => (opts.withItem ? item.value : ""),
    load(s, moves, held = "") {
      pokemon.value = String(s.form.poke_id);
      refreshForm();
      ability.value = s.ability;
      nature.value = s.nature;
      evs.write(s.evs);
      ivs.write(s.ivs);
      if (opts.withItem) item.value = held;
      moveSelects.forEach((sel, i) => {
        const id = moves[i] === undefined ? "" : String(moves[i]);
        if ([...sel.options].some((o) => o.value === id)) sel.value = id;
        else if (optional) sel.value = "";
      });
    },
  };
}
