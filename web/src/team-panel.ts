// Team panel of the calculator page (#17): build a team of up to 6 from the calculator sides, load a member into
// either side, save named teams in this browser, share a team as a link. DOM only; the logic is in team.ts.
import { displayName, movesFor, spreadError, STATS, type CalcMaster, type CalcMove, type SideInput } from "./calc";
import {
  decodeTeam,
  encodeTeam,
  MAX_MEMBERS,
  MAX_MOVES,
  MAX_NAME,
  resolveTeam,
  sideFromMember,
  teamError,
  TeamLinkError,
  type Team,
  type TeamMember,
  type TeamStore,
  withMember,
} from "./team";

/** One side of the calculator, as the team panel sees it. */
export interface SideControl {
  root: HTMLElement;
  read(): SideInput;
  move?: () => CalcMove | undefined;
  /** Shows this Pokémon (and move, on the attacker side) in the side and recalculates. */
  load(side: SideInput, moveId?: number): void;
}

type SideName = "attacker" | "defender";
const STAT_LABEL: Record<string, string> = { hp: "HP", atk: "Atk", def: "Def", spatk: "SpA", spdef: "SpD", spe: "Spe" };
const LINK_PREFIX = "#team=";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {},
  ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function spreadText(m: TeamMember): string {
  const evs = STATS.filter((s) => m.evs[s] > 0).map((s) => `${m.evs[s]} ${STAT_LABEL[s]}`).join(" / ") || "no EVs";
  const ivs = STATS.filter((s) => m.ivs[s] !== 31).map((s) => `${m.ivs[s]} ${STAT_LABEL[s]}`).join(" / ");
  return ivs ? `${evs} · IVs ${ivs}` : evs;
}

