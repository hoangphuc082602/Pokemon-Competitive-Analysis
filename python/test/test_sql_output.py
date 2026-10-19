import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect

from python.analytics.sql_output import write_table


@pytest.fixture
def engine():
    return create_engine("sqlite://")


def test_table_is_written_with_the_requested_indexes(engine):
    df = pd.DataFrame({"regulation": ["gen9vgc2024regg"], "rating_band": ["all"], "species_id": [892], "appearances": [3]})
    write_table(df, "pokemon_usage_stats", engine, [["regulation", "rating_band", "species_id"], ["species_id"]])
    insp = inspect(engine)
    assert pd.read_sql("SELECT * FROM pokemon_usage_stats", engine).iloc[0]["appearances"] == 3
    assert sorted(tuple(i["column_names"]) for i in insp.get_indexes("pokemon_usage_stats")) == [
        ("regulation", "rating_band", "species_id"), ("species_id",)]


def test_rewriting_a_table_recreates_its_indexes(engine):
    df = pd.DataFrame({"regulation": ["a"], "species_id": [1]})
    for _ in range(2):                                   # if_exists='replace' drops the table and its indexes
        write_table(df, "t", engine, [["species_id"]])
    assert len(inspect(engine).get_indexes("t")) == 1


def test_unknown_index_column_is_an_error(engine):
    with pytest.raises(ValueError, match="missing"):
        write_table(pd.DataFrame({"a": [1]}), "t", engine, [["nope"]])