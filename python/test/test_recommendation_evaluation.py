"""Evaluator of the v2.0 recommender (#51): leave-one-out Hit@10 / MRR, temporal split, team dedup."""
import pandas as pd
import pytest

from python.recommendation.evaluation import evaluate, leave_one_out, main, metrics, report

REG = "gen9vgc2024regg"
A, A2, B, C = (1, 1), (1, 99), (2, 2), (3, None)          # A2: another form of A's species; C: form unknown
FILLERS = [(100 + i, 100 + i) for i in range(10)]


def _stub(ranking):
    calls = []

    def scorer(team, regulation, band):
        calls.append((tuple(team), regulation, band))
        return ranking
    scorer.calls = calls
    return scorer


def _teams(*members, band="1500_plus"):
    return pd.DataFrame({"regulation": REG, "rating_band": band, "members": list(members)})


def test_hand_computed_hit_at_10_and_mrr_with_team_members_excluded():
    scorer = _stub([A, A2] + FILLERS + [B])               # C is never ranked
    ranks = leave_one_out(_teams((A, B, C)), scorer)
    # hide A: context {B, C} -> A first. hide B: context {A, C} -> A and A2 excluded (species clause), B 11th.
    # hide C: not ranked -> a miss with reciprocal rank 0.
    got = ranks[ranks["rating_band"] == "1500_plus"].set_index("hidden_species_id")["rank"].to_dict()
    assert got[1] == 1 and got[2] == 11 and pd.isna(got[3])               # one member per species on a team
    m = metrics(ranks, min_test=1).set_index("rating_band")
    for band in ("all", "1500_plus"):                     # every team is scored in 'all' and in its own band
        row = m.loc[band]
        assert (row["test_teams"], row["queries"]) == (1, 3)
        assert row["hit_at_10"] == pytest.approx(1 / 3)
        assert row["mrr"] == pytest.approx((1 + 1 / 11 + 0) / 3)
    assert {c[2] for c in scorer.calls} == {"all", "1500_plus"} and len(scorer.calls) == 6
    assert all(len(team) == 2 for team, _, _ in scorer.calls)          # the hidden member is never shown


def test_cells_below_the_minimum_test_size_are_listed_as_skipped_with_their_size():
    ranks = leave_one_out(_teams((A, B), (A, C), (B, C)).assign(rating_band=["1500_plus", "1500_plus", "unknown"]),
                          _stub([A, B, C]))
    m = metrics(ranks, min_test=2)
    assert m.set_index("rating_band")["test_teams"].to_dict() == {"all": 3, "1500_plus": 2, "unknown": 1}
    assert m.set_index("rating_band")["skipped"].to_dict() == {"all": False, "1500_plus": False, "unknown": True}
    assert m.set_index("rating_band")["hit_at_10"].isna().to_dict() == {"all": False, "1500_plus": False, "unknown": True}


# --- End to end on synthetic Parquet (same tables and columns as test_pokemon_usage.py::_write) --------------
WEEK0 = 1704067200                                        # Monday 2024-01-01 00:00 UTC
S = {f"S{i}": (i, i) for i in range(1, 10)}               # S1..S9: one listed form each, poke_id = species_id
BATTLES = [  # week, (p1 user, team), (p2 user, team): one battle a week, every player rated 1500
    (0, ("alice", "S1 S2 S3"), ("bob", "S1 S4 S5")),
    (1, ("bob", "S1 S4 S5"), ("erin", "S2 S4 S6")),
    (2, ("Carol", "S1 S2 S6"), ("erin", "S2 S4 S6")),
    (3, ("alice", "S1 S2 S3"), ("bob", "S1 S4 S5")),
    (4, ("alice", "S1 S2 S3"), ("bob", "S1 S4 S5")),
    (5, ("alice", "S1 S2 S3"), ("bob", "S1 S4 S5")),     # weeks 0-5 -> train (60% of the battles)
    (6, ("erin", "S2 S4 S6"), ("frank", "S3 S5 S6")),
    (7, ("erin", "S2 S4 S6"), ("frank", "S3 S5 S6")),    # weeks 6-7 -> validation
    (8, ("alice", "S1 S2 S4"), ("dave", "S9 S5 S6")),    # weeks 8-9 -> test; S9 is only ever seen in test
    (9, ("alice", "S4 S2 S1"), ("carol", "S6 S1 S2")),   # alice: same team as week 8; carol: same as week 2 (train)
]


