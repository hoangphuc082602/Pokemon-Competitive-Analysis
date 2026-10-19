# EDA insights

Hand-written reading of [`EDA_FINDINGS.md`](EDA_FINDINGS.md), which is generated from the aggregate tables. Population for every
number: completed VGC battles of the regulation shown, public Showdown replays uploaded between 2023-12 and 2026-05, regulations with at
least 50,000 player-battles (see [`METRICS.md`](../METRICS.md)). Each finding separates what was **counted** (fact), what it
**suggests** (interpretation) and what is only a **hypothesis** with the check that would test it. Nothing here is causal.

## 1. The meta is concentrated, but not collapsed

**Fact.** In the eight large regulations the most used species appears on 37.0% (Reg H 2025, Incineroar) to 48.8% (Reg I 2025, Calyrex)
of teams. Between 25 and 31 species exceed 5% usage in every regulation. `effective_species` ranges from 34.9 (Reg F 2026, the most
concentrated: highest top-5 mean, 35.7%) to 48.7 (Reg J 2025, the most diverse). Calyrex is the top species in three regulations
(I 2025, J 2025, I 2026), Incineroar in two (G 2024, H 2025).

**Interpretation.** A regulation is never dominated by one or two species, yet a handful of species (about 5) sit on a third of all teams.

**Hypothesis.** Regulations that allow restricted legendaries concentrate usage on the strongest few (Calyrex 48.8% in Reg I 2025).
Check: split species into restricted / not restricted and compare the share of team slots they take per regulation.

## 2. The ranking settles quickly

**Fact.** The mean rank correlation of species usage between consecutive months is 0.889 (Reg F 2024) to 0.973 (Reg J 2025), and at least
0.919 for every 2025-2026 regulation. Reg F 2024 has the lowest single transition (0.811). Champions Reg M-A has only two usable months,
so its 0.921 rests on one transition.

**Interpretation.** After the first regulations the month-to-month order of the top 30 species barely changes.

**Hypothesis.** The earlier regulations are less stable because their first months are volatile, or because the dataset is smaller in those
months. Check: recompute the correlation on equal-sized random samples of each month, which removes the sample-size explanation.

## 3. Strong players pick differently (Reg F 2026)

**Fact.** Between players below 1200 and players rated 1500+, usage of Urshifu rises from 40.0% to 50.0% (+9.9 pp), Flutter Mane +8.3,
Ogerpon +7.9, Tornadus +6.6. Dondozo goes from 3.9% to 10.4% and Tatsugiri from 2.9% to 9.5% (2.7 and 3.3 times as common). Incineroar falls
from 39.2% to 30.9% (-8.2 pp) and Rillaboom from 21.6% to 17.8% (-3.8 pp).

**Interpretation.** At high rating the most used species are used even more, and the Dondozo and Tatsugiri pair (which also has a lift of
19.1 in section 6) is adopted far more often. Incineroar, the most common species overall, is the one that high-rated players use less.

**Hypothesis.** Strategies that need coordination between two Pokémon are chosen more often by strong players; generalist support
species are chosen more by weaker ones. Check: compute pair shares per rating band (the partner table already has the bands). A caution:
players who publish replays are a self-selected group, so this describes who uploads, not all players.

## 4. Popularity correlates with win rate in every rating band; rating does not explain it

**Fact.** Over all players and the species with at least 2,000 teams, the rank correlation between usage and win rate minus the baseline is 0.48 to 0.65 in the seven Scarlet/Violet regulations. Inside rating bands, on the species with at least 2,000 teams below 1200 (95-140 species), the unweighted mean over six regulations is 0.54 below 1200, 0.49 at 1200-1399, 0.42 at 1400-1499 and 0.43 at 1500+, and every cell is positive (0.28 to 0.71). On the narrower set of species with at least 500 teams at 1500+ (52-107 species) the same means are 0.32, 0.15, 0.02 and 0.24. Champions Reg M-A is about 0 on the wider set (0.08 overall) and 0.2 on the narrow one.