export function mountTeamPanel(root: HTMLElement, master: CalcMaster, store: TeamStore,
  sides: Record<SideName, SideControl>): void {
  const forms = new Map(master.forms.map((f) => [f.poke_id, f]));
  let team: Team = { name: "", members: [] };
  let savedId: string | null = null;
  let dirty = false;
  const editing: Record<SideName, number | null> = { attacker: null, defender: null };

  const status = el("p", { className: "context", role: "status", ariaLive: "polite" });
  const name = el("input", { type: "text", maxLength: MAX_NAME, placeholder: "Untitled team" });
  const saved = el("select");
  const button = (text: string) => el("button", { type: "button", textContent: text });
  const saveBtn = button("Save"), newBtn = button("New team"), deleteBtn = button("Delete saved team"),
    shareBtn = button("Share link");
  const share = el("input", { type: "text", readOnly: true, hidden: true, ariaLabel: "Share link" });
  const list = el("ol", { className: "team-list" });
  root.append(
    el("div", { className: "filters" }, el("label", {}, "Team name", name), el("label", {}, "Saved teams", saved)),
    el("div", { className: "team-actions" }, saveBtn, newBtn, deleteBtn, shareBtn),
    share, status, list,
    el("p", { className: "note" }, "Teams are saved in this browser only (no account, nothing is sent to a server). " +
      "A share link holds the whole team; opening one never changes your saved teams until you press Save. " +
      "Moves are limited to the damaging moves the calculator knows."),
  );

  const say = (...lines: string[]) => status.replaceChildren(...lines.flatMap((l, i) => (i ? [el("br"), l] : [l])));
  const changed = () => { dirty = true; };

  const addButtons = {} as Record<SideName, HTMLButtonElement>;
  const updateButtons = {} as Record<SideName, HTMLButtonElement>;
  const renderSideButtons = () => {
    for (const s of ["attacker", "defender"] as const) {
      const i = editing[s];
      addButtons[s].disabled = team.members.length >= MAX_MEMBERS;
      updateButtons[s].hidden = i === null;
      updateButtons[s].textContent = `Update team member ${(i ?? 0) + 1}`;
    }
  };

  const renderSaved = () => {
    const teams = store.list();
    const items: [string, string][] = teams.map((t) => [t.id, `${t.name || "Untitled team"} (${t.members.length})`]);
    if (savedId === null) items.unshift(["", "— not saved —"]);
    saved.replaceChildren(...items.map(([value, label]) => el("option", { value, textContent: label })));
    saved.value = savedId ?? "";
    deleteBtn.disabled = savedId === null;
  };

  const renderMembers = () => {
    list.replaceChildren(...team.members.map((m, i) => {
      const form = forms.get(m.poke_id)!;   // resolved team: every form is in the master data
      const options = movesFor(master, form).moves;
      const selects = Array.from({ length: MAX_MOVES }, (_, k) => {
        const sel = el("select", { ariaLabel: `${displayName(form.form)} move ${k + 1}` },
          el("option", { value: "", textContent: "—" }),
          ...options.map((mv) => el("option", { value: String(mv.id), textContent: displayName(mv.name) })));
        sel.value = m.moves[k] === undefined ? "" : String(m.moves[k]);
        sel.addEventListener("change", () => {
          m.moves = [...new Set(selects.map((s) => Number(s.value)).filter((v) => v > 0))];
          changed();
        });
        return sel;
      });
      const use = (side: SideName) => {
        sides[side].load(sideFromMember(form, m), side === "attacker" ? m.moves[0] : undefined);
        editing[side] = i;
        renderSideButtons();
        say(`${displayName(form.form)} is now the ${side}. Change it there, then press “Update team member ${i + 1}”.`);
      };
      const toAttacker = button("Attacker"), toDefender = button("Defender"), remove = button("Remove");
      toAttacker.addEventListener("click", () => use("attacker"));
      toDefender.addEventListener("click", () => use("defender"));
      remove.addEventListener("click", () => {
        team.members.splice(i, 1);
        editing.attacker = editing.defender = null;
        changed();
        render();
      });
      return el("li", { className: "member" },
        el("div", {}, el("strong", { textContent: displayName(form.form) }),
          el("span", { className: "muted", textContent: ` ${displayName(m.ability)} · ${displayName(m.nature)} · ${spreadText(m)}` })),
        el("div", { className: "member-moves" }, ...selects),
        el("div", { className: "team-actions" }, toAttacker, toDefender, remove));
    }));
    if (team.members.length === 0) list.append(el("li", { className: "muted", textContent: "No Pokémon yet: set one up as attacker or defender above and press “Add to team”." }));
  };

  const render = () => {
    name.value = team.name;
    renderSaved();
    renderMembers();
    renderSideButtons();
  };

  const open = (next: Team, id: string | null) => {
    const r = resolveTeam(master, next);
    team = r.team;
    savedId = id;
    dirty = r.notes.length > 0;   // a repaired team differs from what is stored
    editing.attacker = editing.defender = null;
    share.hidden = true;
    render();
    return r.notes;
  };

  const discardOk = () => !dirty ||
    confirm("The current team has unsaved changes. Discard them?");

  const putSide = (s: SideName, index: number | null) => {
    const side = sides[s].read();
    const bad = spreadError(side.evs, side.ivs);
    if (bad) return say(`Not added: ${bad}`);
    try {
      team = withMember(master, team, side, index, index === null ? sides[s].move?.()?.id : undefined);
    } catch (e) {
      return say(e instanceof Error ? e.message : String(e));
    }
    const i = index ?? team.members.length - 1;
    editing[s] = i;
    say(index === null ? `${displayName(side.form.form)} added to the team as member ${i + 1}.` : `Team member ${i + 1} updated.`);
    changed();
    renderMembers();
    renderSideButtons();
  };
  for (const s of ["attacker", "defender"] as const) {
    addButtons[s] = button("Add to team");
    updateButtons[s] = button("Update team member");
    addButtons[s].addEventListener("click", () => putSide(s, null));
    updateButtons[s].addEventListener("click", () => {
      const i = editing[s];
      if (i !== null && team.members[i]) putSide(s, i);
    });
    sides[s].root.append(el("div", { className: "team-actions side-team" }, addButtons[s], updateButtons[s]));
  }

  name.addEventListener("input", () => { team.name = name.value; changed(); });
  saved.addEventListener("change", () => {
    const pick = store.list().find((t) => t.id === saved.value);
    if (!pick || !discardOk()) return renderSaved();
    say(`Opened “${pick.name || "Untitled team"}”.`, ...open(pick, pick.id));
  });
  saveBtn.addEventListener("click", () => {
    team.name = name.value.trim();
    const bad = teamError(team);
    if (bad) return say(`Not saved: ${bad}`);
    const result = store.save(team, savedId ?? undefined);
    if (!result) {
      return say("This browser did not let the page store data (site data blocked, private window or storage full): " +
        "the team is not saved. The share link still keeps it.");
    }
    savedId = result.id;
    dirty = false;
    renderSaved();
    say(`Saved “${result.name || "Untitled team"}” in this browser.`);
  });
  newBtn.addEventListener("click", () => {
    if (!discardOk()) return;
    open({ name: "", members: [] }, null);
    say("New team (not saved yet).");
  });
  deleteBtn.addEventListener("click", () => {
    if (savedId === null || !confirm(`Delete the saved team “${team.name || "Untitled team"}” from this browser?`)) return;
    if (!store.remove(savedId)) return say("The saved team could not be deleted (storage unavailable).");
    savedId = null;
    dirty = true;   // still on screen, now unsaved
    renderSaved();
    say("Saved team deleted. It is still shown here: press Save to keep it again.");
  });
  shareBtn.addEventListener("click", () => {
    team.name = name.value.trim();
    const bad = teamError(team);
    if (bad) return say(`No link: ${bad}`);
    share.value = `${location.origin}${location.pathname}${LINK_PREFIX}${encodeTeam(team)}`;
    share.hidden = false;
    share.select();
    const copied = navigator.clipboard?.writeText(share.value);   // undefined outside a secure context
    if (!copied) return say("Copy the share link below.");
    copied.then(
      () => say("Share link copied. Anyone opening it sees this team; their saved teams are not changed."),
      () => say("Copy the share link below."));
  });

  /** A share link in the URL fragment: shown as an unsaved team; false when there is none or it was refused. */
  const openLink = (): boolean => {
    if (!location.hash.startsWith(LINK_PREFIX)) return false;
    const link = location.hash.slice(LINK_PREFIX.length);
    history.replaceState(null, "", location.pathname + location.search);   // reloading must not re-open the link
    try {
      const team = decodeTeam(link);
      if (!discardOk()) return true;
      const notes = open(team, null);
      dirty = true;
      say("Team opened from a share link. It is not saved: press Save to keep it in this browser. " +
        "Your saved teams are unchanged.", ...notes);
      return true;
    } catch (e) {
      if (!(e instanceof TeamLinkError)) throw e;
      say(`The team link could not be opened: ${e.message} Your saved teams are unchanged.`);
      return false;
    }
  };
  // A link pasted into a tab already on this page changes only the fragment: no reload.
  window.addEventListener("hashchange", () => { openLink(); });

  // Start: a share link wins (loaded as unsaved), otherwise the most recently saved team.
  if (!openLink()) {
    const refused = status.textContent ?? "";   // a refused link's message, kept above the repair notes
    const latest = store.list()[0];
    const notes = open(latest ?? { name: "", members: [] }, latest?.id ?? null);
    if (refused || notes.length) say(...[refused, ...notes].filter(Boolean));
  }
  root.hidden = false;
}
