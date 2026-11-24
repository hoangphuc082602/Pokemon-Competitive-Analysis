# Power BI dashboard plan

Audience: a recruiter or analyst who opens the report for two minutes, and a player who wants to explore one regulation.
Rule for every page: **state the population** (regulation, rating band) and show the **sample size** next to any rate.
All numbers come from the aggregate tables described in [`Metrics.md`](../Metrics.md); nothing is recomputed from raw replays.

## 1. Data model

Source: the CSV / Parquet files in `data/aggregates/` (simplest, no driver needed) or the same tables in MySQL
(`--to-mysql`; needs the MySQL connector). Use **Import** mode: the tables are small (the largest, teammate pairs, has a few hundred thousand rows).

| Table | Role | Grain |
|---|---|---|
| `dim_regulation` | dimension | one row per regulation (label, sort order, first / last / busiest month) |
| `dim_rating_band` | dimension | one row per band, with `sort_order` (`all`, `below_1200` ... `unknown`) |
| `dim_month` | dimension | one row per month (`month_start` as a date) |
| `dim_species` | dimension | one row per species (`species_id`, label, `has_masked_form`) |
| `regulation_totals` | fact (denominators) | regulation × rating band: battles, player-battles |
| `pokemon_usage_stats` | fact | regulation × rating band × species × form |
| `pokemon_usage_monthly` + `regulation_monthly_totals` | fact | regulation × month × rating band × species; `tail` flag (per regulation-month) |
| `pokemon_tera_summary`, `pokemon_tera_types` | fact | regulation × rating band × species (× Tera type) |
| `pokemon_partner_stats` → `pair_directed` | fact | regulation × rating band × **ordered** species pair (see 1.1) |

Relationships (all many-to-one, single direction from the dimension):

- `dim_regulation[regulation]` → every fact table.
- `dim_rating_band[rating_band]` → `regulation_totals`, `pokemon_usage_stats`, `pokemon_tera_*`, `pokemon_partner_stats`,
  `pokemon_usage_monthly`, `regulation_monthly_totals`.
- `dim_month[month]` → `pokemon_usage_monthly`, `regulation_monthly_totals`.
- `dim_species[species_id]` → `pokemon_usage_stats`, `pokemon_usage_monthly`, `pokemon_tera_*`, `pair_directed[species_a_id]`.
  For the partner's species make a second copy `dim_partner` related to `pair_directed[species_b_id]` (role-playing dimension).
  Load `pokemon_partner_stats` only as the source of `pair_directed` and disable its load (otherwise both tables count every pair).

### 1.1 Directed pairs (required)

`pokemon_partner_stats` stores each pair **once**, with `species_a_id < species_b_id` (partner_stats.py). A matrix or a "partners of X" list
built on it would be half empty, and `share_of_a` would be the right share only when X happens to be the lower id. Add one Power Query
query `pair_directed` (Reference `pokemon_partner_stats`, then Advanced Editor) that appends the mirrored rows:

```m
let
    Src   = pokemon_partner_stats,
    Step1 = Table.RenameColumns(Src, {{"species_a", "t_species_b"}, {"species_b", "t_species_a"}, {"species_a_id", "t_species_b_id"},
            {"species_b_id", "t_species_a_id"}, {"teams_a", "t_teams_b"}, {"teams_b", "t_teams_a"}, {"share_of_a", "t_share_of_b"},
            {"share_of_b", "t_share_of_a"}}),
    Step2 = Table.RenameColumns(Step1, {{"t_species_b", "species_b"}, {"t_species_a", "species_a"}, {"t_species_b_id", "species_b_id"},
            {"t_species_a_id", "species_a_id"}, {"t_teams_b", "teams_b"}, {"t_teams_a", "teams_a"}, {"t_share_of_b", "share_of_b"},
            {"t_share_of_a", "share_of_a"}}),
    Out   = Table.Combine({Src, Step2})
in
    Out
```

Check: `Table.RowCount(pair_directed)` is twice the rows of `pokemon_partner_stats`. In `pair_directed`, `share_of_a` is always P(B | A) for
the row's A, `lift`, `teams_both`, `win_rate` and its interval are symmetric. Filter on A (the species of the page), then B lists its partners.

Three modelling rules, because getting them wrong gives plausible but false numbers:

1. **Never sum across rating bands.** The `all` band repeats the other bands. Make the rating-band slicer **single select, default `all`**.
2. **Denominators come from `regulation_totals`, not from the fact rows.** `player_battles` is repeated on every usage row, so a sum would multiply it.
3. **Sum rates as ratios of sums** (`DIVIDE(SUM(wins), SUM(appearances))`), never average percentages.

## 2. Measures (DAX)

