# Power BI dashboard plan

Audience: a recruiter or analyst who opens the report for two minutes, and a player who wants to explore one regulation.
Rule for every page: **state the population** (regulation, rating band) and show the **sample size** next to any rate.
All numbers come from the aggregate tables described in [`METRICS.md`](../METRICS.md); nothing is recomputed from raw replays.

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
| `pokemon_usage_monthly` + `regulation_monthly_totals` | fact | regulation × month × species; `tail` flag |
| `pokemon_tera_summary`, `pokemon_tera_types` | fact | regulation × rating band × species (× Tera type) |
| `pokemon_partner_stats` | fact | regulation × rating band × species pair |

Relationships (all many-to-one, single direction from the dimension):

- `dim_regulation[regulation]` → every fact table.
- `dim_rating_band[rating_band]` → `regulation_totals`, `pokemon_usage_stats`, `pokemon_tera_*`, `pokemon_partner_stats`.
- `dim_month[month]` → `pokemon_usage_monthly`, `regulation_monthly_totals`.
- `dim_species[species_id]` → `pokemon_usage_stats`, `pokemon_usage_monthly`, `pokemon_tera_*`, `pokemon_partner_stats[species_a_id]`.
  For the partner's species make a second copy `dim_partner` related to `species_b_id` (role-playing dimension).

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
Pair %  = MAX ( pokemon_partner_stats[share_of_a] )            -- share of A's teams that also have B
```

Visual-level filters used everywhere: `[Teams] >= 100` (hide tiny samples), and on the monthly visuals
`regulation_monthly_totals[tail] = FALSE` (months far below the busiest one are a different population).

## 3. Pages

1. **Overview.** Cards: battles, player-battles, regulations covered, date range. Area chart of battles per month by regulation
   (tail months excluded). Bar chart of player-battles per rating band. Slicers: regulation, rating band.
2. **Meta.** Top-N species by `Usage %` (N from a what-if parameter), a scatter of `Usage %` against `Win %` (bubble size `Teams`),
   and a table with usage, win, interval, sent-out and lead rates. Conditional format `Win vs Band (pp)`.
3. **Pokémon detail** (drill-through from any species). Monthly usage line, win rate with its interval, sent-out and lead rates,
   Tera rate and a bar of Tera types, top partners (share, lift, `Win vs Band`), and for the nine masked families a stacked bar by
   `form_basis` (`observed` / `unobserved`), so the unknown share is visible.
4. **Teammates.** A heat map of lift for the 20 most used species (matrix, species A × species B), with a size filter on `teams_both`.
5. **Method and data notes.** Scope (VGC only, completed battles), the population numbers, and the caveats from
   `METRICS.md`: upload month, tail months, Illusion, form-masked species, Tera win rates not comparable, lift is not synergy.

## 4. Build order

1. Import the dimensions and facts, set the relationships, hide the key columns.
2. Create the measures above and check three numbers against the CLI output: Reg I 2025 Calyrex usage 48.8%, the sum of monthly
   battles of Reg F 2026 equal to 502,121, and Incineroar's partner share with Urshifu 55.2% (Reg F 2026).
3. Pages 1 and 2, then 3, then 4, then 5.
4. Export screenshots and a PDF for the README; commit the `.pbix` only if it stays small (it holds aggregates only, no replay logs).

## 5. Pitfalls to design against

- A rating band with few battles produces wide intervals: show the interval, not just the point value.
- Champions Reg M-A has no Tera, so its Tera rate is zero by construction, not by choice.
- A rate shown for one species without `Teams` next to it breaks the project's own rule.
- Percentages in a tooltip must use the same denominator as the visual.