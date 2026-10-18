"""Team-level matchups between species (definitions: METRICS.md): pokemon_matchup_stats.

    python -m python.analytics.matchup_stats --output-dir data/output --species Incineroar

Observation: a team containing species A facing a team containing species B in a completed VGC battle
(A != B). `win_rate` is how often A's team won those battles. Every battle yields observations for both sides, so the
table is antisymmetric in band 'all': n(A,B) = n(B,A) and wins(A,B) + wins(B,A) = n. Per rating band it is not (the band is
the band of A's player, which for (B,A) is the other player).
This is a statement about TEAMS that contain the species, not about the species on the field: the other five
Pokémon, the lead and the choice of four are all mixed in, so a low win rate is not proof of a counter.
`win_rate_delta` compares with A's win rate against everything, which removes A's own strength only. The opponent matters
too: teams with rare species are often weaker, so A "beats" them for reasons unrelated to the matchup. `expected_win_rate`
combines both teams' overall win rates (log5) and `win_rate_vs_expected` / `z_vs_expected` measure what is left.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from python.analytics.batches import battle_chunks
from python.analytics.partner_stats import BAND_CODES, BAND_NAMES
from python.analytics.pokemon_usage import load_scope, rating_band, species_labels, wilson

KEYS = ["reg", "band", "a", "b"]


def matchup_counts(team_slot_path: Path, scope: pd.DataFrame, name_map: pd.DataFrame):
    """Returns (ordered pair counts, species team counts, regulation names)."""
    index = pd.Index(scope.index.astype(str))
    reg_cat = scope["regulation"].astype("category")
    reg_codes, regs = reg_cat.cat.codes.to_numpy(), reg_cat.cat.categories.to_numpy()
    p1_win, p1_rating, p2_rating = scope["p1_win"].to_numpy(), scope["p1_rating"].to_numpy(), scope["p2_rating"].to_numpy()
    species_of = name_map.drop_duplicates("showdown_name").set_index("showdown_name")["species_id"].to_dict()
    pairs, singles = [], []

    for df in battle_chunks(team_slot_path, ["battle_id", "player_side", "pokemon_name"]):
        pos = index.get_indexer(df["battle_id"].astype(str))
        keep = pos >= 0
        df, pos = df[keep].reset_index(drop=True), pos[keep]
        sid = df["pokemon_name"].astype(object).map(species_of)
        ok = sid.notna().to_numpy()
        df, pos, sid = df[ok], pos[ok], sid[ok].astype(int).to_numpy()
        if len(df) == 0:
            continue
        is_p1 = df["player_side"].to_numpy() == "p1"
        band = np.array([BAND_CODES[b] for b in rating_band(np.where(is_p1, p1_rating[pos], p2_rating[pos]))])
        t = pd.DataFrame({"pos": pos, "p1": is_p1, "sid": sid, "reg": reg_codes[pos], "band": band,
                          "won": np.where(is_p1, p1_win[pos], ~p1_win[pos]).astype(int)}).drop_duplicates(["pos", "p1", "sid"])
        singles.append(t.groupby(["reg", "band", "sid"], as_index=False).agg(teams=("won", "size"), wins=("won", "sum")))
        m = t.merge(t[["pos", "p1", "sid"]], on="pos", suffixes=("_a", "_b"))
        m = m[(m["p1_a"] != m["p1_b"]) & (m["sid_a"] != m["sid_b"])].rename(columns={"sid_a": "a", "sid_b": "b"})
        pairs.append(m.groupby(KEYS, as_index=False).agg(battles=("won", "size"), wins=("won", "sum")))
        if len(pairs) >= 100:
            pairs[:] = [pd.concat(pairs).groupby(KEYS, as_index=False).sum()]
    pairs = pd.concat(pairs).groupby(KEYS, as_index=False).sum()
    singles = pd.concat(singles).groupby(["reg", "band", "sid"], as_index=False).sum()
    return pairs, singles, regs


def is_antisymmetric(table: pd.DataFrame) -> bool:
    """In band 'all': n(A,B) == n(B,A) and wins(A,B) + wins(B,A) == n for every pair present in both directions."""
    t = table[table["rating_band"] == "all"][["regulation", "rating_band", "species_a_id", "species_b_id", "battles", "wins"]]
    back = t.rename(columns={"species_a_id": "species_b_id", "species_b_id": "species_a_id", "battles": "n2", "wins": "w2"})
    m = t.merge(back, on=["regulation", "rating_band", "species_a_id", "species_b_id"])
    return bool(len(m) > 0 and (m["battles"] == m["n2"]).all() and (m["wins"] + m["w2"] == m["battles"]).all())


def build_matchup_table(out_dir: Path, name_map: pd.DataFrame, min_support: int = 200) -> pd.DataFrame:
    scope = load_scope(out_dir)
    pairs, singles, regs = matchup_counts(out_dir / "battle_team_slot.parquet", scope, name_map)
    every = pairs.groupby(["reg", "a", "b"], as_index=False)[["battles", "wins"]].sum().assign(band=-1)
    pairs = pd.concat([every, pairs], ignore_index=True)
    all_singles = singles.groupby(["reg", "sid"], as_index=False)[["teams", "wins"]].sum().assign(band=-1)
    singles = pd.concat([all_singles, singles], ignore_index=True)
    pairs = pairs[pairs["battles"] >= min_support]
    pairs = pairs.merge(singles.rename(columns={"sid": "a", "teams": "teams_a", "wins": "wins_a_all"}), on=["reg", "band", "a"])
    b_rates = all_singles.assign(b_win_rate=all_singles["wins"] / all_singles["teams"])[["reg", "sid", "b_win_rate"]].rename(columns={"sid": "b"})
    pairs = pairs.merge(b_rates, on=["reg", "b"])

    labels = species_labels(name_map)
    out = pd.DataFrame({
        "regulation": regs[pairs["reg"].to_numpy()],
        "rating_band": pairs["band"].map(lambda c: "all" if c < 0 else BAND_NAMES[c]),
        "species_a": pairs["a"].map(labels), "species_b": pairs["b"].map(labels),
        "species_a_id": pairs["a"], "species_b_id": pairs["b"],
        "battles": pairs["battles"], "wins": pairs["wins"], "teams_a": pairs["teams_a"]})
    out["win_rate"] = out["wins"] / out["battles"]
    out["win_ci_low"], out["win_ci_high"] = wilson(out["wins"], out["battles"])
    out["a_win_rate"] = pairs["wins_a_all"] / pairs["teams_a"]           # A's win rate against everything
    out["win_rate_delta"] = out["win_rate"] - out["a_win_rate"]
    out["b_win_rate"] = pairs["b_win_rate"]                              # B's win rate against everything (all bands)
    pa, pb = out["a_win_rate"].clip(0.01, 0.99), out["b_win_rate"].clip(0.01, 0.99)
    out["expected_win_rate"] = pa * (1 - pb) / (pa * (1 - pb) + pb * (1 - pa))                   # log5
    out["win_rate_vs_expected"] = out["win_rate"] - out["expected_win_rate"]
    out["z_vs_expected"] = out["win_rate_vs_expected"] / np.sqrt(out["expected_win_rate"] * (1 - out["expected_win_rate"]) / out["battles"])
    return out.sort_values(["regulation", "rating_band", "battles"], ascending=[True, True, False]).reset_index(drop=True)


def opponents_of(table: pd.DataFrame, species: str, regulation: str, band: str = "all", min_battles: int = 500, n: int = 8):
    """(hardest, easiest) opponents by z-score of the win rate against what both teams' overall strength predicts."""
    t = table[(table["species_a"] == species) & (table["regulation"] == regulation) & (table["rating_band"] == band)]
    t = t[t["battles"] >= min_battles]
    t = pd.DataFrame({"opponent": t["species_b"], "battles": t["battles"], "win_%": (100 * t["win_rate"]).round(1),
                      "expected_%": (100 * t["expected_win_rate"]).round(1),
                      "vs_expected_pp": (100 * t["win_rate_vs_expected"]).round(1), "z": t["z_vs_expected"].round(1)}).sort_values("z")
    return t.head(n).reset_index(drop=True), t.tail(n).iloc[::-1].reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", type=Path, default=Path("data/output"))
    ap.add_argument("--map", type=Path, default=Path("data/mapping/pokemon_name_map.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/aggregates"))
    ap.add_argument("--min-support", type=int, default=200, help="drop ordered pairs seen in fewer battles")
    ap.add_argument("--species", default="Incineroar")
    ap.add_argument("--show", default=None, metavar="REGULATION")
    ap.add_argument("--band", default="all")
    ap.add_argument("--to-mysql", action="store_true", help="also (re)write table pokemon_matchup_stats")
    args = ap.parse_args(argv)

    table = build_matchup_table(args.output_dir, pd.read_csv(args.map, dtype={"showdown_name": str}), args.min_support)
    args.out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out / "pokemon_matchup_stats.parquet", index=False)
    table.to_csv(args.out / "pokemon_matchup_stats.csv", index=False)
    a = table[table["rating_band"] == "all"]
    print(f"{len(table):,} matchup rows (ordered pairs seen in at least {args.min_support} battles)")
    print(f"checks: antisymmetric (n equal both ways, wins add up to n): {is_antisymmetric(table)}; "
          f"win rate over all observations {100 * a['wins'].sum() / a['battles'].sum():.2f}% (expect 50.00)")
    reg = args.show or a.groupby("regulation")["battles"].sum().idxmax()
    hard, easy = opponents_of(table, args.species, reg, args.band)
    print(f"\nTeams with {args.species} in {reg}, band '{args.band}' (opponent team contains ...):")
    print("hardest (lowest z against expectation):\n" + hard.to_string(index=False) + "\neasiest:\n" + easy.to_string(index=False))
    if args.to_mysql:
        from python.analytics.sql_output import write_table
        from python.database.db_connection import engine
        write_table(table, "pokemon_matchup_stats", engine, [["regulation", "rating_band", "species_a_id", "species_b_id"]])
        print("Wrote pokemon_matchup_stats to MySQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())