"""Damage-calc façade for the browser (ADR-014, #16): the only module the web app calls through Pyodide.

JSON in, JSON out. Builds level-50 stats from base stats + nature + EVs / IVs (stats_calc) and runs the existing
engine (damage_calc_v2) on a {(attack_type, defense_type): multiplier} type chart. Standard library and engine
modules only: no pandas, no database, no type_v2.

Request:
    {"attacker": side, "defender": side,
     "move": {"type": "fire", "power": 90, "damage_class": "physical" | "special"},
     "type_chart": [["fire", "grass", 2.0], ...]}          # pairs not listed are 1.0
    side = {"types": ["fire"], "ability": "blaze", "base_stats": {hp, atk, def, spatk, spdef, spe},
            "nature": {"increased": "atk" | None, "decreased": "spatk" | None},
            "evs": {hp..spe: 0-252, total <= 508}, "ivs": {hp..spe: 0-31}}
Response: both sides' level-50 stats, min / max damage, the same as % of the defender's HP, OHKO / 2HKO chance (% of
the 16 rolls), type modifier, STAB, category. Only the mechanics the engine models (see damage_calc_v2).
"""
import json

from python.calculations.damage_calc_v2 import calculate_damage
from python.calculations.stats_calc import calculate_final_stats

LEVEL = 50
STATS = ("hp", "atk", "def", "spatk", "spdef", "spe")
MAX_EV, MAX_EV_TOTAL, MAX_IV = 252, 508, 31


def nature_modifiers(nature):
    """{"increased": "atk", "decreased": "spatk"} -> {atk: 1.1, spatk: 0.9, others 1.0}; same stat or None -> neutral."""
    mods = {s: 1.0 for s in STATS[1:]}
    up, down = (nature or {}).get("increased"), (nature or {}).get("decreased")
    for stat in (up, down):
        if stat is not None and stat not in mods:
            raise ValueError(f"unknown nature stat {stat!r}")
    if up != down:
        if up is not None:
            mods[up] = 1.1
        if down is not None:
            mods[down] = 0.9
    return mods


def _spread(values, name, top):
    out = {s: int((values or {}).get(s, 0)) for s in STATS}
    if any(v < 0 or v > top for v in out.values()):
        raise ValueError(f"{name} must be between 0 and {top}: {out}")
    return out


def level_50_stats(side):
    evs = _spread(side.get("evs"), "EVs", MAX_EV)
    if sum(evs.values()) > MAX_EV_TOTAL:
        raise ValueError(f"EVs total {sum(evs.values())} > {MAX_EV_TOTAL}")
    ivs = _spread(side.get("ivs", {s: MAX_IV for s in STATS}), "IVs", MAX_IV)
    base = {s: int(side["base_stats"][s]) for s in STATS}
    return calculate_final_stats(base, ivs, evs, LEVEL, nature_modifiers(side.get("nature")))


def _battler(side, stats):
    return {"types": [str(t).lower() for t in side["types"] if t], "ability": side.get("ability") or "",
            "level": LEVEL, "stats": stats}


def calculate(request):
    move = request["move"]
    if move.get("power") is None or move.get("damage_class") not in ("physical", "special"):
        raise ValueError(f"move has no base power to calculate (damage class {move.get('damage_class')!r})")
    move = {"type": str(move["type"]).lower(), "power": float(move["power"]), "damage_class": move["damage_class"]}
    chart = {(str(a).lower(), str(d).lower()): float(m) for a, d, m in request["type_chart"]}
    a_stats, d_stats = level_50_stats(request["attacker"]), level_50_stats(request["defender"])
    r = calculate_damage(_battler(request["attacker"], a_stats), _battler(request["defender"], d_stats), move, chart)
    hp = d_stats["hp"]
    return {"attacker_stats": a_stats, "defender_stats": d_stats,
            "min_damage": r["min_damage"], "max_damage": r["max_damage"],
            "min_percent": round(100 * r["min_damage"] / hp, 1), "max_percent": round(100 * r["max_damage"] / hp, 1),
            "ohko_chance": r["ohko_chance"], "two_hko_chance": r["two_hko_chance"],
            "type_modifier": r["type_modifier"], "stab": r["stab"], "category": r["category"]}


def calculate_json(text):
    """String in, string out: what the web worker calls (no Python objects cross the JS boundary)."""
    return json.dumps(calculate(json.loads(text)), allow_nan=False)