**Interpretation.** Usage and win rate move together at every rating, and the drop from the weakest to the strongest band (about 0.1) is within noise, so rating does not explain the link. Its size depends on the species counted: most of it comes from rarely used species winning less, and among the most used species it is weaker (about 0.2 to 0.3). This is correlation, not cause.

**Hypothesis.** Rarely used species may win less because they are weaker or less well played; the data cannot separate the two. Champions Reg M-A (new game, 85k battles) may differ because its meta has not settled. Reg I 2026 turns negative on a 27-species set only, which is too small to read.

## 5. About one in five sent-out Pokémon Terastallizes, and the type is only partly predictable

**Fact.** Terastallizations per sent-out appearance are 19.6% to 21.4% in every regulation with Tera. For species with at least 5,000
Terastallizations, the most used Tera type takes a median of 48.0% to 61.0% of the species' Terastallizations, and between 46.2% and 69.6% of
those species have a type used in at least half of the cases. The number of species analysed varies from 8 (Reg I 2026) to 35 (Reg F 2026).

**Interpretation.** With about 3.74 Pokémon sent out per team (measured in the usage table), 0.20 to 0.21 Terastallizations per sent-out
appearance means roughly 0.73 to 0.80 per team: close to three in four players Terastallize in a game (a derived estimate). For a typical
species the most used Tera type is the choice in about half of the cases.

**Caution.** The predictability figure depends on how many species pass the 5,000 threshold, so regulations with 8 or 13 species
(Reg I 2026, Reg J 2025) are not directly comparable with those with 28 or 35.

## 6. The teammates seen together most are known archetypes

**Fact.** In Reg F 2026 the highest lifts among pairs on at least 5,000 teams are Tyranitar and Excadrill (33.2), Weezing and Regigigas
(29.1), Dondozo and Tatsugiri (19.1, on 39,628 teams), Gallade and Hatterene (14.8), Ninetales and Articuno (14.6), Pelipper and Archaludon
(11.2), Torkoal and Lilligant (9.6).

**Interpretation.** Several of these match well-known interactions (a sand setter and a sand abuser, a rain setter and its partner, a Commander
pair, a sun setter and a sun abuser). This is domain knowledge and was not checked against the data; it supports reading lift as co-occurrence
that reflects team archetypes.

**Caution.** Lift says two species are seen together more often than chance. It does not say the pair wins more; that is the separate
`win_rate_delta` of the pair in the partner table.

## 7. Team-level counters are weak

**Fact.** For species pairs with at least 2,000 battles, the observed win rate differs from what the two teams' overall strength predicts
by a median of 0.56 to 0.81 percentage points (95th percentile 1.9 to 3.0 pp). The share of pairs with |z| above 4 is 0.0% to 5.5%
(largest in Reg F 2026, which also has more pairs).

**Interpretation.** Knowing that an opposing team contains a given species adds little beyond how strong the two teams are generally.

**Hypothesis.** The share of pairs beyond |z| of 4 is far above the 0.006% expected from pure sampling noise, but battles are not independent
(the same players repeat, and the games of a best-of-three set are correlated), which inflates z. Check: recompute with player-level clustering,
or keep one battle per player pair. Until then the effect sizes (a few pp) are the number to trust, not the z-scores.

## Data and report notes

- Reg D 2023 has only 2,534 player-battles (late uploads of an older regulation) and is left out of every comparison; the report now
  excludes regulations below 50,000 player-battles automatically.
- Regulations were listed by first upload month, which put Reg D after Reg F 2024; they are now ordered by busiest month.
- Champions Reg M-A has two usable months and no Tera, so its rows in sections 2, 4 and 5 are thin or absent by construction.
- Numbers are over public ladder replays, not tournament play; usage and win rates are for teams, not for Pokémon on the field.