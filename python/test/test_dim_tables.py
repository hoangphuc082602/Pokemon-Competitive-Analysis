import pandas as pd

from python.analytics.dim_tables import build_dimensions, parse_regulation
from python.test.test_pokemon_usage import REG, _write


def test_regulation_ids_become_readable_labels():
    assert parse_regulation("gen9vgc2025regi") == ("Scarlet/Violet", 2025, "I", "Reg I 2025")
    assert parse_regulation("gen9championsvgc2026regm-a") == ("Champions", 2026, "M-A", "Champions Reg M-A 2026")
    assert parse_regulation("gen9doublesou")[3] == "gen9doublesou"


def test_dimensions_are_built_from_the_scope(tmp_path):
    out, name_map = _write(tmp_path)
    dims = build_dimensions(out, name_map)
    reg = dims["dim_regulation"].iloc[0]
    assert (reg["regulation"], reg["label"], reg["first_month"], reg["last_month"], reg["battles"]) == (REG, "Reg G 2024", "2024-01", "2024-02", 2)
    assert list(dims["dim_month"]["month"]) == ["2024-01", "2024-02"]
    assert list(dims["dim_month"]["label"]) == ["Jan 2024", "Feb 2024"]


def test_rating_bands_have_an_explicit_sort_order(tmp_path):
    out, name_map = _write(tmp_path)
    band = build_dimensions(out, name_map)["dim_rating_band"]
    assert list(band["rating_band"]) == ["all", "below_1200", "1200_1399", "1400_1499", "1500_plus", "unknown"]
    assert list(band["sort_order"]) == [1, 2, 3, 4, 5, 6]
    assert band.set_index("rating_band").loc["1400_1499", "rating_min"] == 1400


def test_species_dimension_flags_masked_families(tmp_path):
    out, name_map = _write(tmp_path)
    sp = build_dimensions(out, name_map)["dim_species"].set_index("species_id")
    assert sp.loc[892, "species"] == "Urshifu" and bool(sp.loc[892, "has_masked_form"])
    assert not bool(sp.loc[727, "has_masked_form"])


def test_regulations_are_ordered_by_busiest_month_not_by_first_upload(tmp_path):
    out, name_map = _write(tmp_path)
    battle, players = pd.read_parquet(out / "battle.parquet"), pd.read_parquet(out / "battle_players.parquet")
    dec, jan = 1701432000, 1704110400                                    # 2023-12-01 / 2024-01-01 12:00 UTC
    rows = [("f0", "gen9vgc2024regf", dec), ("f1", "gen9vgc2024regf", jan), ("f2", "gen9vgc2024regf", jan),   # F: first Dec, busiest Jan
            ("d0", "gen9vgc2023regd", jan)]                                                                      # D: only late uploads in Jan
    extra = pd.DataFrame({"battle_id": [r[0] for r in rows], "format_id": [r[1] for r in rows], "turn_count": 5, "upload_time": [r[2] for r in rows]})
    pl = [(b, side, res, 1300.0, f"{b}{side}") for b, _, _ in rows for side, res in (("p1", "WIN"), ("p2", "LOSS"))]
    pd.concat([battle, extra], ignore_index=True).to_parquet(out / "battle.parquet")
    pd.concat([players, pd.DataFrame(pl, columns=players.columns)], ignore_index=True).to_parquet(out / "battle_players.parquet")
    reg = build_dimensions(out, name_map)["dim_regulation"]
    assert reg.loc[reg["regulation"] == "gen9vgc2024regf", "first_month"].iloc[0] == "2023-12"   # F did start earlier ...
    assert list(reg["regulation"])[:2] == ["gen9vgc2023regd", "gen9vgc2024regf"]                  # ... but D is the older regulation