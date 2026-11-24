"""Damage-calc façade for the browser (#16, ADR-014): the only module Pyodide calls.

Seam: calc_facade.calculate(request) -> dict, JSON in / JSON out. The façade must give the same numbers as the
existing engine path (stats_calc + nature_calc + damage_calc_v2 on a DataFrame type chart) for equivalent inputs.
"""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from python.calculations.calc_facade import calculate, calculate_json
from python.calculations.damage_calc_v2 import calculate_damage
from python.calculations.nature_calc import get_nature_modifiers
from python.calculations.stats_calc import calculate_final_stats

REPO_ROOT = Path(__file__).resolve().parents[2]
STATS = ["hp", "atk", "def", "spatk", "spdef", "spe"]
# pokemon_nature_info.csv layout: stat ids 2..6 = atk, def, spatk, spdef, spe; neutral natures have no ids
NATURES = pd.DataFrame([("adamant", 2, 4), ("modest", 4, 2), ("hardy", None, None), ("bold", 3, 2)],
                       columns=["nature_name", "increased_stat", "decreased_stat"])
NATURE_JSON = {"adamant": {"increased": "atk", "decreased": "spatk"}, "modest": {"increased": "spatk", "decreased": "atk"},
               "hardy": {"increased": None, "decreased": None}, "bold": {"increased": "def", "decreased": "atk"},
               "timid": {"increased": "spe", "decreased": "atk"}}


def _spread(**kw):
    return {s: kw.get(s, 0) for s in STATS}


def side(types, base, nature, evs=None, ivs=None, ability="none"):
    return {"types": types, "ability": ability, "base_stats": dict(zip(STATS, base)), "nature": NATURE_JSON[nature],
            "evs": evs or _spread(), "ivs": ivs or {s: 31 for s in STATS}}


def request(attacker, defender, move, type_chart_df):
    return {"attacker": attacker, "defender": defender, "move": move,
            "type_chart": type_chart_df[["attack_type", "defense_type", "multiplier"]].values.tolist()}


def engine(attacker, defender, nature_a, nature_d, move, type_chart_df):
    """The existing path: final stats from stats_calc + nature_calc (DataFrame), damage from damage_calc_v2."""
    def battler(s, nature):
        stats = calculate_final_stats(s["base_stats"], s["ivs"], s["evs"], 50, get_nature_modifiers(NATURES, nature))
        return {"types": s["types"], "ability": s["ability"], "level": 50, "stats": stats}
    return calculate_damage(battler(attacker, nature_a), battler(defender, nature_d), move, type_chart_df)


def test_level_50_stats_match_known_values(type_chart_df):
    # base 100 / IV 31 / EV 252 at level 50: HP 207; +Atk nature 167; -SpA nature 108 (floor(120 * 0.9))
    a = side(["fire"], [100] * 6, "adamant", evs=_spread(hp=252, atk=252))
    out = calculate(request(a, a, {"type": "fire", "power": 80, "damage_class": "physical"}, type_chart_df))
    assert out["attacker_stats"] == {"hp": 207, "atk": 167, "def": 120, "spatk": 108, "spdef": 120, "spe": 120}


CASES = [
    # attacker, defender, natures, move
    (side(["fire"], [80, 130, 80, 60, 80, 100], "adamant", evs=_spread(atk=252, spe=252)),
     side(["grass"], [100, 80, 100, 80, 100, 50], "bold", evs=_spread(hp=252, **{"def": 252})),
     ("adamant", "bold"), {"type": "fire", "power": 120, "damage_class": "physical"}),
    (side(["fairy", "fire"], [70, 60, 70, 135, 90, 105], "modest", evs=_spread(spatk=252)),
     side(["dragon"], [108, 130, 95, 80, 85, 102], "hardy"),
     ("modest", "hardy"), {"type": "fairy", "power": 95, "damage_class": "special"}),
    (side(["normal"], [100] * 6, "hardy", ability="scrappy"), side(["ghost"], [60] * 6, "hardy"),
     ("hardy", "hardy"), {"type": "normal", "power": 90, "damage_class": "physical"}),
    (side(["electric"], [100] * 6, "modest"), side(["ground"], [100] * 6, "hardy"),
     ("modest", "hardy"), {"type": "electric", "power": 90, "damage_class": "special"}),
    (side(["water"], [100] * 6, "modest"), side(["fire"], [100] * 6, "hardy", ability="Flash Fire"),
     ("modest", "hardy"), {"type": "water", "power": 90, "damage_class": "special"}),
    (side(["water"], [100] * 6, "modest"), side(["fire"], [100] * 6, "hardy", ability="flash-fire"),   # PokéAPI slug
     ("modest", "hardy"), {"type": "fire", "power": 90, "damage_class": "special"}),
]


