"""Word2Vec baseline (#48): training is a function, nothing runs on import. No MySQL."""
import importlib
import sys

import pytest

from python.recommendation.word2vec_baseline import train_word2vec

TEAMS = [
    ["Incineroar", "Rillaboom", "Flutter Mane", "Urshifu", "Amoonguss", "Landorus"],
    ["Incineroar", "Flutter Mane", "Chien-Pao", "Dragonite", "Amoonguss", "Gholdengo"],
    ["Rillaboom", "Urshifu", "Landorus", "Gholdengo", "Chien-Pao", "Dragonite"],
] * 5


def test_train_returns_vectors_for_seen_species():
    model = train_word2vec(TEAMS, min_count=1, vector_size=8, workers=1)

    assert set(model.wv.index_to_key) == {p for team in TEAMS for p in team}
    assert model.wv["Incineroar"].shape == (8,)


def test_min_count_drops_rare_species():
    teams = TEAMS + [["Ditto"]]
    model = train_word2vec(teams, min_count=2, vector_size=8, workers=1)

    assert "Ditto" not in model.wv
    assert "Incineroar" in model.wv


def test_defaults_are_the_current_baseline():
    model = train_word2vec(TEAMS * 10, min_count=1)

    assert (model.vector_size, model.sg, model.window, model.epochs) == (128, 1, 6, 10)


def test_one_shot_iterator_is_refused():
    # Vocabulary and training each need a full pass over the corpus.
    with pytest.raises(TypeError):
        train_word2vec(iter(TEAMS), min_count=1)


def test_importing_the_cli_reads_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no data/ here: any read or training would fail
    sys.modules.pop("src.train_word2vec", None)

    importlib.import_module("src.train_word2vec")

    assert list(tmp_path.iterdir()) == []


def test_cli_trains_and_saves_the_model(tmp_path, monkeypatch):
    import pandas as pd
    from gensim.models import Word2Vec

    monkeypatch.chdir(tmp_path)  # a run-on-import regression must not touch the real data/
    import src.train_word2vec as cli

    rows = [
        {"battle_id": b, "player_side": "p1", "slot_no": s, "pokemon_name": name}
        for b, team in enumerate(TEAMS)
        for s, name in enumerate(team, start=1)
    ]
    parquet = tmp_path / "battle_team_slot.parquet"
    pd.DataFrame(rows).to_parquet(parquet)
    out = tmp_path / "models" / "pokemon_embedding.model"
    out.parent.mkdir()
    # Tiny corpus: lower min_count, keep every other default.
    real = cli.train_word2vec
    monkeypatch.setattr(cli, "train_word2vec", lambda teams: real(teams, min_count=1, workers=1))

    cli.main(parquet_path=str(parquet), model_path=str(out))

    assert "Flutter Mane" in Word2Vec.load(str(out)).wv
