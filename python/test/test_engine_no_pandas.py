"""ADR-014: the damage-calc engine must run without pandas (Pyodide path).

conftest.py imports pandas into this process, so the check runs in a fresh
subprocess where `import pandas` is blocked before the engine is imported.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT = r"""
import json
import random
import sys

sys.path.insert(0, sys.argv[1])
sys.modules["pandas"] = None  # any `import pandas` now raises ImportError

from python.calculations.damage_calc_v2 import calculate_damage

random.uniform = lambda a, b: 1.0  # fixed max roll

def battler(types, **stats):
    base = {"hp": 150, "atk": 100, "def": 100, "spatk": 100, "spdef": 100, "spe": 100}
    base.update(stats)
    return {"types": types, "ability": "none", "level": 50, "stats": base}

type_chart = {("fire", "grass"): 2.0, ("fire", "water"): 0.5}
move = {"type": "fire", "power": 80, "damage_class": "physical"}
result = calculate_damage(battler(["fire"]), battler(["grass"], hp=100), move, type_chart)
print(json.dumps(result))
"""


def test_damage_calc_runs_without_pandas_on_mapping_type_chart():
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"engine needs pandas or failed:\n{proc.stderr}"

    result = json.loads(proc.stdout.strip().splitlines()[-1])
    # Same known values as test_dmg_v2.py::test_stab_super_effective_known_values:
    # base 37.2 * STAB 1.5 * type 2.0 = 111.6
    assert result["damage"] == 111
    assert result["max_damage"] == 111
    assert result["min_damage"] == 94
    assert result["damage_percent"] == 111.0
    assert result["stab"] == 1.5
    assert result["type_modifier"] == 2.0
    assert result["ohko_chance"] == 62.5
    assert result["two_hko_chance"] == 100.0
    assert result["category"] == "physical"
