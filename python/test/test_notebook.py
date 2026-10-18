import json
import os
from pathlib import Path

import pandas as pd
import pytest

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "eda_exploration.ipynb"


def test_notebook_is_valid_and_its_code_cells_run_on_the_aggregate_tables(tmp_path, monkeypatch):
    import matplotlib
    matplotlib.use("Agg")
    from python.analytics import dim_tables, matchup_stats, partner_stats, pokemon_usage, tera_stats, usage_trend
    from python.test.test_partner_stats import TEAMS
    from python.test.test_pokemon_usage import _write
    from python.test.test_tera_stats import TERA

    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and any(c["cell_type"] == "code" for c in nb["cells"])
    assert all(c["outputs"] == [] for c in nb["cells"] if c["cell_type"] == "code")      # committed clean; run it to see results

    out, name_map = _write(tmp_path)
    pd.DataFrame(TERA, columns=["battle_id", "username", "species", "tera_type"]).to_parquet(out / "battle_tera.parquet")
    nm = pd.concat([name_map, pd.DataFrame([("Rillaboom", 812, "rillaboom", 812, "exact", "known")], columns=name_map.columns)], ignore_index=True)
    map_csv, agg = tmp_path / "map.csv", tmp_path / "agg"
    nm.to_csv(map_csv, index=False)
    common = ["--output-dir", str(out), "--map", str(map_csv), "--out", str(agg)]
    pokemon_usage.main(common)
    tera_stats.main(common + ["--usage", str(agg / "pokemon_usage_stats.parquet")])
    usage_trend.main(common)
    dim_tables.main(common)
    pd.DataFrame(TEAMS, columns=["battle_id", "player_side", "pokemon_name"]).to_parquet(out / "battle_team_slot.parquet")
    partner_stats.main(common + ["--min-support", "1"])
    matchup_stats.main(common + ["--min-support", "1"])

    monkeypatch.setenv("AGG_DIR", str(agg))
    namespace = {"display": print}
    for i, cell in enumerate(c for c in nb["cells"] if c["cell_type"] == "code"):
        exec(compile("".join(cell["source"]), f"notebook-cell-{i}", "exec"), namespace)
    assert namespace["REGULATION"] == "gen9vgc2024regg" and namespace["SPECIES"] == "Incineroar"