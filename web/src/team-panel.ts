// Team builder page (#17): a team of up to 6, each member edited in place (form, ability, nature, EVs / IVs, four
// moves), named teams saved in this browser, a share link, a Showdown paste (#20), and a link that opens a member in
// the damage calculator.
// Needs only calc_master.json: no Python engine. DOM only; the logic is in team.ts and showdown.ts.
import { defaultSide, displayName, type CalcMaster } from "./calc";
import { createPokemonEditor, el } from "./pokemon-editor";
import { showdownPaste } from "./showdown";
import {
  calcLink,
  decodeTeam,
  encodeTeam,
  itemClauseError,
  MAX_MEMBERS,
  MAX_MOVES,
  MAX_NAME,
  memberFromSide,
  resolveTeam,
  sideFromMember,
  teamError,
  TeamLinkError,
  type Team,
  type TeamStore,
} from "./team";

const LINK_PREFIX = "#team=";
const UNTITLED = "Untitled team";

/** onChange: called with the team shown after every edit, add, remove or open (team analysis, #19). */
export function mountTeamPanel(root: HTMLElement, master: CalcMaster, store: TeamStore, calcUrl: string,
  onChange: (team: Team) => void = () => {}): void {
  const forms = new Map(master.forms.map((f) => [f.poke_id, f]));
  let team: Team = { name: "", members: [] };
  let savedId: string | null = null;
  let dirty = false;

  const status = el("p", { className: "context", role: "status", ariaLive: "polite" });
  const name = el("input", { type: "text", maxLength: MAX_NAME, placeholder: UNTITLED });
  const saved = el("select");
  const button = (text: string) => el("button", { type: "button", textContent: text });
  const saveBtn = button("Save"), newBtn = button("New team"), deleteBtn = button("Delete saved team"),
    shareBtn = button("Share link"), pasteBtn = button("Showdown paste"), addBtn = button("Add Pokémon");
  const share = el("input", { type: "text", readOnly: true, hidden: true, ariaLabel: "Share link" });
  const paste = el("textarea", { readOnly: true, hidden: true, rows: 12, className: "paste", ariaLabel: "Showdown paste" });
  const list = el("ol", { className: "team-list" });
  const clause = el("p", { className: "down", role: "alert", hidden: true });
  root.append(
    el("div", { className: "filters" }, el("label", {}, "Team name", name), el("label", {}, "Saved teams", saved)),
    el("div", { className: "team-actions" }, saveBtn, newBtn, deleteBtn, shareBtn, pasteBtn),
    share, paste, status, clause, list,
    el("div", { className: "team-actions" }, addBtn),
  );

  /** Item clause shown as soon as two members hold the same item; Save and Share link refuse such a team. */
  const renderClause = () => {
    const bad = itemClauseError(team);
    clause.textContent = bad ?? "";
    clause.hidden = bad === null;
  };

  const say = (...lines: string[]) => status.replaceChildren(...lines.flatMap((l, i) => (i ? [el("br"), l] : [l])));

  /** The team changed: the share link and paste shown no longer match it (#41). */
  const edited = () => {
    dirty = true;
    share.hidden = true;
    paste.hidden = true;
  };

  /** Shows text in its read-only field, selected, and copies it; the field stays as the fallback. */
  const showAndCopy = (field: HTMLInputElement | HTMLTextAreaElement, text: string, copiedMsg: string, fallbackMsg: string) => {
    field.value = text;
    field.hidden = false;
    field.select();
    const copied = navigator.clipboard?.writeText(text);   // undefined outside a secure context
    if (!copied) return say(fallbackMsg);
    copied.then(() => say(copiedMsg), () => say(fallbackMsg));
  };

  const renderSaved = () => {
    const items: [string, string][] = store.list().map((t) => [t.id, `${t.name || UNTITLED} (${t.members.length})`]);
    if (savedId === null) items.unshift(["", "— not saved —"]);
    saved.replaceChildren(...items.map(([value, label]) => el("option", { value, textContent: label })));
    saved.value = savedId ?? "";
    deleteBtn.disabled = savedId === null;
  };

  const renderMembers = () => {
    list.replaceChildren(...team.members.map((m, i) => {
      const box = el("fieldset", { className: "side member" }, el("legend", { textContent: `Pokémon ${i + 1}` }));
      const calcLinks = { attacker: el("a", { textContent: "Attacker in calc ↗" }), defender: el("a", { textContent: "Defender in calc ↗" }) };
      const refreshLinks = () => {
        for (const side of ["attacker", "defender"] as const) calcLinks[side].href = calcUrl + calcLink(side, team.members[i]);
      };
      const editor = createPokemonEditor(box, master, { moveSlots: MAX_MOVES, withItem: true, onChange: () => {
        team.members[i] = memberFromSide(editor.read(), editor.moves(), editor.item());
        edited();
        refreshLinks();
        renderClause();
        onChange(team);
      } });
      editor.load(sideFromMember(forms.get(m.poke_id)!, m), m.moves, m.item);   // resolved team: the form is in the data
      refreshLinks();
      const remove = button("Remove");
      remove.addEventListener("click", () => {
        team.members.splice(i, 1);
        edited();
        renderMembers();
      });
      box.append(el("div", { className: "team-actions" }, calcLinks.attacker, calcLinks.defender, remove));
      return el("li", {}, box);
    }));
    if (team.members.length === 0) list.append(el("li", { className: "muted", textContent: "No Pokémon yet: press “Add Pokémon”." }));
    addBtn.disabled = team.members.length >= MAX_MEMBERS;
    renderClause();
    onChange(team);
  };

  const render = () => {
    name.value = team.name;
    share.hidden = true;
    paste.hidden = true;
    renderSaved();
    renderMembers();
  };

  /** Shows a team (checked against the game data); returns the notes on what had to change. */
  const open = (next: Team, id: string | null) => {
    const r = resolveTeam(master, next);
    team = r.team;
    savedId = id;
    dirty = r.notes.length > 0;   // a repaired team differs from what is stored
    render();
    return r.notes;
  };

  const discardOk = () => !dirty || confirm("The current team has unsaved changes. Discard them?");

  /** The team as shown, or a message when it cannot be saved / shared. */
  const current = (): Team | string => {
    team.name = name.value.trim();
    return teamError(team) ?? team;   // includes each member's EV / IV limits
  };

  addBtn.addEventListener("click", () => {
    if (team.members.length >= MAX_MEMBERS) return;
    const first = [...master.forms].sort((a, b) => displayName(a.form).localeCompare(displayName(b.form)))[0];
    team.members.push(memberFromSide(defaultSide(first), [], ""));
    edited();
    renderMembers();
  });
  name.addEventListener("input", () => { team.name = name.value; edited(); });
  saved.addEventListener("change", () => {
    const pick = store.list().find((t) => t.id === saved.value);
    if (!pick || !discardOk()) return renderSaved();
    say(`Opened “${pick.name || UNTITLED}”.`, ...open(pick, pick.id));
  });
  saveBtn.addEventListener("click", () => {
    const t = current();
    if (typeof t === "string") return say(`Not saved: ${t}`);
    const result = store.save(t, savedId ?? undefined);
    if (!result) {
      return say("This browser did not let the page store data (site data blocked, private window or storage full): " +
        "the team is not saved. The share link still keeps it.");
    }
    savedId = result.id;
    dirty = false;
    renderSaved();
    say(`Saved “${result.name || UNTITLED}” in this browser.`);
  });
  newBtn.addEventListener("click", () => {
    if (!discardOk()) return;
    open({ name: "", members: [] }, null);
    say("New team (not saved yet).");
  });
  deleteBtn.addEventListener("click", () => {
    if (savedId === null || !confirm(`Delete the saved team “${team.name || UNTITLED}” from this browser?`)) return;
    if (!store.remove(savedId)) return say("The saved team could not be deleted (storage unavailable).");
    savedId = null;
    dirty = true;   // still on screen, now unsaved
    renderSaved();
    say("Saved team deleted. It is still shown here: press Save to keep it again.");
  });
  shareBtn.addEventListener("click", () => {
    const t = current();
    if (typeof t === "string") return say(`No link: ${t}`);
    showAndCopy(share, `${location.origin}${location.pathname}${LINK_PREFIX}${encodeTeam(t)}`,
      "Share link copied. Anyone opening it sees this team; their saved teams are not changed.",
      "Copy the share link below.");
  });

  pasteBtn.addEventListener("click", () => {
    const t = current();
    if (typeof t === "string") return say(`No paste: ${t}`);
    if (t.members.length === 0) return say("No paste: the team has no Pokémon.");
    showAndCopy(paste, showdownPaste(master, t),
      "Showdown paste copied: import it in Showdown's teambuilder (Import from text).", "Copy the Showdown paste below.");
  });

  /** A share link in the URL fragment: shown as an unsaved team; false when there is none or it was refused. */
  const openLink = (): boolean => {
    if (!location.hash.startsWith(LINK_PREFIX)) return false;
    const link = location.hash.slice(LINK_PREFIX.length);
    history.replaceState(null, "", location.pathname + location.search);   // reloading must not re-open the link
    try {
      const linked = decodeTeam(link);
      if (!discardOk()) return true;
      const notes = open(linked, null);
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

  // Start: a share link wins (opened as unsaved), otherwise the most recently saved team.
  if (!openLink()) {
    const refused = status.textContent ?? "";   // a refused link's message, kept above the repair notes
    const latest = store.list()[0];
    const notes = open(latest ?? { name: "", members: [] }, latest?.id ?? null);
    if (refused || notes.length) say(...[refused, ...notes].filter(Boolean));
  }
  root.hidden = false;
}
