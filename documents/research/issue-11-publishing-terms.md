# Publishing Showdown / PokéAPI-derived aggregates: terms check (issue #11)

Research note for [#11](https://github.com/hoangphuc082602/Pokemon-Competitive-Analysis/issues/11) (parent: [#9](https://github.com/hoangphuc082602/Pokemon-Competitive-Analysis/issues/9), "Open risk (UNKNOWN)" in *Further Notes*). Checked 2026-11-23 against primary sources only (operator websites, upstream source code and licence files, this repo's code). Labels follow `AGENTS.md`: **CONFIRMED** (read in the source), **INFERRED** (reasoned from confirmed facts), **UNKNOWN**. This is not legal advice.

## Verdict

| Source | Verdict | Short reason |
|---|---|---|
| Pokémon Showdown replays → aggregates | **Allowed with conditions** (no explicit grant: the formal answer is *unclear*, see Q1) | No published terms restrict reuse; the replay API is publicly documented for programmatic use; only public replays are returned; the export already drops personal data. |
| PokéAPI data → aggregates and calculator master data | **Allowed with conditions** | Free and open; fair-use policy asks for caching; repository data is BSD-3-Clause, so keep the copyright notice when redistributing. |
| Pokémon names (Nintendo / Creatures / GAME FREAK trademarks) | **Allowed with conditions** (INFERRED) | Keep the existing non-affiliation disclaimer; ship no official artwork or sprites. |

## Questions from the issue

1. Q1: Do Showdown's terms or replay policy allow publishing aggregates derived from public replays, and under which conditions?
2. Q2: Do PokéAPI's fair-use policy and licence allow it, and under which conditions?
3. Q3: What credit text goes in the site footer and the README?
4. Q4: Does any condition change the export, for example extra fields to drop?

## Q1: Pokémon Showdown

### Findings

- **No terms of service exist covering replay or data reuse.** CONFIRMED: the site footer links only Rules, Credits, Privacy and Contact ([credits][ps-credits]); `/terms` returns HTTP 404 ([ps-terms]). The Rules page covers conduct, usernames and pirated material. It says nothing about replays, scraping, bots or data reuse ([ps-rules]). The Privacy page covers cookies, IP use for bans, analytics/ads and chat logging. It sets no terms on replay reuse ([ps-privacy]).
- **The replay API is documented for programmatic use.** CONFIRMED: `WEB-API.md` in the official client repo says "Most PS APIs that you would want to access programmatically are available by adding `.json` to the URL" and that they send `Access-Control-Allow-Origin: *` ([web-api] L4–6). It documents `/<id>.json`, `/<id>.log` and `search.json` with `format=` and `before=` pagination ([web-api] L12–56). This is the same pattern as `python/crawl_data/data_vgc.py:195-198` and `:217-218`.
- **One informal limit:** "Obviously don't _scrape_ it". In context this refers to the HTML replay page source, and the JSON endpoints are offered instead ([web-api] L24). CONFIRMED wording; INFERRED reading. It concerns how data is collected, not whether aggregates may be published.
- **Only public replays are reachable this way.** CONFIRMED: the public search and fetch queries filter `WHERE private = 0` ([replays-ts] L232–250). Private-replay search needs a login as the searched user or a sysop ([actions-ts] L1090–1124). Uploaders can mark a replay hidden or private at upload time ([actions-ts] L326–338). Staff can change a replay's privacy afterwards ([actions-ts] L1126–1146). INFERRED: every replay in the dataset was public when crawled. Some may have been made private since. An aggregate does not reveal any single replay, but a replay id or username would.
- **Replays carry usernames.** CONFIRMED: uploads store a `players` list ([actions-ts] L328–333) and search filters by `playerid` ([replays-ts] L176–197). This is personal-ish data that must not be republished. The privacy policy states no rule either way ([ps-privacy]).
- **Software licences do not cover the data.** CONFIRMED: the server is MIT, "Copyright (c) 2011-2026 Guangcong Luo and other contributors" ([ps-server-license]). The client, including the replay API code, is AGPLv3. Its README says "This is NOT the same license as Pokémon Showdown's server" and gives `staff@pokemonshowdown.com` for licensing questions ([ps-client-readme], [ps-client-license]). Neither licence mentions replay logs or derived statistics. INFERRED: this project redistributes no Showdown code, so neither licence imposes obligations. UNKNOWN: the legal status of the replay logs themselves.
- **Ownership for credit.** CONFIRMED: the Credits page lists Guangcong Luo [Zarel] (development, design, sysadmin) and Smogon University (sponsorship) ([ps-credits]).
- **Ecosystem precedent.** CONFIRMED: Smogon publishes monthly folders of battle statistics (`/stats/2014-11/` … `/stats/2026-10/`) ([smogon-stats]). INFERRED: public usage aggregates are an accepted practice in the Showdown/Smogon ecosystem. This is precedent, not permission.

### Assessment for Q1

INFERRED: publishing **aggregates** (species-level counts and rates with n ≥ 100) is low risk. No published term forbids it, the operator documents the API for programmatic use, and the output holds no usernames, replay ids or per-battle rows. The formal status is **unclear**, because no source grants permission explicitly. Optional mitigation: one email to `staff@pokemonshowdown.com` (the only contact published in a primary source ([ps-client-readme])) describing the aggregate-only site. A reply would turn the UNKNOWN into USER-REPORTED.

## Q2: PokéAPI

### Findings

- **Free and open use, with a fair-use policy.** CONFIRMED: "PokéAPI is free and open to use." Developers must follow the fair use policy, and non-compliance can lead to a permanent IP ban. Rules: "Locally cache resources whenever you request them", be nice, report vulnerabilities responsibly. Rate limiting was removed, but users are asked to limit request frequency ([pokeapi-docs], *Fair Use Policy*).
- **The policy concerns API access, not republishing derived data.** CONFIRMED: the docs and About pages state no attribution or reuse terms beyond fair use ([pokeapi-docs], [pokeapi-about]).
- **Licence: BSD-3-Clause.** CONFIRMED: both the API repo ([pokeapi-license]) and the static data repo `PokeAPI/api-data` ([pokeapi-apidata-license]) are BSD-3-Clause. GitHub's licence API reports `BSD-3-Clause` for both. Notice: "Copyright (c) © 2013–2023 Paul Hallett and PokéAPI contributors". Conditions: redistributions keep or reproduce the notice and disclaimer, and the PokéAPI name may not be used to endorse or promote derived products ([pokeapi-license]). INFERRED: the calculator master data (base stats, types, abilities, learnsets, moves, natures, type chart) planned in #9 is a redistribution of PokéAPI data. Ship the BSD notice with it and do not imply endorsement.
- **Data origin and trademarks.** CONFIRMED: PokéAPI says its data comes mainly from Veekun's open-source CSV data, with Gen 8 data from other sources, and that "Pokémon and Pokémon character names are trademarks of Nintendo" ([pokeapi-about]).
- **Repo compliance with fair use.** CONFIRMED: the crawlers sleep between requests (e.g. `python/crawl_data/data_move.py:57`, `data_type.py:29`) and write each entity to `data/raw/<name>.csv` (`docs/ai-onboarding/08-DATA-SOURCES.md`, table row "PokéAPI"), which is local caching. The site will read the exported snapshot and never call PokéAPI at runtime (#9 *Implementation Decisions*, ADR-013). INFERRED: compliant.

## Q3: Credit text

Current state (CONFIRMED): the site footer (`web/index.html:60-63`) credits "Pokémon Showdown replays and PokéAPI" and says "Fan project, not affiliated with Nintendo, Game Freak or The Pokémon Company." The README has a *Data sources and acknowledgements* section (`README.md:315-322`) with a trademark line. Neither mentions the PokéAPI licence, the absence of personal data, or the snapshot date.

### Proposed site footer

```html
<p>Data: aggregate statistics computed from public
<a href="https://replay.pokemonshowdown.com/">Pokémon Showdown</a> replays
(snapshot <span data-snapshot>2026-10-14</span>) and game data from
<a href="https://pokeapi.co/">PokéAPI</a> (BSD-3-Clause, © Paul Hallett and PokéAPI contributors).
No usernames, replay ids or individual battles are published.</p>
<p>Non-commercial fan project. Not affiliated with or endorsed by Pokémon Showdown, Smogon, PokéAPI,
Nintendo, Creatures Inc., GAME FREAK inc. or The Pokémon Company.
Pokémon and Pokémon character names are trademarks of Nintendo.</p>
```

The snapshot date can be filled from `manifest.json` → `snapshot_date` (CONFIRMED field, `web/public/data/manifest.json`).

### Proposed README section (replaces `README.md:315-322`)

```markdown
## Data sources and acknowledgements

- [Pokémon Showdown](https://pokemonshowdown.com/) (created by Guangcong Luo and contributors, sponsored by Smogon University) – public battle replays, fetched through the documented replay API. The web app publishes only species-level aggregates with n ≥ 100: no usernames, replay ids or per-battle data.
- [PokéAPI](https://pokeapi.co/) – canonical Pokémon / move / ability / item data, cached locally per the PokéAPI fair use policy. PokéAPI data is BSD-3-Clause, Copyright (c) 2013–2023 Paul Hallett and PokéAPI contributors; the notice ships with the exported data.
- The replay scraper follows the log-scraping approach of [VGC-Bench](https://github.com/cameronangliss/vgc-bench) (MIT) and uses [poke-env](https://github.com/hsahovic/poke-env).
- Word2Vec via [Gensim](https://radimrehurek.com/gensim/).

Pokémon and Pokémon character names are trademarks of Nintendo, Creatures Inc. and GAME FREAK inc. This is a non-commercial educational project and is not affiliated with or endorsed by them, by Pokémon Showdown / Smogon, or by PokéAPI.
```

## Q4: Conditions that change the export

Already enforced (CONFIRMED): `python/analytics/export_web.py:36` defines `FORBIDDEN = re.compile(r"user|replay|battle_id|player_side|^side$|^p[12]_|rating_before|nickname|pokemon_name", re.I)`. Any match raises `ExportError` (`:45-47`). Output keys are an allow-list (`:33-34`, `:130`), and rows with n < 100 are dropped (`:13`, `MIN_N = 100` at `:30`). The current snapshot ships only species-level rows (sample: `web/public/data/team_usage/gen9vgc2023regd__all.json`).

Changes needed:

1. **Add a PokéAPI licence notice to the export** (new): when the calculator master data is exported (#9), write the BSD-3-Clause notice next to it (e.g. `web/public/data/master/LICENSE-POKEAPI.txt`) and list it in the manifest. Basis: [pokeapi-license]. INFERRED requirement.
2. **Apply the same forbidden-column check to every new dataset** (partner, matchup, trend, Tera, master data), not only `team_usage`. No new fields to drop: the current pattern already covers usernames, replay/battle ids, side, nickname and per-player rating. INFERRED from Q1.
3. **Do not include replay ids, replay URLs or usernames in hand-written content**: Insights text, chart annotations, screenshots, README examples. A replay could have become private after the crawl ([actions-ts] L1126–1146), and usernames are personal data. The export guard does not check prose, so this is a review rule.
4. **No sprites or official artwork** from Showdown or PokéAPI in v1.0. No licence is stated for Showdown's `/sprites/` ([ps-client-readme]), and PokéAPI's licence and trademark notice do not license Nintendo artwork ([pokeapi-license], [pokeapi-about]). Text names only. INFERRED.
5. **Keep n ≥ 100** as both a statistical and a privacy rule: small cells (e.g. Reg D, 1,267 battles; manifest) narrow aggregates toward individual players. INFERRED.

Not an export change, but recorded for the v1.2 crawl job: `data_vgc.py` fetches with up to `--num_workers` threads (`:84-85`), with no delay or User-Agent between requests (`:196-198`, `:218`). Neither PokéAPI's fair-use spirit nor Showdown's docs set numbers, but a delay and a descriptive User-Agent are prudent. INFERRED. The v1.0 data freeze means no crawl happens now (#9).

## Open questions and unknowns

- **UNKNOWN:** whether the Showdown operators consider replay logs, or statistics derived from them, subject to any restriction. No primary source addresses it. Resolve by emailing `staff@pokemonshowdown.com` if certainty is wanted (user decision).
- **UNKNOWN:** whether a replay owner or staff can request removal of derived aggregates. INFERRED to be moot, since aggregates contain no per-replay data.
- **UNKNOWN:** the copyright status of game data (stats, move data) owned by Nintendo/GAME FREAK, beyond PokéAPI's BSD licence on its compilation. Mitigated by the non-commercial disclaimer, not resolved.
- **Repo licence (side finding, CONFIRMED):** the repository has no `LICENSE` file (`git ls-files` shows none outside `.pnpm-store`). `data_vgc.py` states it is the "Battle log scraping module for VGC-Bench" (`:1-7`), and VGC-Bench is MIT (GitHub licence API, [vgc-bench]). INFERRED: if the file is copied code, the MIT notice must be kept. The user should choose a repo licence.
- **Side finding (CONFIRMED):** 3,911 files under `.pnpm-store/` are tracked by git. This is unrelated to #11 but worth a cleanup issue.

## Sources

Primary, external:

- [ps-rules]: https://pokemonshowdown.com/rules
- [ps-privacy]: https://pokemonshowdown.com/privacy
- [ps-credits]: https://pokemonshowdown.com/credits
- [ps-terms]: https://pokemonshowdown.com/terms (HTTP 404, 2026-11-23)
- [web-api]: https://github.com/smogon/pokemon-showdown-client/blob/36ba1106bbb0e95b457e29a07b5f9e9db29ac85a/WEB-API.md
- [replays-ts]: https://github.com/smogon/pokemon-showdown-client/blob/36ba1106bbb0e95b457e29a07b5f9e9db29ac85a/api/src/replays.ts
- [actions-ts]: https://github.com/smogon/pokemon-showdown-client/blob/36ba1106bbb0e95b457e29a07b5f9e9db29ac85a/api/src/actions.ts
- [ps-client-readme]: https://github.com/smogon/pokemon-showdown-client/blob/master/README.md
- [ps-client-license]: https://github.com/smogon/pokemon-showdown-client/blob/master/LICENSE (AGPL-3.0)
- [ps-server-license]: https://github.com/smogon/pokemon-showdown/blob/master/LICENSE (MIT)
- [smogon-stats]: https://www.smogon.com/stats/
- [pokeapi-docs]: https://pokeapi.co/docs/v2 (*Information*, *Fair Use Policy*)
- [pokeapi-about]: https://pokeapi.co/about
- [pokeapi-license]: https://github.com/PokeAPI/pokeapi/blob/master/LICENSE.md (BSD-3-Clause)
- [pokeapi-apidata-license]: https://github.com/PokeAPI/api-data/blob/master/LICENSE.txt (BSD-3-Clause)
- [vgc-bench]: https://github.com/cameronangliss/vgc-bench (MIT, per GitHub licence API)

Repository (branch `sprint-5/web-data`, HEAD `962012e`):

- `python/analytics/export_web.py:13,30,33-36,45-47,130`
- `python/crawl_data/data_vgc.py:1-7,84-85,195-198,217-218`
- `python/crawl_data/data_move.py:57`, `python/crawl_data/data_type.py:29`
- `web/index.html:60-63`, `README.md:315-322`
- `web/public/data/manifest.json`, `web/public/data/team_usage/gen9vgc2023regd__all.json`
- `docs/ai-onboarding/08-DATA-SOURCES.md` (PokéAPI row)
- Issues #9 and #11 (read via `gh issue view`, 2026-11-23)

[ps-rules]: https://pokemonshowdown.com/rules
[ps-privacy]: https://pokemonshowdown.com/privacy
[ps-credits]: https://pokemonshowdown.com/credits
[ps-terms]: https://pokemonshowdown.com/terms
[web-api]: https://github.com/smogon/pokemon-showdown-client/blob/36ba1106bbb0e95b457e29a07b5f9e9db29ac85a/WEB-API.md
[replays-ts]: https://github.com/smogon/pokemon-showdown-client/blob/36ba1106bbb0e95b457e29a07b5f9e9db29ac85a/api/src/replays.ts
[actions-ts]: https://github.com/smogon/pokemon-showdown-client/blob/36ba1106bbb0e95b457e29a07b5f9e9db29ac85a/api/src/actions.ts
[ps-client-readme]: https://github.com/smogon/pokemon-showdown-client/blob/master/README.md
[ps-client-license]: https://github.com/smogon/pokemon-showdown-client/blob/master/LICENSE
[ps-server-license]: https://github.com/smogon/pokemon-showdown/blob/master/LICENSE
[smogon-stats]: https://www.smogon.com/stats/
[pokeapi-docs]: https://pokeapi.co/docs/v2
[pokeapi-about]: https://pokeapi.co/about
[pokeapi-license]: https://github.com/PokeAPI/pokeapi/blob/master/LICENSE.md
[pokeapi-apidata-license]: https://github.com/PokeAPI/api-data/blob/master/LICENSE.txt
[vgc-bench]: https://github.com/cameronangliss/vgc-bench
