"""Master data for the browser damage calculator (#16, ADR-014), limited to the species dimension of the web export.

    python -m python.analytics.calc_master --master data/raw --data web/public/data \
        --out web/public/data/calc_master.json

Run after export_web: it reads species_forms.json, manifest.json and team_usage/<regulation>__all.json from --data.
Writes one JSON file (schema 3, #37):
    regulations every manifest regulation, newest first (season year, then regulation letter; the first is the page
                default): id, label, its game (`version_group`, python/analytics/regulation_sources.py; an unmapped
                regulation fails the export) and the poke_ids of the exported forms seen in its team usage
    forms       every form of species_forms.json that has typing and base stats: its own types and base stats, its
                abilities, and per version group of the regulations its damaging-move learnset (any learn method)
    moves       only the moves in those learnsets that have a base power and a physical / special damage class
    natures     name, increased / decreased stat (null for neutral natures)
    type_chart  [attack_type, defense_type, multiplier] for every pair that is not 1x
    items       (team builder #17) the items a Pokémon can usefully hold in battle, by name: PokéAPI categories
                HELD_CATEGORIES plus every berry (category "berries"), except baking / catching berries.
                Which items a regulation allows is not modelled.
Mechanics only (PokéAPI, BR-16): nothing from Showdown, except which exported forms a regulation lists (its
team usage, already in the web export) — that scopes the page's Pokémon list and never changes a mechanic. Learnsets come from the crawl of each version group
(data_poke_move --version-group, one CSV per group; a missing CSV fails the export). A learnset is the first of: the
form's rows in that game, its species' default form's (poke_id = species_id) rows in that game, then the same in the
other games of VERSION_GROUPS; `{"moves", "version_group", "poke_id"}` names where it came from (both null when no
game has one), so the page can say so (BR-05). Rows that hold only status moves still count as a learnset.
Abilities are not split per game in PokéAPI (regulation_sources.py): a form without ability rows gets its default
form's, and `abilities_from` names that poke_id. Typing and base stats are never borrowed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from python.analytics.dim_tables import parse_regulation
from python.analytics.export_web import FORBIDDEN
from python.analytics.regulation_sources import VERSION_GROUPS, learnset_name, version_group
from python.calculations.nature_calc import STAT_MAPPING

SCHEMA_VERSION = 3   # 3: learnsets per version group + regulations (#37); 2: items (#17)
STATS = ["hp", "atk", "def", "spatk", "spdef", "spe"]
FILES = ("stats_raw.csv", "data_type.csv", "type_effectiveness.csv", "ability_raw.csv", "pokemon_ability.csv",
         "data_damage_class.csv", "move_raw.csv", "pokemon_nature_info.csv", "item_raw.csv")
DAMAGING = ("physical", "special")
HELD_CATEGORIES = ("held-items", "choice", "type-enhancement", "type-protection", "in-a-pinch", "picky-healing",
                   "bad-held-items", "species-specific", "plates", "mega-stones")
NOT_HELD_BERRIES = ("baking-only", "catching-bonus")


class CalcMasterError(RuntimeError):
    """The master data is missing a file / column or holds a forbidden column."""


def _read(master: Path, name: str) -> pd.DataFrame:
    path = Path(master) / name
    if not path.exists():
        raise CalcMasterError(f"{path} not found")
    df = pd.read_csv(path)              # master tables: at most ~46k rows (pokemon_moves), not event data
    bad = [c for c in df.columns if FORBIDDEN.search(str(c))]
    if bad:
        raise CalcMasterError(f"{name} holds forbidden column(s) {bad}")
    return df


def _stat(v) -> str | None:
    return None if pd.isna(v) else STAT_MAPPING[int(v)]


def _newest_first(regulation: dict) -> tuple:
    _, year, letter, _ = parse_regulation(regulation["id"])
    return (-(year or 0), tuple(-ord(c) for c in letter), regulation["id"])


def _learnsets(master: Path, damaging: dict) -> dict[str, tuple[set[int], dict[int, set[int]]]]:
    """Per version group: (poke_ids with any learnset row, poke_id -> damaging move ids)."""
    out = {}
    for group in VERSION_GROUPS:
        pm = _read(master, f"{learnset_name(group)}.csv")
        damaging_of: dict[int, set[int]] = {}
        for pid, mid in zip(pm["pokemon_id"].astype("int64"), pm["move_id"].astype("int64")):
            if int(mid) in damaging:
                damaging_of.setdefault(int(pid), set()).add(int(mid))
        out[group] = (set(pm["pokemon_id"].astype("int64").tolist()), damaging_of)
    return out


def _learnset(learnsets: dict, group: str, pid: int, default: int) -> dict:
    """The first learnset found for `pid` in `group` (see the module docstring), with its source."""
    for g in (group, *(x for x in VERSION_GROUPS if x != group)):
        has_rows, damaging_of = learnsets[g]
        for source in dict.fromkeys((pid, default)):
            if source in has_rows:
                return {"moves": sorted(damaging_of.get(source, ())), "version_group": g, "poke_id": source}
    return {"moves": [], "version_group": None, "poke_id": None}


def build(master: Path, forms: list[dict], regulations: list[dict]) -> dict:
    """Calculator master data for `forms` (species_forms.json records) and `regulations` ({id, label, poke_ids}:
    the manifest regulations with the poke_ids of their team usage). See the module docstring."""
    groups_used = {r["id"]: version_group(r["id"]) for r in regulations}     # an unmapped regulation fails here
    t = {name: _read(master, name) for name in FILES}
    types = dict(zip(t["data_type.csv"]["type_id"].astype("int64"), t["data_type.csv"]["type"].astype(str)))
    classes = dict(zip(t["data_damage_class.csv"]["damage_class_id"].astype("int64"),
                       t["data_damage_class.csv"]["damage_class"].astype(str)))
    species_of = dict(zip(t["stats_raw.csv"]["poke_id"].astype("int64"), t["stats_raw.csv"]["species_id"].astype("int64")))

    ability_names = dict(zip(t["ability_raw.csv"]["ability_id"].astype("int64"), t["ability_raw.csv"]["ability_name"].astype(str)))
    pa = t["pokemon_ability.csv"]
    abilities: dict[int, list[str]] = {}
    for pid, aid in zip(pa["pokemon_id"].astype("int64"), pa["abi_id"].astype("int64")):
        name = ability_names.get(int(aid))
        if name is None:
            raise CalcMasterError(f"pokemon_ability.csv: ability id {aid} missing from ability_raw.csv")
        if name not in abilities.setdefault(int(pid), []):
            abilities[int(pid)].append(name)

    mv = t["move_raw.csv"]
    mv = mv[mv["power"].notna() & mv["damage_class_id"].map(classes).isin(DAMAGING)]
    damaging = {int(r.move_id): {"id": int(r.move_id), "name": str(r.move_name), "type": types[int(r.type_id)],
                                 "power": int(r.power), "damage_class": classes[int(r.damage_class_id)]}
                for r in mv.itertuples(index=False)}
    learnsets = _learnsets(master, damaging)
    games = [g for g in VERSION_GROUPS if g in groups_used.values()]

    out_forms, skipped = [], []
    for f in sorted(forms, key=lambda f: (f["species"], f["form"])):
        pid = int(f["poke_id"])
        if f.get("type_1") is None or any(f.get(s) is None for s in STATS):
            skipped.append(f["form"])
            continue
        default = species_of.get(pid, pid)
        own_abilities = pid in abilities
        out_forms.append({"poke_id": pid, "species": f["species"], "form": f["form"],
                          "types": [x for x in (f["type_1"], f.get("type_2")) if x],
                          "base_stats": {s: int(f[s]) for s in STATS},
                          "abilities": abilities.get(pid if own_abilities else default, []),
                          "abilities_from": None if own_abilities or default == pid else default,
                          "learnsets": {g: _learnset(learnsets, g, pid, default) for g in games}})
    exported = {f["poke_id"] for f in out_forms}
    regs = [{"id": r["id"], "label": r["label"], "version_group": groups_used[r["id"]],
             "forms": sorted({int(p) for p in r["poke_ids"]} & exported)}
            for r in sorted(regulations, key=_newest_first)]
    used = sorted({m for f in out_forms for ls in f["learnsets"].values() for m in ls["moves"]})
    natures = [{"name": str(r.nature_name), "increased": _stat(r.increased_stat), "decreased": _stat(r.decreased_stat)}
               for r in t["pokemon_nature_info.csv"].itertuples(index=False)]
    te = t["type_effectiveness.csv"]
    chart = [[types[int(a)], types[int(d)], float(m)]
             for a, d, m in zip(te["attack_type_id"], te["defense_type_id"], te["multiplier"]) if float(m) != 1.0]
    items = _held_items(t["item_raw.csv"])
    return {"schema_version": SCHEMA_VERSION, "level": 50, "regulations": regs, "forms": out_forms, "skipped": skipped,
            "moves": [damaging[m] for m in used], "natures": natures, "type_chart": chart, "items": items}


def _held_items(it: pd.DataFrame) -> list[dict]:
    """Holdable battle items, one row per name (the crawl repeats some names), sorted by name; berries grouped."""
    name, cat = it["item_name"].astype(str), it["category"].astype(str)
    berry = name.str.endswith("-berry") & ~cat.isin(NOT_HELD_BERRIES)
    keep = pd.DataFrame({"name": name, "category": cat.where(~berry, "berries")})[cat.isin(HELD_CATEGORIES) | berry]
    keep = keep.drop_duplicates("name").sort_values("name")
    return [{"name": n, "category": c} for n, c in zip(keep["name"], keep["category"])]


def read_regulations(data: Path) -> list[dict]:
    """The manifest regulations of a web export with the poke_ids of their team_usage/<id>__all.json. Species-level
    rows (masked / unlisted forms, #24: poke_id null) add no form: none is guessed (BR-05); the forms seen of such a
    species have rows of their own."""
    regs = []
    for r in json.loads((Path(data) / "manifest.json").read_text(encoding="utf-8"))["regulations"]:
        path = Path(data) / "team_usage" / f"{r['id']}__all.json"
        if not path.exists():
            raise CalcMasterError(f"{path} not found (run export_web first)")
        rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
        regs.append({"id": r["id"], "label": r["label"], "poke_ids": [int(x["poke_id"]) for x in rows if x["poke_id"] is not None]})
    return regs


def _print_checks(data: dict, forms: list[dict]) -> None:
    fs = {f["poke_id"]: f for f in data["forms"]}
    print(f"  checks: every form in species_forms: {set(fs) <= {f['poke_id'] for f in forms}}; "
          f"abilities from the default form: {sum(f['abilities_from'] is not None for f in fs.values())}; "
          f"no ability: {[f['form'] for f in fs.values() if not f['abilities']]}")
    for r in data["regulations"]:
        g, by = r["version_group"], {"own": [], "default": [], "other": [], "none": []}
        for p in r["forms"]:
            s, name = fs[p]["learnsets"][g], fs[p]["form"]
            kind = ("none" if s["version_group"] is None else "other" if s["version_group"] != g
                    else "own" if s["poke_id"] == p else "default")
            by[kind].append(name if kind != "other" else f"{name} ({s['version_group']})")
        print(f"  {r['id']} ({g}): {len(r['forms'])} forms; own learnset {len(by['own'])}; default form's "
              f"{len(by['default'])} {by['default'][:10]}; other game's {len(by['other'])} {by['other']}; "
              f"none {len(by['none'])} {by['none']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", type=Path, default=Path("data/raw"))
    ap.add_argument("--data", type=Path, default=Path("web/public/data"),
                    help="web export: species_forms.json, manifest.json, team_usage/")
    ap.add_argument("--out", type=Path, default=Path("web/public/data/calc_master.json"))
    args = ap.parse_args(argv)

    forms = json.loads((args.data / "species_forms.json").read_text(encoding="utf-8"))
    data = build(args.master, forms, read_regulations(args.data))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out}: {len(text.encode('utf-8')):,} B; forms {len(data['forms'])} of {len(forms)} in "
          f"species_forms.json; skipped (no typing / base stats): {len(data['skipped'])} {data['skipped'][:10]}; "
          f"default regulation {data['regulations'][0]['id'] if data['regulations'] else None}")
    _print_checks(data, forms)
    print(f"  moves {len(data['moves'])}, natures {len(data['natures'])}, type chart pairs != 1x {len(data['type_chart'])}, "
          f"items {len(data['items'])} (unique names: {len({i['name'] for i in data['items']}) == len(data['items'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