def _write_weeks(tmp_path, extra_slots=()):
    out = tmp_path / "out"
    out.mkdir()
    ids = [f"w{w}" for w, _, _ in BATTLES]
    pd.DataFrame({"battle_id": ids, "format_id": REG, "turn_count": 5,
                  "upload_time": [WEEK0 + w * 604800 + 3600 for w, _, _ in BATTLES]}).to_parquet(out / "battle.parquet")
    players, slots = [], []
    for bid, (_, p1, p2) in zip(ids, BATTLES):
        for side, (user, team), result in (("p1", p1, "WIN"), ("p2", p2, "LOSS")):
            players.append((bid, side, result, 1500.0, user))
            slots += [(bid, side, name, name, "listed", 1, 0) for name in team.split()]
    pd.DataFrame(players, columns=["battle_id", "side", "result", "rating_before", "username"]).to_parquet(out / "battle_players.parquet")
    slots += list(extra_slots)
    pd.DataFrame(slots, columns=["battle_id", "player_side", "pokemon_name", "species_observed", "form_status",
                                 "was_sent_out", "is_lead"]).to_parquet(out / "battle_team_slot.parquet", row_group_size=4)
    name_map = pd.DataFrame([(n, p, n.lower(), s, "exact", "known") for n, (s, p) in S.items()],
                            columns=["showdown_name", "poke_id", "pokemon", "species_id", "method", "form_status"])
    return out, name_map


def _evaluate(tmp_path, **kw):
    out, name_map = _write_weeks(tmp_path)
    return evaluate(out, name_map, train_frac=0.6, test_frac=0.2, min_test=1, **kw)


def test_popularity_report_matches_hand_computed_hit_at_10_and_mrr(tmp_path):
    res = _evaluate(tmp_path)
    m = res.metrics.set_index("rating_band")
    assert list(m.index) == ["1500_plus", "all"] and set(m["regulation"]) == {REG}
    # Train popularity (weeks 0-5): S1 10, S2 7, S4 7 (tie -> lower species_id first), S5 5, S3 4, S6 3.
    # alice S1 S2 S4: every hidden member ranks 1st. dave S9 S5 S6: S9 unranked, S5 4th, S6 5th.
    for band in ("all", "1500_plus"):
        row = m.loc[band]
        assert (row["test_teams"], row["queries"], row["train_player_battles"]) == (2, 6, 12)
        assert row["hit_at_10"] == pytest.approx(5 / 6)
        assert row["mrr"] == pytest.approx((3 + 1 / 4 + 1 / 5) / 6)


def test_no_test_week_battle_reaches_the_train_component(tmp_path):
    res = _evaluate(tmp_path)
    alls = res.component[res.component["rating_band"] == "all"]
    assert set(alls["player_battles"]) == {12}                                   # 6 train battles x 2 sides
    assert 9 not in set(res.component["species_id"])                             # S9 is only in test weeks
    split = res.teams.groupby("split")["battle_id"].agg(set).to_dict()
    assert split["test"] == {"w8"} and split["validation"] == {"w6"}           # erin: team first seen in week 1
    assert split["train"] <= {f"w{w}" for w in range(6)}


def test_identical_teams_of_one_player_count_once_and_the_earliest_copy_is_kept(tmp_path):
    teams = _evaluate(tmp_path).teams
    test = teams[teams["split"] == "test"]
    assert sorted(test["player"]) == ["alice", "dave"]        # alice week 9 = week 8; carol week 9 = week 2 (train)
    carol = teams[teams["player"] == "carol"]
    assert list(carol["battle_id"]) == ["w2"]                  # 'Carol' and 'carol' are one Showdown user
    assert not teams.duplicated(["regulation", "player", "team_key"]).any()


