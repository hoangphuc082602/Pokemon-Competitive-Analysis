"""
example_analysis.py
===================
Shows how to wire team_builder.build_pokemon() into
defensive + offensive analysis.
"""

from python.database.db_connection      import engine
from python.database.type_effectiveness_loader import load_type_effectiveness
from python.database.pokemon_loader     import load_all_pokemon_stats   # your existing loader
from python.database.moves_loader       import load_all_moves     # needs move name → type
from python.database.natures_loader      import load_all_natures    # your existing loader

from python.models.team_builder   import build_pokemon
from python.calculations.type_v2      import (
    analyze_team_defense,
    analyze_team_offense
)

# ── Load reference tables ──────────────────────────────────────────────────
type_chart_df = load_type_effectiveness()
pokemon_df    = load_all_pokemon_stats()
moves_df      = load_all_moves()      # must have columns: name, type
nature_df     = load_all_natures()

# ── Build each team member ─────────────────────────────────────────────────
charizard = build_pokemon(
    pokemon_df, nature_df,
    pokemon_name = "charizard",
    level        = 50,
    nature       = "timid",
    ability      = "blaze",
    item         = "charizardite-y",
    moves        = ["flamethrower", "air-slash", "focus-blast", "solar-beam"],
    ivs          = {"hp":31,"atk":31,"def":31,"spatk":31,"spdef":31,"spe":31},
    evs          = {"hp":0, "atk":0, "def":4, "spatk":252,"spdef":0,"spe":252},
)

venusaur = build_pokemon(
    pokemon_df, nature_df,
    pokemon_name = "venusaur",
    level        = 50,
    nature       = "modest",
    ability      = "chlorophyll",
    item         = "life-orb",
    moves        = ["sludge-bomb", "giga-drain", "earth-power", "sleep-powder"],
    ivs          = {"hp":31,"atk":0,"def":31,"spatk":31,"spdef":31,"spe":31},
    evs          = {"hp":4,"atk":0,"def":0,"spatk":252,"spdef":0,"spe":252},
)

# ... add Incineroar, Rotom, Garchomp, Milotic the same way

team = [charizard, venusaur]   # extend with full 6


# ── Run analyses ───────────────────────────────────────────────────────────
defense_report = analyze_team_defense(type_chart_df, team)
offense_report = analyze_team_offense(type_chart_df, moves_df, team)


# ── Quick print helpers ────────────────────────────────────────────────────
def print_defense_summary(report: dict):
    s = report["summary"]
    print(f"⚠  4× weaknesses  : {s['4x_weaknesses'] or 'none'}")
    print(f"🛡  Well-covered vs: {s['well_covered']   or 'none'}")
    print("\nNet score per type (negative = more exposed):")
    for t, data in sorted(report["by_type"].items(), key=lambda x: x[1]["net"]):
        bar = "█" * abs(data["net"]) if data["net"] else "-"
        sign = "+" if data["net"] > 0 else ""
        print(f"  {t:<10} {sign}{data['net']:>3}  {bar}")


def print_offense_summary(report: dict):
    s = report["summary"]
    print(f"✅  Types covered    : {s['coverage_count']}  → {s['covered_types']}")
    print(f"❌  Types not covered: {s['not_covered_count']} → {s['not_covered_types']}")
    print("\nPer-type breakdown:")
    for t, data in sorted(report["by_type"].items()):
        status = "✅" if data["is_covered"] else "❌"
        hitters = ", ".join(data["can_hit"]) or "—"
        print(f"  {status} {t:<10} covered by: {hitters}")

# ── Output ─────────────────────────────────────────────────────────────────
print("=" * 50)
print("  DEFENSIVE ANALYSIS")
print("=" * 50)
print_defense_summary(defense_report)

print("\n" + "=" * 50)
print("  OFFENSIVE ANALYSIS")
print("=" * 50)
print_offense_summary(offense_report)