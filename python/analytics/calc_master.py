"""Master data for the browser damage calculator (#16, ADR-014), limited to the species dimension of the web export.

    python -m python.analytics.calc_master --master data/raw --forms web/public/data/species_forms.json \
        --out web/public/data/calc_master.json

Run after export_web (it reads the species_forms.json that export wrote). Writes one JSON file:
    forms       every form of species_forms.json that has typing and base stats: its own types and base stats, its
                abilities and the ids of the damaging moves it learns (any learn method; the crawl keeps Scarlet / Violet only)
    moves       only the moves in those learnsets that have a base power and a physical / special damage class
    natures     name, increased / decreased stat (null for neutral natures)
    type_chart  [attack_type, defense_type, multiplier] for every pair that is not 1x
Mechanics only (PokéAPI, BR-16): nothing from Showdown. The crawled ability and learnset tables have no rows for
alternate forms (poke_id >= 10001); such a form gets the rows of its species' default form (poke_id = species_id)
and `borrowed_from` names that poke_id, so the UI can say so. Typing and base stats are never borrowed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from python.analytics.export_web import FORBIDDEN
from python.calculations.nature_calc import STAT_MAPPING

SCHEMA_VERSION = 1
STATS = ["hp", "atk", "def", "spatk", "spdef", "spe"]
FILES = ("stats_raw.csv", "data_type.csv", "type_effectiveness.csv", "ability_raw.csv", "pokemon_ability.csv",
         "data_damage_class.csv", "move_raw.csv", "pokemon_moves.csv", "pokemon_nature_info.csv")
DAMAGING = ("physical", "special")


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


def build(master: Path, forms: list[dict]) -> dict:
    """Calculator master data for `forms` (species_forms.json records). See the module docstring."""
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
    pm = t["pokemon_moves.csv"]
    learnsets: dict[int, set[int]] = {}
    for pid, mid in zip(pm["pokemon_id"].astype("int64"), pm["move_id"].astype("int64")):
        if int(mid) in damaging:
            learnsets.setdefault(int(pid), set()).add(int(mid))

    out_forms, skipped = [], []
    for f in sorted(forms, key=lambda f: (f["species"], f["form"])):
        pid = int(f["poke_id"])
        if f.get("type_1") is None or any(f.get(s) is None for s in STATS):
            skipped.append(f["form"])
            continue
        own = pid in abilities or pid in learnsets
        source = pid if own else species_of.get(pid, pid)
        out_forms.append({"poke_id": pid, "species": f["species"], "form": f["form"],
                          "types": [x for x in (f["type_1"], f.get("type_2")) if x],
                          "base_stats": {s: int(f[s]) for s in STATS},
                          "abilities": abilities.get(source, []), "moves": sorted(learnsets.get(source, ())),
                          "borrowed_from": None if source == pid else source})

    used = sorted({m for f in out_forms for m in f["moves"]})
    natures = [{"name": str(r.nature_name), "increased": _stat(r.increased_stat), "decreased": _stat(r.decreased_stat)}
               for r in t["pokemon_nature_info.csv"].itertuples(index=False)]
    te = t["type_effectiveness.csv"]
    chart = [[types[int(a)], types[int(d)], float(m)]
             for a, d, m in zip(te["attack_type_id"], te["defense_type_id"], te["multiplier"]) if float(m) != 1.0]
    return {"schema_version": SCHEMA_VERSION, "level": 50, "forms": out_forms, "skipped": skipped,
            "moves": [damaging[m] for m in used], "natures": natures, "type_chart": chart}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", type=Path, default=Path("data/raw"))
    ap.add_argument("--forms", type=Path, default=Path("web/public/data/species_forms.json"))
    ap.add_argument("--out", type=Path, default=Path("web/public/data/calc_master.json"))
    args = ap.parse_args(argv)

    forms = json.loads(args.forms.read_text(encoding="utf-8"))
    data = build(args.master, forms)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    args.out.write_text(text, encoding="utf-8")
    fs = data["forms"]
    print(f"{args.out}: {len(text.encode('utf-8')):,} B; forms {len(fs)} of {len(forms)} in species_forms.json; "
          f"skipped (no typing / base stats): {len(data['skipped'])} {data['skipped'][:10]}")
    print(f"  checks: every form in species_forms: {set(f['poke_id'] for f in fs) <= set(f['poke_id'] for f in forms)}; "
          f"borrowed abilities / learnset from the default form: {sum(f['borrowed_from'] is not None for f in fs)}; "
          f"no learnset: {sum(not f['moves'] for f in fs)} {[f['form'] for f in fs if not f['moves']][:10]}; "
          f"no ability: {sum(not f['abilities'] for f in fs)}")
    print(f"  moves {len(data['moves'])}, natures {len(data['natures'])}, type chart pairs != 1x {len(data['type_chart'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
