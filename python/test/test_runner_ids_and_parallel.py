import pandas as pd
import pytest

from parser.runner import run
from python.test.test_parser_species import LOG

# Same two players and teams in a Bo3: the first 500 characters are identical, so a hash of them collides.
GAME_2 = LOG.replace("|win|alice", "|win|bob")
OTHER = LOG.replace("alice", "carol")


@pytest.fixture
def source_dir(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    pd.DataFrame({
        "id": ["gen9vgc2024regg-1", "gen9vgc2024regg-2", "gen9vgc2024regg-3"],
        "log": [LOG, GAME_2, OTHER],
    }).to_parquet(d / "Gen 9 VGC 2024_part1.parquet")
    return d


def _battle_ids(out_dir):
    return set(pd.read_parquet(out_dir / "battle.parquet")["battle_id"])


def test_log_hash_ids_drop_rematches_with_identical_heads(source_dir, tmp_path):
    stats = run(source_dir, tmp_path / "out", None, 100, 0, False)
    assert stats.parsed_ok == 2 and stats.skipped_duplicate == 1


def test_replay_id_keeps_every_game(source_dir, tmp_path):
    stats = run(source_dir, tmp_path / "out", None, 100, 0, False, id_col="id")
    assert stats.parsed_ok == 3 and stats.skipped_duplicate == 0
    assert _battle_ids(tmp_path / "out") == {"gen9vgc2024regg-1", "gen9vgc2024regg-2", "gen9vgc2024regg-3"}


def test_parallel_and_serial_write_the_same_battles(source_dir, tmp_path):
    run(source_dir, tmp_path / "serial", None, 100, 0, False, id_col="id")
    run(source_dir, tmp_path / "parallel", None, 100, 2, False, id_col="id")
    assert _battle_ids(tmp_path / "serial") == _battle_ids(tmp_path / "parallel")
    for table in ("battle_switch", "battle_leads"):
        a = pd.read_parquet(tmp_path / "serial" / f"{table}.parquet").sort_values(["battle_id", "username", "pokemon_name"])
        b = pd.read_parquet(tmp_path / "parallel" / f"{table}.parquet").sort_values(["battle_id", "username", "pokemon_name"])
        assert len(a) == len(b) and a["species"].tolist() == b["species"].tolist()


def test_limit_rows_only_parses_the_first_logs(source_dir, tmp_path):
    stats = run(source_dir, tmp_path / "out", None, 100, 0, False, limit_rows=2, id_col="id")
    assert stats.parsed_ok == 2


def test_missing_id_column_is_reported_not_crashing(source_dir, tmp_path):
    stats = run(source_dir, tmp_path / "out", None, 100, 0, False, id_col="nope")
    assert stats.parsed_ok == 0 and stats.parse_errors == 1


def test_source_metadata_fills_battle_fields_the_log_does_not_have(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    pd.DataFrame({
        "id": ["gen9vgc2024regg-1"], "log": [LOG], "uploadtime": [1700000000],
        "rating": [1612.0], "formatid": ["gen9vgc2024regg"], "format": ["ignored: the log already has it"],
    }).to_parquet(d / "Gen 9 VGC 2024_part1.parquet")
    run(d, tmp_path / "out", None, 100, 0, False, id_col="id")
    row = pd.read_parquet(tmp_path / "out" / "battle.parquet").iloc[0]
    assert row["upload_time"] == 1700000000
    assert row["rating"] is not pd.NA and row["rating"] > 0
    assert row["format"] != "ignored: the log already has it"


# ---------- per-file parts, resume, streaming ----------
import parser.runner as runner_module  # noqa: E402


@pytest.fixture
def two_files(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    pd.DataFrame({"id": ["gen9vgc2024regg-1", "gen9vgc2024regg-2"], "log": [LOG, GAME_2]}).to_parquet(d / "Gen 9 VGC 2024_part1.parquet")
    pd.DataFrame({"id": ["gen9vgc2024regg-3", "gen9vgc2024regg-4"], "log": [OTHER, OTHER.replace("bob", "dave")]}).to_parquet(d / "Gen 9 VGC 2024_part2.parquet")
    return d


def test_small_chunks_give_the_same_output(two_files, tmp_path):
    run(two_files, tmp_path / "big", None, 100, 0, False, id_col="id")
    run(two_files, tmp_path / "small", None, 100, 0, False, id_col="id", chunk_rows=1)
    for table in ("battle", "battle_switch", "battle_leads", "battle_team_slot"):
        a = pd.read_parquet(tmp_path / "big" / f"{table}.parquet")
        b = pd.read_parquet(tmp_path / "small" / f"{table}.parquet")
        assert len(a) == len(b), table
    assert _battle_ids(tmp_path / "small") == _battle_ids(tmp_path / "big")


def test_every_source_file_gets_a_finished_part_and_a_merged_table(two_files, tmp_path):
    run(two_files, tmp_path / "out", None, 100, 0, False, id_col="id")
    parts = tmp_path / "out" / "parts"
    assert (parts / "Gen 9 VGC 2024_part1" / "_DONE").exists() and (parts / "Gen 9 VGC 2024_part2" / "_DONE").exists()
    assert len(_battle_ids(tmp_path / "out")) == 4
    assert len(pd.read_parquet(tmp_path / "out" / "battle.parquet")) == 4


def test_a_crash_keeps_finished_files_and_resume_completes_the_run(two_files, tmp_path, monkeypatch):
    real = runner_module._process_file

    def crash_on_second_file(pq_path, *a, **k):
        if "part2" in pq_path.name:
            raise RuntimeError("boom")
        return real(pq_path, *a, **k)

    monkeypatch.setattr(runner_module, "_process_file", crash_on_second_file)
    with pytest.raises(RuntimeError):
        run(two_files, tmp_path / "out", None, 100, 0, False, id_col="id")
    parts = tmp_path / "out" / "parts"
    assert (parts / "Gen 9 VGC 2024_part1" / "_DONE").exists()
    assert not (parts / "Gen 9 VGC 2024_part2" / "_DONE").exists()

    monkeypatch.setattr(runner_module, "_process_file", real)
    stats = run(two_files, tmp_path / "out", None, 100, 0, False, id_col="id", resume=True)
    assert stats.parsed_ok == 4
    assert len(_battle_ids(tmp_path / "out")) == 4


def test_resume_keeps_cross_file_deduplication(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    pd.DataFrame({"id": ["x-1"], "log": [LOG]}).to_parquet(d / "Gen 9 VGC 2024_part1.parquet")
    pd.DataFrame({"id": ["x-1", "x-2"], "log": [LOG, OTHER]}).to_parquet(d / "Gen 9 VGC 2024_part2.parquet")   # x-1 repeated
    run(d, tmp_path / "out", None, 100, 0, False, id_col="id")
    (tmp_path / "out" / "parts" / "Gen 9 VGC 2024_part2" / "_DONE").unlink()
    stats = run(d, tmp_path / "out", None, 100, 0, False, id_col="id", resume=True)
    assert stats.skipped_duplicate == 1
    assert sorted(_battle_ids(tmp_path / "out")) == ["x-1", "x-2"]


def test_existing_parts_are_not_reused_without_resume(two_files, tmp_path):
    run(two_files, tmp_path / "out", None, 100, 0, False, id_col="id")
    with pytest.raises(SystemExit):
        run(two_files, tmp_path / "out", None, 100, 0, False, id_col="id")


def test_leftovers_of_an_interrupted_file_are_discarded_on_resume(two_files, tmp_path):
    run(two_files, tmp_path / "out", None, 100, 0, False, id_col="id")
    part2 = tmp_path / "out" / "parts" / "Gen 9 VGC 2024_part2"
    (part2 / "_DONE").unlink()
    (part2 / "junk.txt").write_text("partial", encoding="utf-8")
    run(two_files, tmp_path / "out", None, 100, 0, False, id_col="id", resume=True)
    assert not (part2 / "junk.txt").exists() and (part2 / "_DONE").exists()
    assert len(_battle_ids(tmp_path / "out")) == 4