
import streamlit as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from python.database.pokemon_loader import load_all_pokemon_stats
from python.database.poke_move_loader import load_all_pokemon_moves
from python.database.poke_abi_loader import load_all_poke_abi
from python.database.items_loader import load_all_items
from python.database.natures_loader import load_all_natures
from python.database.teams_loader import load_all_teams, get_team
from python.services.team_service import load_team, save_team, load_team_by_name

# LOAD DATA
pokemon_df = load_all_pokemon_stats()
poke_moves_df = load_all_pokemon_moves()
poke_abi_df = load_all_poke_abi()
item_df = load_all_items()
nature_df = load_all_natures()
team_df = load_all_teams()

# DATA LIST
pokemon_list = [pokemon for pokemon in pokemon_df["pokemon"].unique()]
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

team_names = (
    team_df["team_name"]
    .tolist()
)

team = []

selected_team = st.selectbox(
    "Select Team",
    team_names
)
if st.button(
    "Load Selected Team"
):
    team = load_team(
        selected_team
    )

    for pokemon in team:

        showdown_text = f"""
    {pokemon['pokemon'].title()} @ {pokemon['item']}
    Ability: {pokemon['ability']}
    Level: {pokemon['level']}
    {pokemon['nature'].title()} Nature

    EVs:
    HP {pokemon['evs']['hp']}
    Atk {pokemon['evs']['atk']}
    Def {pokemon['evs']['def']}
    SpA {pokemon['evs']['spatk']}
    SpD {pokemon['evs']['spdef']}
    Spe {pokemon['evs']['spe']}

    Moves:
    """

        for move in pokemon["moves"]:
            showdown_text += f"\n- {move}"
        st.code(showdown_text)

for i in range(6):
        with st.container(border=True):

            st.subheader(
            f"Pokemon #{i+1}"
        )

        name = st.selectbox(
            "Pokemon",
            pokemon_list,
            key=f"pokemon_{i}"
        )
        ability_list = poke_abi_list(
            poke_abi_df,
            name
        )
        move_list = poke_moves_list(
            poke_moves_df,
            name
        )

        col1, col2 = st.columns(2)
        with col1:

            nature = st.selectbox(
                "Nature",
                nature_list,
                key=f"nature_{i}"
            )
            ability = st.selectbox(
                "Ability",
                ability_list,
                key=f"ability_{i}"
            )

        with col2:

            item = st.selectbox(
                "Item",
                item_list,
                key=f"item_{i}"
            )
        with st.expander("Moves"):
            st.markdown("### Moves")
            move_cols = st.columns(4)
            move1 = move_cols[0].selectbox(
                "Move 1",
                move_list,
                key=f"move1_{i}"
            )
            move2 = move_cols[1].selectbox(
                "Move 2",
                move_list,
                key=f"move2_{i}"
            )
            move3 = move_cols[2].selectbox(
                "Move 3",
                move_list,
                key=f"move3_{i}"
            )
            move4 = move_cols[3].selectbox(
                "Move 4",
                move_list,
                key=f"move4_{i}"
            )
            # IVS & EVS
        with st.expander("Advanced Stats"):
            st.markdown("### IVs")
            iv_cols = st.columns(6)
            hp_iv = iv_cols[0].number_input(
                "HP IV",
                min_value=0,
                max_value=31,
                value=31,
                key=f"{i}_hp_iv"
            )

            atk_iv = iv_cols[1].number_input(
                "ATK IV",
                min_value=0,
                max_value=31,
                value=31,
                key=f"{i}_iv"
            )

            def_iv = iv_cols[2].number_input(
                "DEF IV",
                min_value=0,
                max_value=31,
                value=31,
                key=f"{i}_def_iv"
            )

            spiv = iv_cols[3].number_input(
                "SPATK IV",
                min_value=0,
                max_value=31,
                value=31,
                key=f"{i}_spiv"
            )

            spdef_iv = iv_cols[4].number_input(
                "SPDEF IV",
                min_value=0,
                max_value=31,
                value=31,
                key=f"{i}_spdef_iv"
            )

            spe_iv = iv_cols[5].number_input(
                "SPE IV",
                min_value=0,
                max_value=31,
                value=31,
                key=f"{i}_spe_iv"
            )

            ivs = {
                "hp": hp_iv,
                "atk": atk_iv,
                "def": def_iv,
                "spatk": spiv,
                "spdef": spdef_iv,
                "spe": spe_iv
            }

            st.markdown("### EVs")
            ev_cols = st.columns(6)

            hp_ev = ev_cols[0].number_input(
                "HP EV",
                min_value=0,
                max_value=252,
                value=0,
                step=4,
                key=f"{i}_hp_ev"
            )

            ev = ev_cols[1].number_input(
                "ATK EV",
                min_value=0,
                max_value=252,
                value=0,
                step=4,
                key=f"{i}_atk_ev"
            )

            def_ev = ev_cols[2].number_input(
                "DEF EV",
                min_value=0,
                max_value=252,
                value=0,
                step=4,
                key=f"{i}_def_ev"
            )

            spev = ev_cols[3].number_input(
                "SPATK EV",
                min_value=0,
                max_value=252,
                value=0,
                step=4,
                key=f"{i}_spev"
            )

            spdef_ev = ev_cols[4].number_input(
                "SPDEF EV",
                min_value=0,
                max_value=252,
                value=0,
                step=4,
                key=f"{i}_spdef_ev"
            )

            spe_ev = ev_cols[5].number_input(
                "SPE EV",
                min_value=0,
                max_value=252,
                value=0,
                step=4,
                key=f"{i}_spe_ev"
            )

            evs = {
                "hp": hp_ev,
                "atk": ev,
                "def": def_ev,
                "spatk": spev,
                "spdef": spdef_ev,
                "spe": spe_ev
            }
            total_ev = sum(evs.values())
            if total_ev > 510:
                st.error(
                    f"EV total exceeds 510 ({total_ev}/510)"
                )

        pokemon_object = {
            "pokemon": name,
            "nature": nature,
            "ability": ability,
            "item": item,
            "moves": [
                move1,
                move2,
                move3,
                move4
            ],
            "ivs":ivs,
            "evs":evs
        }

        team.append(
            pokemon_object
        )

team_name = st.text_input(
    "Team Name"
)

st.write(team)

if st.button(
    "Save Team"
):

    save_team(
        team_name,
        team
    )

    st.success(
        "Team Saved"
    )