"""Evaluator of the v2.0 recommender (#51): temporal split, team dedup, leave-one-out Hit@k / MRR.

Population: completed VGC battles (python.analytics.pokemon_usage.load_scope) with an upload time; unit =
player-battle, one team per player-battle.

1. Temporal split, within each regulation, by UTC week (Monday start): weeks in time order go to train
   while the battles of the earlier weeks are < train_frac of the regulation, to test once they are
   >= 1 - test_frac, to validation in between. A week is never split, so a battle is in one split only.
2. Dedup: a player's (Showdown user id, per regulation) identical teams (same team-preview names) are one
   team, kept at its earliest battle; the later copies, in any split, are dropped (Bo3 games and team reuse
   are not independent).
3. The components are built from the train weeks' battles only (every battle of those weeks).
4. Leave-one-out on the test (or validation) teams: each member is hidden in turn, the scorer ranks
   candidates from the other members, candidates of a species already on the team are removed; the rank
   of the hidden member is kept (none when it is not ranked; a member of unknown form is matched on its
   species). Teams with 2-5 mapped members are scored too (the CLI prints the share with 6).
5. Hit@k and MRR per regulation x rating band (the player's own band; 'all' is scored separately), with
   the test size; cells under `min_test` test teams are listed as skipped with their size.

A member is (species_id, poke_id), poke_id None when the form is unknown (masked and never sent out, or
not in the master data): forms are kept apart, only the way the form is known (form_basis) is merged.
A scorer is any callable (team members, regulation, rating band) -> candidates, best first.

    python -m python.recommendation.evaluation --output-dir data/output --work data/aggregates/evaluation
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from python.analytics.batches import battle_chunks
from python.analytics.pokemon_usage import form_keys, load_scope, rating_band
from python.recommendation.components import usage_component

Member = tuple
Scorer = Callable[[Sequence[Member], str, str], Sequence[Member]]
WEEK = 7 * 86400
MONDAY = 3 * 86400            # 1970-01-01 was a Thursday
SPLITS = ("train", "validation", "test")
TEAM_COLUMNS = ["battle_id", "side", "regulation", "rating_band", "player", "week", "split", "team_key", "members"]


# --- split and teams -------------------------------------------------------------------------------------------
def split_battles(out_dir: Path, train_frac: float = 0.7, test_frac: float = 0.15) -> pd.DataFrame:
    """In-scope battles with an upload time, index battle_id (str): regulation, time, week, split, and
    p1/p2 rating and user (from load_scope)."""
    if not (0 < train_frac and 0 < test_frac and train_frac + test_frac <= 1):
        raise ValueError(f"need 0 < train_frac, 0 < test_frac, train_frac + test_frac <= 1; got {train_frac}, {test_frac}")
    scope = load_scope(out_dir)
    scope.index = scope.index.astype(str)
    t = pq.read_table(out_dir / "battle.parquet", columns=["battle_id", "upload_time"]).to_pandas()
    t = t.assign(battle_id=t["battle_id"].astype(str)).drop_duplicates("battle_id").set_index("battle_id")["upload_time"]
    scope["time"] = pd.to_numeric(t.reindex(scope.index), errors="coerce").astype(float).to_numpy()
    scope = scope[scope["time"].notna()].copy()
    scope["week"] = np.floor((scope["time"] + MONDAY) / WEEK).astype(int)
    per_week = scope.groupby(["regulation", "week"]).size().rename("battles").reset_index()
    per_week = per_week.sort_values(["regulation", "week"])
    total = per_week.groupby("regulation")["battles"].transform("sum")
    before = (per_week.groupby("regulation")["battles"].cumsum() - per_week["battles"]) / total
    eps = 1e-12
    per_week["split"] = np.where(before < train_frac - eps, "train",
                                 np.where(before >= 1 - test_frac - eps, "test", "validation"))
    scope = scope.join(per_week.set_index(["regulation", "week"])["split"], on=["regulation", "week"])
    return scope


def showdown_id(names) -> pd.Series:
    """Showdown user ids: lower case, letters and digits only ('Carol' and 'carol' are one user); None if empty."""
    uid = pd.Series(names, dtype=object).str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    return uid.where(uid.notna() & (uid != ""), None)


def load_teams(out_dir: Path, name_map: pd.DataFrame, battles: pd.DataFrame,
               keep_members: Iterable[str] = ("validation", "test")) -> pd.DataFrame:
    """One row per kept (deduplicated) player-battle with at least 2 mapped members (TEAM_COLUMNS).
    team_key = hash of the sorted team-preview names, mapped or not (the dedup identity); members = sorted
    'species_id:poke_id' tokens ('-' = form unknown), filled for the `keep_members` splits only (memory).
    Team slots are read in whole-battle chunks; slots whose name is not in the mapping are dropped."""
    index = pd.Index(battles.index)
    nm = name_map.drop_duplicates("showdown_name").set_index("showdown_name")
    species_of, poke_of = nm["species_id"].to_dict(), nm["poke_id"].to_dict()
    cols = ["battle_id", "player_side", "pokemon_name", "species_observed", "form_status"]
    path = out_dir / "battle_team_slot.parquet"
    missing = [c for c in cols if c not in pq.ParquetFile(path).schema_arrow.names]
    if missing:
        raise ValueError(f"{path} has no column(s) {', '.join(missing)}: a parse older than the form columns; "
                         "pass the --output-dir of a current parse")
    parts = []
    for df in battle_chunks(path, cols):
        pos = index.get_indexer(df["battle_id"].astype(str))
        df = df[pos >= 0].assign(pos=pos[pos >= 0]).reset_index(drop=True)
        if df.empty:
            continue
        sid, pid, _ = form_keys(df, species_of, poke_of)
        df = df.assign(sid=sid.to_numpy(), pid=pid.to_numpy(), name=df["pokemon_name"].astype(str))
        df = df.sort_values(["pos", "player_side", "name"])
        names = df.groupby(["pos", "player_side"], sort=False)["name"].agg(" ".join).rename("names")     # identity: every preview name
        mapped = df[df["sid"].notna()]
        pid_text = pd.Series(np.where(mapped["pid"].isna(), "-", mapped["pid"].fillna(0).astype(int).astype(str)),
                             index=mapped.index)
        mapped = mapped.assign(token=mapped["sid"].astype(int).astype(str) + ":" + pid_text)
        g = mapped.groupby(["pos", "player_side"], sort=False)
        part = pd.DataFrame({"members": g["token"].agg(" ".join), "size": g.size()}).join(names).reset_index()
        part = part[part["size"] >= 2]
        if part.empty:
            continue
        part["team_key"] = pd.util.hash_pandas_object(part["names"], index=False).to_numpy()
        part["split"] = battles["split"].to_numpy()[part["pos"].to_numpy()]
        part.loc[~part["split"].isin(list(keep_members)), "members"] = None
        parts.append(part[["pos", "player_side", "team_key", "split", "members"]])
    teams = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["pos", "player_side", "team_key", "split", "members"])
    pos, is_p1 = teams["pos"].to_numpy(dtype=int), (teams["player_side"] == "p1").to_numpy()
    teams["battle_id"] = battles.index.to_numpy()[pos]
    teams["side"] = teams["player_side"]
    teams["regulation"] = battles["regulation"].to_numpy()[pos]
    teams["week"] = battles["week"].to_numpy()[pos]
    teams["time"] = battles["time"].to_numpy()[pos]
    teams["rating_band"] = rating_band(np.where(is_p1, battles["p1_rating"].to_numpy()[pos], battles["p2_rating"].to_numpy()[pos]))
    users = np.where(is_p1, battles["p1_user"].to_numpy()[pos], battles["p2_user"].to_numpy()[pos])
    teams["player"] = showdown_id(users).to_numpy()
    unknown = teams["player"].isna()                         # no user name: the player-battle is its own player
    teams.loc[unknown, "player"] = "?" + teams.loc[unknown, "battle_id"].astype(str) + "/" + teams.loc[unknown, "side"]
    teams = teams.sort_values(["time", "battle_id", "side"], kind="stable")
    teams = teams.drop_duplicates(["regulation", "player", "team_key"], keep="first")
    return teams[TEAM_COLUMNS].reset_index(drop=True)


def parse_members(members: str) -> tuple:
    """'727:727 892:-' -> ((727, 727), (892, None))."""
    out = []
    for tok in members.split():
        s, p = tok.split(":")
        out.append((int(s), None if p == "-" else int(p)))
    return tuple(out)


# --- scorers ---------------------------------------------------------------------------------------------------
def popularity_scorer(component: pd.DataFrame) -> Scorer:
    """Ranks candidates by usage (appearances) in the regulation and band of the usage component, whatever
    the team; ties by species_id then poke_id (unknown form last). A cell absent from the component ranks
    nothing."""
    c = component.assign(pid=component["poke_id"].astype("Float64"))
    g = c.groupby(["regulation", "rating_band", "species_id", "pid"], dropna=False)["appearances"].sum().reset_index()
    g = g.sort_values(["regulation", "rating_band", "appearances", "species_id", "pid"],
                      ascending=[True, True, False, True, True], na_position="last")
    ranking = {}
    for (reg, band), cell in g.groupby(["regulation", "rating_band"], sort=False):
        ranking[(reg, band)] = [(int(s), None if pd.isna(p) else int(p)) for s, p in zip(cell["species_id"], cell["pid"])]

    def scorer(team, regulation, band):
        return ranking.get((regulation, band), [])
    return scorer


# --- leave-one-out and metrics ---------------------------------------------------------------------------------
def _rank(ranked: Sequence[Member], hidden: Member, context: Sequence[Member]) -> int | None:
    """1-based rank of `hidden` once candidates of a species already on the team are removed. A hidden
    member of unknown form (poke_id None) is found by the first candidate of its species (species only);
    a known form needs the exact (species_id, poke_id)."""
    taken, rank, species_only = {m[0] for m in context}, 0, hidden[1] is None
    for cand in ranked:
        if cand[0] in taken:
            continue
        rank += 1
        if cand == hidden or (species_only and cand[0] == hidden[0]):
            return rank
    return None


def leave_one_out(teams: pd.DataFrame, scorer: Scorer) -> pd.DataFrame:
    """teams: columns regulation, rating_band (the player's own band), members (tuple of members).
    Each member is hidden in turn and ranked from the others, once with band 'all' and once with the
    team's own band. One row per query: regulation, rating_band, team (row label), hidden_species_id,
    hidden_poke_id, rank (NaN = not ranked)."""
    rows = []
    for team, reg, band, members in zip(teams.index, teams["regulation"], teams["rating_band"], teams["members"]):
        for b in ("all", band):
            for i, hidden in enumerate(members):
                context = members[:i] + members[i + 1:]
                rows.append((reg, b, team, hidden[0], hidden[1], _rank(scorer(context, reg, b), hidden, context)))
    out = pd.DataFrame(rows, columns=["regulation", "rating_band", "team", "hidden_species_id", "hidden_poke_id", "rank"])
    for c in ("hidden_species_id", "hidden_poke_id"):
        out[c] = out[c].astype("Int64")
    out["rank"] = out["rank"].astype("Float64")
    return out


def metrics(ranks: pd.DataFrame, k: int = 10, min_test: int = 100) -> pd.DataFrame:
    """Hit@k (share of queries ranked <= k) and MRR (mean reciprocal rank, 0 when not ranked) per regulation
    x rating band, with the test size (teams, queries). Cells with fewer than `min_test` test teams are kept
    as skipped rows with their size and no metric. 'all' is its own band, never a sum of the band rows."""
    r = ranks.assign(hit=(ranks["rank"] <= k).fillna(False).astype(float),
                     rr=(1 / ranks["rank"]).fillna(0.0).astype(float))
    m = (r.groupby(["regulation", "rating_band"])
         .agg(test_teams=("team", "nunique"), queries=("team", "size"), hit=("hit", "mean"), mrr=("rr", "mean"))
         .reset_index().rename(columns={"hit": f"hit_at_{k}"}))
    m["skipped"] = m["test_teams"] < min_test
    m.loc[m["skipped"], [f"hit_at_{k}", "mrr"]] = float("nan")
    return m


# --- end to end ------------------------------------------------------------------------------------------------
@dataclass
class Evaluation:
    metrics: pd.DataFrame      # per regulation x band: test size, Hit@k, MRR, train player-battles, skipped
    teams: pd.DataFrame        # kept teams of every split (TEAM_COLUMNS)
    component: pd.DataFrame    # usage component of the train weeks
    ranks: pd.DataFrame        # one row per leave-one-out query


def evaluate_ranks(teams: pd.DataFrame, scorer: Scorer, split: str = "test") -> pd.DataFrame:
    """Leave-one-out on the kept teams of `split`, one regulation at a time."""
    parts = []
    sel = teams[teams["split"] == split]
    for _, t in sel.groupby("regulation", sort=True):
        parts.append(leave_one_out(t.assign(members=t["members"].map(parse_members)), scorer))
    return pd.concat(parts, ignore_index=True) if parts else leave_one_out(sel.iloc[:0], scorer)


def report(ranks: pd.DataFrame, component: pd.DataFrame, k: int = 10, min_test: int = 100) -> pd.DataFrame:
    """metrics() plus the `n` of the train component (player-battles of the regulation and band); a
    regulation of the train component without any test team is listed as skipped with size 0."""
    m = metrics(ranks, k, min_test)
    missing = sorted(set(component["regulation"]) - set(m["regulation"]))
    if missing:
        empty = pd.DataFrame({"regulation": missing, "rating_band": "all", "test_teams": 0, "queries": 0,
                              f"hit_at_{k}": float("nan"), "mrr": float("nan"), "skipped": True})
        m = pd.concat([m, empty], ignore_index=True).sort_values(["regulation", "rating_band"], ignore_index=True)
    n = component.groupby(["regulation", "rating_band"])["player_battles"].first().rename("train_player_battles")
    return m.join(n, on=["regulation", "rating_band"])


def evaluate(out_dir: Path, name_map: pd.DataFrame, train_frac: float = 0.7, test_frac: float = 0.15,
             split: str = "test", k: int = 10, min_test: int = 100) -> Evaluation:
    """Popularity scorer, end to end, in memory (the CLI runs the same steps with a resumable work dir)."""
    battles = split_battles(out_dir, train_frac, test_frac)
    teams = load_teams(out_dir, name_map, battles)
    component = usage_component(out_dir, name_map, battle_ids=battles.index[battles["split"] == "train"])
    ranks = evaluate_ranks(teams, popularity_scorer(component), split)
    return Evaluation(report(ranks, component, k, min_test), teams, component, ranks)


# --- CLI (resumable: every step is cached in --work and reused when the split parameters match) -----------------
def _markdown(m: pd.DataFrame, k: int, params: dict) -> str:
    lines = [f"# Recommendation evaluation: popularity (Hit@{k} / MRR)", "",
             "Population: completed VGC battles with an upload time; unit = player-battle; identical teams of one "
             "player (per regulation) count once, at their earliest battle. Temporal split by UTC week within each "
             f"regulation: train {params['train_frac']:.0%} / test {params['test_frac']:.0%} of the battles "
             f"(validation in between); evaluated split: {params['split']}. Leave-one-out: each member of a test "
             "team is hidden and ranked from the others; candidates already on the team are excluded. "
             f"Popularity = usage in the train weeks of the same regulation and band. Rating band = the player's own; "
             f"'all' is scored on its own, never summed from the bands. Cells with fewer than {params['min_test']} "
             "test teams are skipped.", ""]
    for reg, cell in m.groupby("regulation", sort=True):
        lines += [f"## {reg}", "", f"| rating band | test teams | queries | train player-battles | Hit@{k} | MRR |",
                  "|---|---:|---:|---:|---:|---:|"]
        for r in cell.itertuples(index=False):
            hit, mrr = getattr(r, f"hit_at_{k}"), r.mrr
            shown = ("skipped", "skipped") if r.skipped else (f"{hit:.3f}", f"{mrr:.3f}")
            train_n = "-" if pd.isna(r.train_player_battles) else f"{int(r.train_player_battles):,}"
            lines.append(f"| {r.rating_band} | {r.test_teams:,} | {r.queries:,} | {train_n} | {shown[0]} | {shown[1]} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Evaluation of the popularity scorer (#51): Hit@k / MRR report.")
    ap.add_argument("--output-dir", type=Path, default=Path("data/output"))
    ap.add_argument("--map", type=Path, default=Path("data/mapping/pokemon_name_map.csv"))
    ap.add_argument("--work", type=Path, default=Path("data/aggregates/evaluation"),
                    help="cache of each step (teams, train component, ranks) and the report")
    ap.add_argument("--train-frac", type=float, default=0.7)
    ap.add_argument("--test-frac", type=float, default=0.15)
    ap.add_argument("--split", default="test", choices=["validation", "test"])
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--min-test", type=int, default=100, help="minimum test teams of a regulation x band cell")
    ap.add_argument("--fresh", action="store_true", help="drop the cache of --work and start again")
    args = ap.parse_args(argv)

    work = args.work
    params = {"train_frac": args.train_frac, "test_frac": args.test_frac,
              "output_dir": str(args.output_dir.resolve()), "map": str(args.map.resolve())}
    stamp = work / "params.json"
    if args.fresh:
        for f in [stamp, work / "teams.parquet", work / "train_usage_component.parquet", *work.glob("ranks_*/*.parquet")]:
            f.unlink(missing_ok=True)
    if stamp.exists() and json.loads(stamp.read_text(encoding="utf-8")) != params:
        raise SystemExit(f"{work} holds a run with {stamp.read_text(encoding='utf-8')}; pass --fresh or another --work")
    work.mkdir(parents=True, exist_ok=True)
    stamp.write_text(json.dumps(params), encoding="utf-8")
    name_map = pd.read_csv(args.map, dtype={"showdown_name": str})

    teams_path, comp_path = work / "teams.parquet", work / "train_usage_component.parquet"
    battles = None
    if teams_path.exists():
        print(f"reusing teams: {teams_path}")
        teams = pd.read_parquet(teams_path)
    else:
        battles = split_battles(args.output_dir, args.train_frac, args.test_frac)
        print("Battles per regulation and split:")
        print(battles.groupby(["regulation", "split"]).size().unstack(fill_value=0).to_string())
        teams = load_teams(args.output_dir, name_map, battles)
        teams.to_parquet(teams_path, index=False)
    if comp_path.exists():
        print(f"reusing train component: {comp_path}")
        component = pd.read_parquet(comp_path)
    else:
        if battles is None:
            battles = split_battles(args.output_dir, args.train_frac, args.test_frac)
        component = usage_component(args.output_dir, name_map, battle_ids=battles.index[battles["split"] == "train"])
        component.to_parquet(comp_path, index=False)
    print("\nKept (deduplicated) teams per regulation and split:")
    print(teams.groupby(["regulation", "split"]).size().unstack(fill_value=0).to_string())

    evaluated = teams.loc[teams["split"] == args.split, "members"]
    full = evaluated.str.split().str.len().eq(6).mean() if len(evaluated) else float("nan")
    print(f"\n{args.split} teams with 6 mapped members: {full:.1%} of {len(evaluated):,} (2-5 are scored too)")
    scorer, rank_dir, parts = popularity_scorer(component), work / f"ranks_{args.split}", []
    rank_dir.mkdir(exist_ok=True)
    for reg, t in teams[teams["split"] == args.split].groupby("regulation", sort=True):
        path = rank_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '_', reg)}.parquet"
        if path.exists():
            print(f"reusing ranks {reg}: {path}")
            parts.append(pd.read_parquet(path))
            continue
        r = leave_one_out(t.assign(members=t["members"].map(parse_members)), scorer)
        r.to_parquet(path, index=False)
        parts.append(r)
    ranks = pd.concat(parts, ignore_index=True) if parts else leave_one_out(teams.iloc[:0], scorer)
    m = report(ranks, component, args.k, args.min_test)
    m.to_csv(work / "evaluation_popularity.csv", index=False)
    (work / "evaluation_popularity.md").write_text(
        _markdown(m, args.k, {**params, "split": args.split, "min_test": args.min_test}), encoding="utf-8")
    print(f"\n{m.to_string(index=False)}")
    print(f"\nqueries ranked (hidden member among the candidates): {ranks['rank'].notna().mean():.1%} of {len(ranks):,}; "
          f"report: {work / 'evaluation_popularity.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