```dax
Teams          = SUM ( pokemon_usage_stats[appearances] )
Wins           = SUM ( pokemon_usage_stats[wins] )
Sent Out       = SUM ( pokemon_usage_stats[sent_out] )
Leads          = SUM ( pokemon_usage_stats[leads] )
Player Battles = SUM ( regulation_totals[player_battles] )

Usage %        = DIVIDE ( [Teams], [Player Battles] )
Win %          = DIVIDE ( [Wins], [Teams] )
Sent-out %     = DIVIDE ( [Sent Out], [Teams] )
Lead %         = DIVIDE ( [Leads], [Teams] )

Win CI Low =
VAR n = [Teams]  VAR p = [Win %]  VAR z = 1.96
RETURN IF ( n = 0, BLANK (),
    ( p + z ^ 2 / ( 2 * n ) - z * SQRT ( p * ( 1 - p ) / n + z ^ 2 / ( 4 * n ^ 2 ) ) ) / ( 1 + z ^ 2 / n ) )

Win CI High =
VAR n = [Teams]  VAR p = [Win %]  VAR z = 1.96
RETURN IF ( n = 0, BLANK (),
    ( p + z ^ 2 / ( 2 * n ) + z * SQRT ( p * ( 1 - p ) / n + z ^ 2 / ( 4 * n ^ 2 ) ) ) / ( 1 + z ^ 2 / n ) )

-- all species of the same regulation and band: the fair reference for a win rate (it is not 50% in a high band)
Band Baseline Win % = CALCULATE ( DIVIDE ( [Wins], [Teams] ), ALL ( dim_species ) )
Win vs Band (pp)    = ( [Win %] - [Band Baseline Win %] ) * 100

Tera %  = DIVIDE ( SUM ( pokemon_tera_summary[tera_events] ), SUM ( pokemon_tera_summary[sent_out] ) )
Lift    = MAX ( pokemon_partner_stats[lift] )                  -- one row per pair, regulation and band
Pair %  = MAX ( pair_directed[share_of_a] )                    -- share of A's teams that also have B (A = the filtered species)
Pair Win %      = MAX ( pair_directed[win_rate] )
Pair Win vs Band (pp) = ( [Pair Win %] - MAX ( pair_directed[band_win_rate] ) ) * 100   -- of the team, not of A: a screening value, not synergy

-- monthly visuals: pokemon_usage_monthly has one row set per rating band ('all' repeats the bands): always filter one band
Monthly Teams         = SUM ( pokemon_usage_monthly[appearances] )
Monthly Player Battles = SUM ( regulation_monthly_totals[player_battles] )
Monthly Usage %       = DIVIDE ( [Monthly Teams], [Monthly Player Battles] )
Monthly Win %         = DIVIDE ( SUM ( pokemon_usage_monthly[wins] ), [Monthly Teams] )

-- sample-size rule with an adjustable limit: What-if parameter `Min Teams` (100 to 5,000, default 500)
Show Row = IF ( [Teams] >= 'Min Teams'[Min Teams Value], 1 )     -- visual filter: Show Row = 1
```

Visual-level filters used everywhere: `[Teams] >= 100` (hide tiny samples; the Meta scatter uses `Show Row`, default 500, the limit the EDA used), and on the monthly visuals
`regulation_monthly_totals[tail] = FALSE` (months far below the busiest one are a different population).

## 3. Pages

1. **Overview.** Cards: battles, player-battles, regulations covered, date range. Area chart of battles per month by regulation
   (tail months excluded). Bar chart of player-battles per rating band. Slicers: regulation, rating band.
2. **Meta.** Top-N species by `Usage %` (N from a what-if parameter), a scatter of `Usage %` against `Win vs Band (pp)` (bubble size `Teams`; the EDA found a positive but modest link, so title it "correlation, not cause"),
   and a table with usage, win, interval, sent-out and lead rates. Conditional format `Win vs Band (pp)`.
3. **Pokémon detail** (drill-through from any species). Monthly usage line, win rate with its interval, sent-out and lead rates,
   Tera rate and a bar of Tera types, top partners (share, lift, `Win vs Band`), and for the nine masked families a stacked bar by
   `form_basis` (`observed` / `unobserved`), so the unknown share is visible.
4. **Teammates.** A heat map of lift for the 20 most used species (matrix, species A × species B on `pair_directed`; Top N on both axes by `Teams`), with a size filter on `teams_both`.
5. **Method and data notes.** Scope (VGC only, completed battles), the population numbers, and the caveats from
   `Metrics.md`: upload month, tail months, Illusion, form-masked species, Tera win rates not comparable, lift is not synergy. Also state why there is no matchup page:
   team-level counters deviate little from expectation (median 0.6-0.8 pp, `documents/EDA_FINDINGS.md`) and the battles of one player are not independent.

## 4. Build order

1. Import the dimensions and facts, set the relationships, hide the key columns.
2. Create the measures above and check three numbers against the CLI output: Reg I 2025 Calyrex usage 48.8% (band `all`), the sum of monthly
   battles of Reg F 2026 equal to 502,121 (tail months included for this check), and Incineroar's partner share with Urshifu 55.2% (Reg F 2026,
   band `all`, on `pair_directed` filtered to A = Incineroar). Also: with a band selected, `Player Battles` equals `regulation_totals` for that band.
3. Pages 1 and 2, then 3, then 4, then 5.
4. Export screenshots and a PDF for the README; commit the `.pbix` only if it stays small (it holds aggregates only, no replay logs).

## 5. Pitfalls to design against

- Pairs are stored once: use `pair_directed`, never `pokemon_partner_stats` directly in a visual (section 1.1).
- Monthly visuals ignore the rating band: say so in the visual title.
- A rating band with few battles produces wide intervals: show the interval, not just the point value.
- Champions Reg M-A has no Tera, so its Tera rate is zero by construction, not by choice.
- A rate shown for one species without `Teams` next to it breaks the project's own rule.
- Percentages in a tooltip must use the same denominator as the visual.