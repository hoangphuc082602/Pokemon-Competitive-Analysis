import streamlit as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from python.database.pokemon_loader import (
    load_all_pokemon_stats
)

from python.database.poke_abi_loader import(
    load_all_poke_abi,
    get_poke_abi
)

from python.database.poke_move_loader import(
    load_all_pokemon_moves,
    get_pokemon_moves
)

from python.database.moves_loader import (
    load_all_moves,
    get_move_data
)

from python.database.natures_loader import (
    load_all_natures
)

from python.database.items_loader import(
    load_all_items
)

from python.database.type_effectiveness_loader import (
    load_type_effectiveness
)

from python.models.team_builder import (
    build_pokemon
)

from python.calculations.damage_calc_v2 import (
    calculate_damage
)

# LOAD DATA
pokemon_df = load_all_pokemon_stats()
move_df = load_all_moves()
nature_df = load_all_natures()
item_df = load_all_items()
type_chart_df = load_type_effectiveness()
poke_abi_df = load_all_poke_abi()
poke_moves_df = load_all_pokemon_moves()

pokemon_list = sorted(
    pokemon_df["pokemon"]
    .unique()
    .tolist()
)
def poke_abi_list(poke_abi_df, pokemon_name):
    ability = (
        poke_abi_df[poke_abi_df["pokemon"] == pokemon_name]
        ["ability_name"]
        .unique()
        .tolist()
)
    return ability

def poke_moves_list(poke_moves_list, pokemon_name):
    moves = (
        poke_moves_df[poke_moves_df["pokemon"] == pokemon_name]
        ["move_name"]
        .unique()
        .tolist()
    )
    return moves

nature_list = sorted(
    nature_df["nature_name"]
    .unique()
    .tolist()
)
item_list = sorted(
    item_df["item_name"]
    .unique()
    .tolist()
)

st.title("Damage Calculator")

# ATTACKER
st.subheader("Attacker")

col1, col2, col3 = st.columns(3)
with col1:
    attacker_name = st.selectbox(
        "Attacker Pokemon",
        pokemon_list
    )
    attacker_nature = st.selectbox(
        "Attacker Nature",
        nature_list,
        key="attacker_nature"
    )

with col2:
    attacker_level = st.number_input(
        "Attacker Level",
        min_value=1,
        max_value=100,
        value=50
    )
    attacker_ability = st.selectbox(
        "Attacker Ability",
        poke_abi_list(poke_abi_df, attacker_name),
        key = "atk ability"
    )

with col3:
    attacker_item = st.selectbox(
        "Attacker Item",
        item_list,
        key="attacker item"
    )

# ATTACKER IVS & EVS
with st.expander("Advanced Stats"):
    st.markdown("### IVs")
    iv_cols = st.columns(6)
    atk_hp_iv = iv_cols[0].number_input(
        "HP IV",
        min_value=0,
        max_value=31,
        value=31,
        key="atk_hp_iv"
    )

    atk_atk_iv = iv_cols[1].number_input(
        "ATK IV",
        min_value=0,
        max_value=31,
        value=31,
        key="atk_atk_iv"
    )

    atk_def_iv = iv_cols[2].number_input(
        "DEF IV",
        min_value=0,
        max_value=31,
        value=31,
        key="atk_def_iv"
    )

    atk_spatk_iv = iv_cols[3].number_input(
        "SPATK IV",
        min_value=0,
        max_value=31,
        value=31,
        key="atk_spatk_iv"
    )

    atk_spdef_iv = iv_cols[4].number_input(
        "SPDEF IV",
        min_value=0,
        max_value=31,
        value=31,
        key="atk_spdef_iv"
    )

    atk_spe_iv = iv_cols[5].number_input(
        "SPE IV",
        min_value=0,
        max_value=31,
        value=31,
        key="atk_spe_iv"
    )

    attacker_ivs = {
        "hp": atk_hp_iv,
        "atk": atk_atk_iv,
        "def": atk_def_iv,
        "spatk": atk_spatk_iv,
        "spdef": atk_spdef_iv,
        "spe": atk_spe_iv
    }

    st.markdown("### EVs")
    ev_cols = st.columns(6)

    atk_hp_ev = ev_cols[0].number_input(
        "HP EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="atk_hp_ev"
    )

    atk_atk_ev = ev_cols[1].number_input(
        "ATK EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="atk_atk_ev"
    )

    atk_def_ev = ev_cols[2].number_input(
        "DEF EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="atk_def_ev"
    )

    atk_spatk_ev = ev_cols[3].number_input(
        "SPATK EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="atk_spatk_ev"
    )

    atk_spdef_ev = ev_cols[4].number_input(
        "SPDEF EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="atk_spdef_ev"
    )

    atk_spe_ev = ev_cols[5].number_input(
        "SPE EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="atk_spe_ev"
    )

    attacker_evs = {
        "hp": atk_hp_ev,
        "atk": atk_atk_ev,
        "def": atk_def_ev,
        "spatk": atk_spatk_ev,
        "spdef": atk_spdef_ev,
        "spe": atk_spe_ev
    }
    total_ev = sum(attacker_evs.values())
    if total_ev > 510:
        st.error(
            f"EV total exceeds 510 ({total_ev}/510)"
        )