@pytest.mark.parametrize("attacker,defender,natures,move", CASES)
def test_facade_equals_the_existing_damage_calculation(attacker, defender, natures, move, type_chart_df):
    out = calculate(request(attacker, defender, move, type_chart_df))
    ref = engine(attacker, defender, *natures, move, type_chart_df)
    for key in ("min_damage", "max_damage", "ohko_chance", "two_hko_chance", "type_modifier", "stab", "category"):
        assert out[key] == ref[key], key
    hp = out["defender_stats"]["hp"]
    assert out["min_percent"] == round(100 * ref["min_damage"] / hp, 1)
    assert out["max_percent"] == round(100 * ref["max_damage"] / hp, 1)


def test_output_is_json_serialisable_and_the_json_entry_point_round_trips(type_chart_df):
    attacker, defender, _, move = CASES[0]
    req = request(attacker, defender, move, type_chart_df)
    out = calculate(req)
    assert json.loads(json.dumps(out, allow_nan=False)) == out
    assert json.loads(calculate_json(json.dumps(req))) == out


@pytest.mark.parametrize("move", [{"type": "fire", "power": None, "damage_class": "status"},
                                  {"type": "fire", "power": None, "damage_class": "physical"}])
def test_a_move_without_base_power_is_refused(move, type_chart_df):
    attacker, defender, _, _ = CASES[0]
    with pytest.raises(ValueError, match="base power"):
        calculate(request(attacker, defender, move, type_chart_df))


@pytest.mark.parametrize("evs,ivs", [(_spread(atk=253), None), (_spread(hp=252, atk=252, spe=8), None),
                                     (None, {**{s: 31 for s in STATS}, "spe": 32})])
def test_out_of_range_evs_or_ivs_are_refused(evs, ivs, type_chart_df):
    attacker, defender, _, move = CASES[0]
    with pytest.raises(ValueError):
        calculate(request({**attacker, **({"evs": evs} if evs else {}), **({"ivs": ivs} if ivs else {})},
                          defender, move, type_chart_df))


