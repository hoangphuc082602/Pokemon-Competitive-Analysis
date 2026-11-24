// Team analysis (#19): the request sent to the Python façade's team_summary (python/calculations/calc_facade.py), its
// response and display labels. Pure: no DOM, no Pyodide; tested with Vitest. The numbers come from the engine only.
import { displayName, facadeSide, type CalcMaster, type Stats } from "./calc";
import { sideFromMember, type Team } from "./team";

export type Role = "physical_sweeper" | "special_sweeper" | "wall" | "balanced";

export interface TeamSummary {
  members: { name: string; stats: Stats; speed: number; role: Role }[];
  speed_tiers: { name: string; speed: number }[];
  roles: Partial<Record<Role, number>>;
  type_table: { type: string; multipliers: number[]; weak: number; resist: number; immune: number }[];
  synergy_score: number;
}

/** The JSON request of calc_facade.team_summary; members must be resolved (their form in the master data). */
export function buildTeamSummaryRequest(master: CalcMaster, team: Team) {
  const forms = new Map(master.forms.map((f) => [f.poke_id, f]));
  const members = team.members.map((m) => {
    const form = forms.get(m.poke_id);
    if (!form) throw new Error(`Pokémon ${m.poke_id} is not in the game data.`);
    return { name: displayName(form.form), item: m.item, ...facadeSide(master, sideFromMember(form, m)) };
  });
  return { members, type_chart: master.type_chart };
}

const ROLE_LABEL: Record<Role, string> = {
  physical_sweeper: "Physical sweeper", special_sweeper: "Special sweeper", wall: "Wall", balanced: "Balanced",
};

export const roleLabel = (role: Role): string => ROLE_LABEL[role] ?? role;

const FRACTION: Record<string, string> = { "0.5": "½", "0.25": "¼" };

/** 4 -> "×4", 0.5 -> "×½", 0 -> "×0"; neutral (1) is blank so the table shows only what matters. */
export function multiplierLabel(x: number): string {
  if (x === 1) return "";
  return `×${FRACTION[String(x)] ?? x}`;
}