# DEFENDER
st.subheader("Defender")

col1, col2, col3 = st.columns(3)
with col1:
    defender_name = st.selectbox(
        "Defender Pokemon",
        pokemon_list
    )
    defender_nature = st.selectbox(
        "Defender Nature",
        nature_list,
        key="defender_nature"
    )
with col2:
    defender_level = st.number_input(
        "Defender Level",
        min_value=1,
        max_value=100,
        value=50
    )
    defender_ability = st.selectbox(
        "Defender Ability",
        poke_abi_list(poke_abi_df, defender_name),
        key="def_ability"
    )
with col3:
    defender_item = st.selectbox(
        "Defender Item",
        item_list,
        key="def_item"
    )

# DEFENDER IVS & EVS
with st.expander("Advanced Stats"):
    st.markdown("### IVs")
    iv_cols = st.columns(6)

    def_hp_iv = iv_cols[0].number_input(
        "HP IV",
        min_value=0,
        max_value=31,
        value=31,
        key="def_hp_iv"
    )

    def_atk_iv = iv_cols[1].number_input(
        "ATK IV",
        min_value=0,
        max_value=31,
        value=31,
        key="def_atk_iv"
    )

    def_def_iv = iv_cols[2].number_input(
        "DEF IV",
        min_value=0,
        max_value=31,
        value=31,
        key="def_def_iv"
    )

    def_spatk_iv = iv_cols[3].number_input(
        "SPATK IV",
        min_value=0,
        max_value=31,
        value=31,
        key="def_spatk_iv"
    )

    def_spdef_iv = iv_cols[4].number_input(
        "SPDEF IV",
        min_value=0,
        max_value=31,
        value=31,
        key="def_spdef_iv"
    )

    def_spe_iv = iv_cols[5].number_input(
        "SPE IV",
        min_value=0,
        max_value=31,
        value=31,
        key="def_spe_iv"
    )

    defender_ivs = {
        "hp": def_hp_iv,
        "atk": def_atk_iv,
        "def": def_def_iv,
        "spatk": def_spatk_iv,
        "spdef": def_spdef_iv,
        "spe": def_spe_iv
    }

    st.markdown("### EVs")
    ev_cols = st.columns(6)
    def_hp_ev = ev_cols[0].number_input(
        "HP EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="def_hp_ev"
    )

    def_atk_ev = ev_cols[1].number_input(
        "ATK EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="def_atk_ev"
    )

    def_def_ev = ev_cols[2].number_input(
        "DEF EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="def_def_ev"
    )

    def_spatk_ev = ev_cols[3].number_input(
        "SPATK EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="def_spatk_ev"
    )

    def_spdef_ev = ev_cols[4].number_input(
        "SPDEF EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="def_spdef_ev"
    )

    def_spe_ev = ev_cols[5].number_input(
        "SPE EV",
        min_value=0,
        max_value=252,
        value=0,
        step=4,
        key="def_spe_ev"
    )

    defender_evs = {
        "hp": def_hp_ev,
        "atk": def_atk_ev,
        "def": def_def_ev,
        "spatk": def_spatk_ev,
        "spdef": def_spdef_ev,
        "spe": def_spe_ev
    }
    total_ev = sum(defender_evs.values())
    if total_ev > 510:
        st.error(
            f"EV total exceeds 510 ({total_ev}/510)"
        )

# MOVE
move_name = st.selectbox(
    "Move",
    poke_moves_list(poke_moves_df, attacker_name)
)

# CALCULATE
if st.button("Calculate Damage"):

    attacker = build_pokemon(
        pokemon_df=pokemon_df,
        nature_df=nature_df,
        pokemon_name=attacker_name,
        level=attacker_level,
        nature=attacker_nature,
        ability=attacker_ability,
        item=attacker_item,
        moves=[move_name],
        ivs=attacker_ivs,
        evs=attacker_evs
    )
    defender = build_pokemon(
        pokemon_df=pokemon_df,
        nature_df=nature_df,
        pokemon_name=defender_name,
        level=defender_level,
        nature=defender_nature,
        ability=defender_ability,
        item=defender_item,
        moves=[],
        ivs=defender_ivs,
        evs=defender_evs
    )

    move = get_move_data(
        move_df,
        move_name
    )
    result = calculate_damage(
        attacker=attacker,
        defender=defender,
        move=move,
        type_chart_df=type_chart_df
    )

    st.subheader("Battle Objects")

    st.table({
        "move": move
    })

    st.subheader("Damage Result")

    st.json(result)