_NO_PANDAS = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
sys.modules["pandas"] = None           # any `import pandas` now raises ImportError
from python.calculations.calc_facade import calculate_json
print(calculate_json(sys.stdin.read()))
print(json.dumps(sorted(m for m, mod in sys.modules.items() if mod is not None and m.split(".")[0] in {"pandas", "numpy", "pyarrow", "sqlalchemy", "pymysql"})))
"""


def test_facade_path_imports_neither_pandas_nor_the_database(type_chart_df):
    attacker, defender, _, move = CASES[0]
    proc = subprocess.run([sys.executable, "-c", _NO_PANDAS, str(REPO_ROOT)], capture_output=True, text=True, timeout=60,
                          input=json.dumps(request(attacker, defender, move, type_chart_df)))
    assert proc.returncode == 0, proc.stderr
    result, heavy = proc.stdout.strip().splitlines()[-2:]
    assert json.loads(heavy) == []
    assert json.loads(result)["max_damage"] > 0


def _engine_closure(module="python.calculations.calc_facade"):
    """Repo files the façade imports, transitively, plus their package __init__ files."""
    import ast
    seen, todo = set(), [module]
    while todo:
        mod = todo.pop()
        path = REPO_ROOT.joinpath(*mod.split(".")).with_suffix(".py")
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [node.module] if isinstance(node, ast.ImportFrom) and node.module else \
                [a.name for a in node.names] if isinstance(node, ast.Import) else []
            todo += [n for n in names if n.split(".")[0] == "python"]
    inits = {"/".join(p.split("/")[:i]) + "/__init__.py" for p in seen for i in range(1, p.count("/") + 1)}
    return seen | inits


def test_the_browser_bundles_exactly_the_modules_the_facade_imports():
    import re
    engine_ts = (REPO_ROOT / "web" / "src" / "engine.ts").read_text(encoding="utf-8")
    bundled = set(re.findall(r'^import \w+ from "\.\./\.\./(python/[\w/]+\.py)\?raw";', engine_ts, re.M))
    listed = set(re.findall(r'^  "(python/[\w/]+\.py)": \w+,', engine_ts, re.M))
    assert bundled == listed == _engine_closure()


# ---- Team summary (#19): speed tiers, roles, type weakness table, synergy score ----

def member(name, types, base, nature="hardy", evs=None, item="", ability="none"):
    return {**side(types, base, nature, evs=evs, ability=ability), "name": name, "item": item}


def summary_request(members, type_chart_df):
    return {"members": members, "type_chart": type_chart_df[["attack_type", "defense_type", "multiplier"]].values.tolist()}


def test_team_summary_speed_tiers_fastest_first_with_held_items(type_chart_df):
    from python.calculations.calc_facade import team_summary
    team = [member("slow", ["water"], [100] * 6),                                            # Spe 120
            member("scarf", ["fire"], [100] * 6, item="choice-scarf"),                        # 180
            member("timid", ["grass"], [100] * 6, nature="timid", evs=_spread(spe=252)),      # 167
            member("ball", ["ground"], [100] * 6, item="iron-ball")]                          # 60
    out = team_summary(summary_request(team, type_chart_df))
    assert out["speed_tiers"] == [{"index": 1, "name": "scarf", "speed": 180}, {"index": 2, "name": "timid", "speed": 167},
                                  {"index": 0, "name": "slow", "speed": 120}, {"index": 3, "name": "ball", "speed": 60}]
    # the Speed stat itself is the unmodified one; only the tier applies the item
    assert [m["stats"]["spe"] for m in out["members"]] == [120, 120, 167, 120]


def test_team_summary_speed_tiers_tell_apart_two_members_with_the_same_name(type_chart_df):
    from python.calculations.calc_facade import team_summary
    team = [member("twin", ["fire"], [100] * 6), member("twin", ["fire"], [100] * 6, item="choice-scarf")]
    tiers = team_summary(summary_request(team, type_chart_df))["speed_tiers"]
    assert [(t["index"], t["speed"]) for t in tiers] == [(1, 180), (0, 120)]


def test_team_summary_roles_use_level_50_stats(type_chart_df):
    from python.calculations.calc_facade import team_summary
    sweeper = member("sweeper", ["fire"], [80, 130, 80, 60, 80, 100], nature="adamant", evs=_spread(atk=252, spe=252))
    # level 50: Atk floor(182 * 1.1) = 200, Spe 152 -> physical sweeper
    wall = member("wall", ["water"], [100, 80, 130, 80, 100, 50])                     # Def 150 -> wall
    plain = member("plain", ["grass"], [100] * 6)                                    # all 120 -> balanced
    out = team_summary(summary_request([sweeper, wall, plain, plain], type_chart_df))
    assert [m["role"] for m in out["members"]] == ["physical_sweeper", "wall", "balanced", "balanced"]
    assert out["roles"] == {"physical_sweeper": 1, "wall": 1, "balanced": 2}


def test_team_summary_type_table_counts_weak_resist_immune_with_abilities(type_chart_df):
    from python.calculations.calc_facade import team_summary
    team = [member("fire", ["fire"], [100] * 6, ability="flash-fire"),
            member("bird", ["water", "flying"], [100] * 6),
            member("ghost", ["ghost"], [100] * 6)]
    out = team_summary(summary_request(team, type_chart_df))
    table = {r["type"]: (r["multipliers"], r["weak"], r["resist"], r["immune"]) for r in out["type_table"]}
    assert [r["type"] for r in out["type_table"]] == ["electric", "fairy", "fighting", "fire", "flying", "ghost",
                                                      "ground", "normal", "water"]   # every attacking type in the chart
    assert table == {
        "electric": ([1.0, 4.0, 1.0], 1, 0, 0),
        "fairy": ([0.5, 1.0, 1.0], 0, 1, 0),
        "fighting": ([1.0, 1.0, 0.0], 0, 0, 1),
        "fire": ([0.0, 0.5, 1.0], 0, 1, 1),          # Flash Fire: immune
        "flying": ([1.0, 1.0, 1.0], 0, 0, 0),
        "ghost": ([1.0, 1.0, 2.0], 1, 0, 0),
        "ground": ([2.0, 0.0, 1.0], 1, 0, 1),
        "normal": ([1.0, 1.0, 0.0], 0, 0, 1),
        "water": ([2.0, 1.0, 1.0], 1, 0, 0),
    }
    # synergy = (resisted + immune) - weak, summed over the table: (2 + 4) - 4
    assert out["synergy_score"] == 2


def test_team_summary_empty_team_and_json_entry_point(type_chart_df):
    from python.calculations.calc_facade import team_summary, team_summary_json
    req = summary_request([], type_chart_df)
    out = team_summary(req)
    assert out["members"] == [] and out["speed_tiers"] == [] and out["roles"] == {} and out["synergy_score"] == 0
    assert all(r["weak"] == r["resist"] == r["immune"] == 0 for r in out["type_table"])
    assert json.loads(team_summary_json(json.dumps(req))) == out


def test_team_summary_refuses_more_than_six_members(type_chart_df):
    from python.calculations.calc_facade import team_summary
    with pytest.raises(ValueError, match="at most 6"):
        team_summary(summary_request([member("x", ["fire"], [100] * 6)] * 7, type_chart_df))
