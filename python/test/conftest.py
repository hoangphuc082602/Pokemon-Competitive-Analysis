"""Fixtures dùng chung cho test tính toán. Không cần MySQL."""
import pandas as pd
import pytest

# Script kiểu cũ (print, kết nối MySQL ngay khi import). KHÔNG xóa, chỉ tạm bỏ khỏi pytest
# cho đến khi viết lại (sprint task #3b) hoặc xóa có kiểm chứng (task #6).
collect_ignore = [
    "main_test.py",
    "test_calc.py",
    "test_team_analyzer.py",
    "test_atk_balance.py",
    "test_role_label.py",
    "test_team_builder.py",
]


@pytest.fixture
def type_chart_df():
    """Type chart tối thiểu, đủ cho các case trong test (cột giống bảng type_effectiveness)."""
    rows = [
        # attack_type, defense_type, multiplier
        ("fire", "grass", 2.0),
        ("fire", "water", 0.5),
        ("fire", "fire", 0.5),
        ("water", "fire", 2.0),
        ("electric", "water", 2.0),
        ("electric", "flying", 2.0),
        ("electric", "ground", 0.0),
        ("ground", "flying", 0.0),
        ("ground", "fire", 2.0),
        ("ground", "electric", 2.0),
        ("normal", "ghost", 0.0),
        ("fighting", "ghost", 0.0),
        ("fairy", "dragon", 2.0),
        ("fairy", "fire", 0.5),
        ("ghost", "ghost", 2.0),
        ("flying", "grass", 2.0),
    ]
    return pd.DataFrame(rows, columns=["attack_type", "defense_type", "multiplier"])


@pytest.fixture
def nature_df():
    """Mã stat theo PokéAPI: 2=atk 3=def 4=spatk 5=spdef 6=spe."""
    return pd.DataFrame(
        [
            ("timid", 6, 2),
            ("adamant", 2, 4),
            ("bold", 3, 2),
            ("hardy", None, None),  # nature trung tính
        ],
        columns=["nature_name", "increased_stat", "decreased_stat"],
    )


@pytest.fixture
def pokemon_df():
    return pd.DataFrame(
        [
            ("incineroar", "fire", "dark"),
            ("flutter-mane", "ghost", "fairy"),
            ("garchomp", "dragon", "ground"),
            ("pelipper", "water", "flying"),
            ("rotom-wash", "electric", "water"),
            ("ditto", "normal", None),
        ],
        columns=["pokemon", "type_1", "type_2"],
    )


def make_battler(types, ability="none", level=50, **stats):
    """Dict battler tối thiểu theo cấu trúc mà calculation engine đang dùng."""
    base = {"hp": 150, "atk": 100, "def": 100, "spatk": 100, "spdef": 100, "spe": 100}
    base.update(stats)
    return {"types": types, "ability": ability, "level": level, "stats": base}


@pytest.fixture
def battler():
    return make_battler