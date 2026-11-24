// Showdown paste export (#20): a team as the text Pokémon Showdown's teambuilder imports. Export only. Pure: no DOM.
// Form names come from the parser's own override table (python/data_quality/showdown_overrides.csv, bundled as
// text), so a pasted name maps back to the same form under the parser's rules (pokemon_name_mapping.py).
import overridesCsv from "../../python/data_quality/showdown_overrides.csv?raw";
import { displayName, STATS, type CalcForm, type CalcMaster, type Stat } from "./calc";
import type { Team, TeamMember } from "./team";

/** Same as pokemon_name_mapping.normalize_name: 'Flutter Mane' -> 'flutter-mane', "Farfetch’d" -> 'farfetchd'. */
export function normalizeName(name: string): string {
  return name.normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase().trim()
    .replace(/[.'’:%]/g, "").replace(/[\s_]+/g, "-").replace(/-{2,}/g, "-").replace(/^-+|-+$/g, "");
}

/** showdown_overrides.csv (header showdown_name,pokemon) as [Showdown name, PokéAPI slug] rows, in file order. */
export function parseOverrides(csv: string): [string, string][] {
  return csv.trim().split(/\r?\n/).slice(1).map((line) => line.split(","))
    .filter((cells) => cells.length === 2 && cells[0].trim() && cells[1].trim())
    .map(([name, slug]) => [name.trim(), normalizeName(slug)]);
}

const namesOf = new Map<string, string[]>();
for (const [name, slug] of parseOverrides(overridesCsv)) namesOf.set(slug, [...(namesOf.get(slug) ?? []), name]);

/**
 * Showdown species name of a form: the species itself for its plain form ("Mr. Rime", not "Gastrodon-East"); else
 * the first override row of the form ("Landorus" for landorus-incarnate, "Minior" before "Minior-Meteor",
 * "Tauros-Paldea-Blaze" before "-Fire": the CSV lists Showdown's current name first); else species + form suffix
 * ("Calyrex-Shadow").
 */
export function showdownName(form: CalcForm): string {
  const base = normalizeName(form.species);
  if (form.form === base) return form.species;
  const names = namesOf.get(form.form);
  if (names) return names[0];
  return form.form.startsWith(`${base}-`) ? `${form.species}-${displayName(form.form.slice(base.length + 1))}` : displayName(form.form);
}

/** Showdown spellings a title-cased slug misses; any other spelling still imports (Showdown matches names by id). */
const SPELLED: Record<string, string> = {
  "u-turn": "U-turn", "v-create": "V-create", "x-scissor": "X-Scissor", "freeze-dry": "Freeze-Dry",
  "double-edge": "Double-Edge", "self-destruct": "Self-Destruct", "mud-slap": "Mud-Slap", "multi-attack": "Multi-Attack",
  "power-up-punch": "Power-Up Punch", "wake-up-slap": "Wake-Up Slap", "lands-wrath": "Land's Wrath",
  "natures-madness": "Nature's Madness", "kings-rock": "King's Rock", "never-melt-ice": "Never-Melt Ice",
  "well-baked-body": "Well-Baked Body", "minds-eye": "Mind's Eye", "soul-heart": "Soul-Heart",
  "as-one-glastrier": "As One (Glastrier)", "as-one-spectrier": "As One (Spectrier)",
};

/** Move / item / ability slug -> Showdown name: "booster-energy" -> "Booster Energy", "beads-of-ruin" -> "Beads of Ruin". */
function spelled(slug: string): string {
  return SPELLED[slug] ?? slug.split("-")
    .map((w, i) => (i > 0 && (w === "of" || w === "the") ? w : w.charAt(0).toUpperCase() + w.slice(1))).join(" ");
}

const LABEL: Record<Stat, string> = { hp: "HP", atk: "Atk", def: "Def", spatk: "SpA", spdef: "SpD", spe: "Spe" };

const spread = (values: Record<Stat, number>, skip: number) =>
  STATS.filter((s) => values[s] !== skip).map((s) => `${values[s]} ${LABEL[s]}`).join(" / ");

function memberPaste(master: CalcMaster, form: CalcForm, m: TeamMember): string {
  const moves = new Map(master.moves.map((mv) => [mv.id, mv.name]));
  const evs = spread(m.evs, 0), ivs = spread(m.ivs, 31);
  return [
    showdownName(form) + (m.item ? ` @ ${spelled(m.item)}` : ""),
    `Ability: ${spelled(m.ability)}`,
    `Level: ${master.level}`,
    ...(evs ? [`EVs: ${evs}`] : []),
    `${displayName(m.nature)} Nature`,
    ...(ivs ? [`IVs: ${ivs}`] : []),
    ...m.moves.map((id) => `- ${spelled(moves.get(id) ?? String(id))}`),
  ].map((line) => `${line}\n`).join("");
}

/**
 * The team in Showdown's paste format: one block per member (name @ item, ability, level, EVs, nature, IVs, moves),
 * blank line between blocks; "" for an empty team. Members must be resolved (resolveTeam): a form that is not in the
 * master data throws.
 */
export function showdownPaste(master: CalcMaster, team: Team): string {
  const forms = new Map(master.forms.map((f) => [f.poke_id, f]));
  return team.members.map((m) => {
    const form = forms.get(m.poke_id);
    if (!form) throw new Error(`Pokémon #${m.poke_id} is not in the calculator data.`);
    return memberPaste(master, form, m);
  }).join("\n");
}
