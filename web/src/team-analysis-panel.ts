// Team analysis section of the team page (#19): speed tiers, roles, type weakness / resistance table and synergy
// score, all computed by the Python engine (calc_facade.team_summary) through Pyodide. The engine is downloaded only
// when the visitor asks for the analysis; after that the analysis follows every edit. DOM only; logic in team-analysis.ts.
import { displayName, type CalcMaster } from "./calc";
import { loadEngine, pythonErrorMessage, type Engine } from "./engine";
import { el } from "./pokemon-editor";
import { teamError, type Team } from "./team";
import { buildTeamSummaryRequest, multiplierLabel, roleLabel, type Role, type TeamSummary } from "./team-analysis";

const DEBOUNCE_MS = 250;

const table = (head: string[], rows: HTMLTableRowElement[], numericFrom = 1) =>
  el("div", { className: "table-scroll" }, el("table", {},
    el("thead", {}, el("tr", {}, ...head.map((h, i) => el("th", { scope: "col", className: i >= numericFrom ? "num" : "", textContent: h })))),
    el("tbody", {}, ...rows)));

const td = (text: string, className = "num") => el("td", { className, textContent: text });

function render(out: HTMLElement, s: TeamSummary, team: Team) {
  const items = new Map(   // species clause: one Pokémon per name
    s.members.map((m, i) => [m.name, team.members[i].item]));
  const speed = el("section", {}, el("h3", { textContent: "Speed tiers" }),
    el("p", { className: "context", textContent: "Level-50 Speed, fastest first, with Choice Scarf (×1.5) and Iron Ball (×0.5). " +
      "Not included: Tailwind, Trick Room, paralysis, stat stages, speed abilities." }),
    table(["Pokémon", "Speed"], s.speed_tiers.map((t) => el("tr", {},
      el("th", { scope: "row", textContent: t.name + (items.get(t.name) ? ` (${displayName(items.get(t.name)!)})` : "") }),
      td(String(t.speed))))));

  const roleCounts = (Object.entries(s.roles) as [Role, number][]).map(([r, n]) => `${roleLabel(r)}: ${n}`).join(" · ");
  const roles = el("section", {}, el("h3", { textContent: "Roles" }),
    el("p", { className: "context", textContent: "Engine rule on level-50 stats: Atk or SpA ≥ 170 with Spe ≥ 150 = sweeper; " +
      "otherwise Def or SpD ≥ 150 = wall; else balanced. A stat-based label, not how the Pokémon is used in battles." }),
    el("p", { textContent: roleCounts }),
    table(["Pokémon", "Role", "Atk", "SpA", "Def", "SpD", "Spe"], s.members.map((m) => el("tr", {},
      el("th", { scope: "row", textContent: m.name }), td(roleLabel(m.role), ""),
      ...(["atk", "spatk", "def", "spdef", "spe"] as const).map((k) => td(String(m.stats[k]))))), 2));

  const types = el("section", {}, el("h3", { textContent: "Type weaknesses and resistances" }),
    el("p", { className: "context", textContent: "Damage multiplier of each attacking type on each member (type chart from " +
      "PokéAPI plus the member's defensive ability, e.g. Levitate, Flash Fire); blank = neutral. Tera, weather and " +
      "attacker abilities are not included." }),
    table(["Attacking type", ...s.members.map((m) => m.name), "Weak", "Resist", "Immune"], s.type_table.map((r) => el("tr", {},
      el("th", { scope: "row", textContent: displayName(r.type) }),
      ...r.multipliers.map((x) => td(multiplierLabel(x), x > 1 ? "num down" : x < 1 ? "num up" : "num")),
      td(String(r.weak), r.weak >= 3 ? "num down" : "num"), td(String(r.resist)), td(String(r.immune))))));

  const synergy = el("section", {}, el("h3", { textContent: "Synergy score" }),
    el("p", {}, el("strong", { textContent: String(s.synergy_score) })),
    el("p", { className: "context", textContent: "Count over the table above: (resisted + immune) − weak, one per member and " +
      "attacking type. A simple defensive tally, not a validated measure of team strength." }));
  out.replaceChildren(speed, roles, types, synergy);
}

/** Mounts the section; returns the function the team panel calls with the team shown. */
export function mountTeamAnalysis(root: HTMLElement, master: CalcMaster): (team: Team) => void {
  const start = el("button", { type: "button", textContent: "Analyse this team" });
  const status = el("p", { className: "context", role: "status", ariaLive: "polite",
    textContent: "Runs the project's Python engine in the browser (Pyodide, about 5.6 MB on the first use, then cached)." });
  const out = el("div", { className: "team-analysis" });
  root.append(el("h2", { textContent: "Team analysis" }), el("div", { className: "team-actions" }, start), status, out);

  let engine: Engine | null = null;
  let team: Team = { name: "", members: [] };
  let timer: ReturnType<typeof setTimeout> | undefined;

  const run = () => {
    if (!engine) return;
    if (team.members.length === 0) return out.replaceChildren(el("p", { className: "muted", textContent: "Add Pokémon to analyse the team." }));
    const bad = teamError(team);
    if (bad) return out.replaceChildren(el("p", { className: "down", textContent: `Fix the team to analyse it: ${bad}` }));
    try {
      render(out, engine.teamSummary(buildTeamSummaryRequest(master, team)), team);
    } catch (e) {
      out.replaceChildren(el("p", { className: "down", textContent: `The engine refused this team: ${pythonErrorMessage(e)}` }));
    }
  };

  start.addEventListener("click", async () => {
    start.disabled = true;
    status.textContent = "Loading the Python engine…";
    try {
      engine = await loadEngine();
      start.hidden = true;
      status.textContent = `Python engine ready (loaded in ${engine.seconds.toFixed(1)} s). The analysis follows every change to the team.`;
      run();
    } catch (e) {
      start.disabled = false;
      status.textContent = `The Python engine could not be loaded (${e instanceof Error ? e.message : e}). Press the button to retry.`;
    }
  });

  return (next: Team) => {
    team = next;
    clearTimeout(timer);
    timer = setTimeout(run, DEBOUNCE_MS);
  };
}
