import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from sqlalchemy import create_engine, text

from python.database.to_sql import (
    LoadError,
    TABLES,
    check_target,
    import_parquet,
    main,
    plan_imports,
)


@pytest.fixture
def engine(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with e.begin() as conn:
        conn.execute(text("CREATE TABLE battle_leads (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "battle_id TEXT, username TEXT, pokemon_name TEXT, lead_slot INTEGER)"))
        conn.execute(text("CREATE TABLE battle_field_state (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "battle_id TEXT, turn_no INTEGER, p1_left TEXT, p1_right TEXT, p2_left TEXT, p2_right TEXT)"))
    return e


def write_parquet(path, df, row_group_size=2):
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, row_group_size=row_group_size)


@pytest.fixture
def leads_df():
    return pd.DataFrame({
        "battle_id": ["b1", "b1", "b2", "b2", "b3"],
        "username": ["a", "b", "a", "b", "a"],
        "pokemon_name": ["Flutter Mane", "Incineroar", "Urshifu-*", "Rillaboom", "Kingambit"],
        "lead_slot": [1, 2, 1, 2, 1],
    })


def count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()


# ---------- mapping / plan ----------
def test_field_state_is_in_the_table_mapping():
    # Regression: this table was never loaded because it was missing from the mapping.
    assert TABLES["battle_field_state.parquet"] == "battle_field_state"


def test_every_runner_table_has_a_loader_entry():
    from parser.runner import TABLE_COLUMNS  # the tables the parser actually writes

    assert {f"{t}.parquet" for t in TABLE_COLUMNS} == set(TABLES)


def test_plan_reports_found_and_missing(tmp_path, leads_df):
    write_parquet(tmp_path / "battle_leads.parquet", leads_df)
    found, missing = plan_imports(tmp_path, only=["battle_leads", "battle_field_state"])
    assert [(p.name, t) for p, t in found] == [("battle_leads.parquet", "battle_leads")]
    assert missing == ["battle_field_state.parquet"]


def test_plan_rejects_unknown_table(tmp_path):
    with pytest.raises(LoadError, match="Unknown table"):
        plan_imports(tmp_path, only=["nope"])


# ---------- pre-flight checks ----------
def test_missing_target_table_is_refused(tmp_path, engine, leads_df):
    write_parquet(tmp_path / "x.parquet", leads_df)
    with pytest.raises(LoadError, match="does not exist"):
        check_target(engine, tmp_path / "x.parquet", "not_a_table")


def test_unknown_parquet_column_is_refused(tmp_path, engine, leads_df):
    write_parquet(tmp_path / "x.parquet", leads_df.assign(surprise=1))
    with pytest.raises(LoadError, match=r"\['surprise'\]"):
        check_target(engine, tmp_path / "x.parquet", "battle_leads")


def test_table_may_have_extra_columns_such_as_autoincrement_id(tmp_path, engine, leads_df):
    write_parquet(tmp_path / "x.parquet", leads_df)           # parquet has no `id`
    assert check_target(engine, tmp_path / "x.parquet", "battle_leads") == 0


# ---------- loading ----------
def test_import_loads_all_rows_across_row_groups(tmp_path, engine, leads_df):
    path = tmp_path / "battle_leads.parquet"
    write_parquet(path, leads_df, row_group_size=2)            # 3 row groups
    assert pq.ParquetFile(path).num_row_groups == 3
    assert import_parquet(path, "battle_leads", engine, batch_size=2) == 5
    assert count(engine, "battle_leads") == 5
    with engine.connect() as conn:
        names = {r[0] for r in conn.execute(text("SELECT pokemon_name FROM battle_leads"))}
    assert names == set(leads_df.pokemon_name)


def test_second_load_is_refused_instead_of_duplicating(tmp_path, engine, leads_df):
    path = tmp_path / "battle_leads.parquet"
    write_parquet(path, leads_df)
    import_parquet(path, "battle_leads", engine)
    with pytest.raises(LoadError, match="already has 5 rows"):
        check_target(engine, path, "battle_leads")
    assert check_target(engine, path, "battle_leads", allow_non_empty=True) == 5


# ---------- CLI ----------
def run(tmp_path, engine, *extra):
    return main(["--output-dir", str(tmp_path), *extra], engine=engine)


def test_dry_run_writes_nothing(tmp_path, engine, leads_df, capsys):
    write_parquet(tmp_path / "battle_leads.parquet", leads_df)
    assert run(tmp_path, engine, "--dry-run") == 0
    assert count(engine, "battle_leads") == 0
    assert "Dry run" in capsys.readouterr().out


def test_cli_loads_then_refuses_then_truncate_reloads(tmp_path, engine, leads_df, capsys):
    write_parquet(tmp_path / "battle_leads.parquet", leads_df)
    assert run(tmp_path, engine) == 0 and count(engine, "battle_leads") == 5
    assert run(tmp_path, engine) == 1 and count(engine, "battle_leads") == 5       # refused, nothing duplicated
    assert "already has 5 rows" in capsys.readouterr().err
    assert run(tmp_path, engine, "--truncate") == 0 and count(engine, "battle_leads") == 5


def test_cli_loads_field_state_table(tmp_path, engine):
    df = pd.DataFrame({"battle_id": ["b1"] * 3, "turn_no": [1, 2, 3], "p1_left": ["A"] * 3,
                       "p1_right": ["B"] * 3, "p2_left": ["C"] * 3, "p2_right": ["D"] * 3})
    write_parquet(tmp_path / "battle_field_state.parquet", df)
    assert run(tmp_path, engine, "--tables", "battle_field_state") == 0
    assert count(engine, "battle_field_state") == 3


def test_one_bad_table_stops_before_any_write(tmp_path, engine, leads_df):
    write_parquet(tmp_path / "battle_leads.parquet", leads_df)                      # fine
    write_parquet(tmp_path / "battle_field_state.parquet", leads_df.assign(surprise=1))  # bad columns
    assert run(tmp_path, engine) == 1
    assert count(engine, "battle_leads") == 0        # checks run for ALL tables before the first insert


def test_no_parquet_files_is_an_error(tmp_path, engine):
    assert run(tmp_path, engine) == 1


# ---------- the refusal message tells you what state the table is in ----------
@pytest.mark.parametrize(
    "table_rows, expected",
    [(5, "looks already loaded"), (3, "INCOMPLETE (2 missing)"), (8, "3 extra rows")],
)
def test_refusal_message_compares_with_parquet(tmp_path, engine, leads_df, table_rows, expected):
    path = tmp_path / "battle_leads.parquet"
    write_parquet(path, leads_df)                                  # 5 rows
    with engine.begin() as conn:
        for i in range(table_rows):
            conn.execute(text("INSERT INTO battle_leads (battle_id) VALUES (:b)"), {"b": f"x{i}"})
    with pytest.raises(LoadError, match=expected.replace("(", r"\(").replace(")", r"\)")):
        check_target(engine, path, "battle_leads")