def test_cli_writes_the_report_and_resumes_from_its_work_dir(tmp_path, capsys):
    out, name_map = _write_weeks(tmp_path)
    name_map.to_csv(tmp_path / "map.csv", index=False)
    args = ["--output-dir", str(out), "--map", str(tmp_path / "map.csv"), "--work", str(tmp_path / "work"),
            "--train-frac", "0.6", "--test-frac", "0.2", "--min-test", "1"]
    assert main(args) == 0
    report = pd.read_csv(tmp_path / "work" / "evaluation_popularity.csv")
    assert report.set_index("rating_band").loc["all", "test_teams"] == 2
    assert report.set_index("rating_band").loc["all", "mrr"] == pytest.approx((3 + 1 / 4 + 1 / 5) / 6)
    assert "Hit@10" in (tmp_path / "work" / "evaluation_popularity.md").read_text(encoding="utf-8")
    capsys.readouterr()
    assert main(args) == 0                                                      # second run: every step cached
    printed = capsys.readouterr().out
    assert printed.count("reusing") == 3
    assert "test teams with 6 mapped members: 0.0%" in printed                 # the fixture teams have 3
    with pytest.raises(SystemExit, match="--fresh"):                            # other split, same work dir
        main(args[:-4] + ["--test-frac", "0.3"])
    name_map.to_csv(tmp_path / "map2.csv", index=False)
    with pytest.raises(SystemExit, match="--fresh"):                            # other mapping, same work dir
        main([a if a != str(tmp_path / "map.csv") else str(tmp_path / "map2.csv") for a in args])
    assert main(args[:-4] + ["--test-frac", "0.3", "--fresh"]) == 0


def test_a_regulation_without_test_teams_is_listed_as_skipped_with_size_0():
    ranks = leave_one_out(_teams((A, B)), _stub([A, B]))
    component = pd.DataFrame({"regulation": [REG, "gen9vgc2025regh"], "rating_band": "all", "player_battles": [500, 40]})
    m = report(ranks, component, min_test=1).set_index(["regulation", "rating_band"])
    other = m.loc[("gen9vgc2025regh", "all")]
    assert (other["test_teams"], other["skipped"], other["train_player_battles"]) == (0, True, 40)
    assert m.loc[(REG, "all"), "train_player_battles"] == 500 and not m.loc[(REG, "all"), "skipped"]


def test_a_hidden_member_of_unknown_form_is_hit_by_its_species():
    # Urshifu masked and never sent out: (3, None) is found by the first candidate of species 3, whatever form.
    ranks = leave_one_out(_teams((A, C)), _stub([B, (3, 7), (3, None), A]))
    got = ranks[ranks["rating_band"] == "all"].set_index("hidden_species_id")["rank"].to_dict()
    assert got[3] == 2                                     # (3, 7) counts as the hit; (3, None) is never reached
    assert got[1] == 2                                     # hiding A: both species-3 candidates are on the team


def test_teams_that_differ_only_by_an_unmapped_pokemon_are_not_merged(tmp_path):
    out, name_map = _write_weeks(tmp_path, extra_slots=[("w9", "p1", "Miasmaw", "Miasmaw", "listed", 1, 0)])
    res = evaluate(out, name_map, train_frac=0.6, test_frac=0.2, min_test=1)
    test = res.teams[res.teams["split"] == "test"]
    assert sorted(test["player"]) == ["alice", "alice", "dave"]          # week 9 team = week 8 team + Miasmaw
    assert set(test.loc[test["player"] == "alice", "members"]) == {"1:1 2:2 4:4"}   # Miasmaw is not a member


def test_a_team_slot_table_from_an_older_parse_fails_with_the_missing_columns(tmp_path):
    out, name_map = _write_weeks(tmp_path)
    slots = pd.read_parquet(out / "battle_team_slot.parquet").drop(columns=["species_observed", "form_status"])
    slots.to_parquet(out / "battle_team_slot.parquet")
    with pytest.raises(ValueError, match="species_observed.*form_status"):
        evaluate(out, name_map, train_frac=0.6, test_frac=0.2, min_test=1)
