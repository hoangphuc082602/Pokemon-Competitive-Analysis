# Metric definitions

Every number reported by this project states its **population, regulation, rating filter and sample size**.
A metric without them is incomplete. Definitions below are the contract for the aggregate tables and dashboards.

## 1. Scope

| Item | Definition |
|---|---|
| Source | Public Pokémon Showdown replays (battle behaviour only; game mechanics come from PokéAPI) |
| In scope | `battle.format_id` starting with `gen9vgc` or `gen9championsvgc`: **2,554,327 battles (70.1%)** of the 3,642,499 crawled |
| Out of scope | `gen9doublesou`, `gen9nationaldexdoubles`, `gen92v2doubles` (about 1.09M battles, kept in the database but excluded from VGC statistics) |
| Regulation | `format_id` with the `(bo3)` / `bo3` suffix removed, e.g. `gen9vgc2024regg` |
| Bo3 | `is_bo3 = 1` when the format id contains `bo3`. Games of one set share players and teams, so they are **not independent** |
| Completed battle | `turn_count >= 1` and exactly one `WIN` and one `LOSS` in `battle_players.result` (190 rows are NULL) |
| Unit | one **player-battle** = one row of `battle_players` (a player's side in one battle) |

The scope is materialised as table `vgc_battles` (`migrations/002_vgc_battles.sql`); every VGC metric joins it.

## 2. Species identity

- Form-level identity comes from `showdown_pokemon_map` (`form_status = 'known'`).
- Nine families are masked at team preview (`Urshifu-*`, `Zacian-*`, ...): they map to a species only
  (`form_status = 'masked'`, `poke_id` NULL). `battle_team_slot.species_observed` holds the real form when the
  Pokémon entered the field (`form_status = 'observed'`); otherwise it is `unobserved`.
- Rule: report these families **at species level**, or state the share of `unobserved` slots next to any form-level number.
- Forms differ mechanically (Urshifu: type and moves; Ogerpon: type and ability; Zygarde: stats; Zacian / Zamazenta Crowned).
  They are **never merged silently**: a form missing from the master data maps to species only (`form_status = 'unlisted'`,
  e.g. `Ogerpon-Wellspring-Tera`, `Arceus-Fire`). Form-level statistics for masked families use the **sent-out population** only.
- Plain `Zygarde` is the 50% form; Aura Break and Power Construct versions differ only by ability (see `battle_ability`).

## 3. Metrics

| Metric | Numerator | Denominator |
|---|---|---|
| Team usage | player-battles whose team contains the species | completed player-battles in the regulation |
| Sent-out rate | team appearances with `was_sent_out = 1` | team appearances of the species |
| Lead rate | team appearances with `is_lead = 1` | team appearances of the species |
| Win rate (team) | wins among player-battles whose team contains the species | completed player-battles whose team contains it |
| Win rate (sent out) | wins among player-battles where it was sent out | player-battles where it was sent out |
| Tera usage | `battle_tera` events for the species | team appearances where it was sent out |
| Partner frequency | player-battles with both species on the team | player-battles with the first species |
| Partner lift | P(A and B) / (P(A) x P(B)) | player-battles in the regulation |

Notes:
- `was_sent_out` means "entered the field at least once". A Pokémon brought but never sent out counts as not sent out,
  so sent-out rates are a lower bound of the real bring rate.
- Win-rate and usage figures are reported with `n` and a 95% Wilson interval; hide rows with `n < 100` player-battles.
- Correlation is not causation: a high win rate for a species with a strong partner is not evidence the species is strong.

## 4. Rating filter

- `battle_players.rating_before` is the player's ladder rating before the battle. It is NULL for part of the data;
  rating-filtered metrics exclude NULL and must report the excluded share.
- `battle.rating` is a battle-level value copied from the crawl when the log has none; its exact meaning is not yet confirmed.

## 5. Known limitations

- Public replays are a self-selected sample of ladder games, not tournament play.
- Arceus type forms and battle-only forms such as `Ogerpon-*-Tera` are not in the master data and are species-only (`unlisted`).
- Per-player statistics need a deduplicated players table, which does not exist yet (`players` has one row per player-battle).
- Damage and KO attribution (`battle_damage`, `battle_ko`) is heuristic; species columns identify forms but not the attacker with certainty.