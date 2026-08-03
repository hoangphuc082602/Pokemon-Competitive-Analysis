from python.database.teams_loader import (
    load_all_teams,
    get_team
)
from python.services.team_service import (
    load_team, 
    load_team_by_name
)
from python.calculations.type_v2 import (
    analyze_team_defense,
    analyze_team_offense
)
from python.database.pokemon_loader import (
    load_all_pokemon_stats
)
from python.database.type_effectiveness_loader import load_type_effectiveness
from python.database.moves_loader import load_all_moves
import streamlit as st
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# LOAD DATA
team_df = load_all_teams()
move_df = load_all_moves()
pokemon_df = load_all_pokemon_stats()
type_chart_df = load_type_effectiveness()

# LIST
team_list = sorted(
    team_df["team_name"]
    .unique()
    .tolist()
)

# SELECT TEAM
selected_team = st.selectbox(
    "Select a team to analyze:",
    team_list
)
team = load_team(
        selected_team
    )

st.subheader(f"Team: {selected_team}")
for row_start in range(0, len(team), 3):
    cols = st.columns(3)

    for col_idx, pokemon in enumerate(team[row_start:row_start + 3]):
        with cols[col_idx]:

            showdown_text = f"""
{pokemon['pokemon'].title()} @ {pokemon['item']}
Ability: {pokemon['ability']}
Level: {pokemon['level']}
{pokemon['nature'].title()} Nature

EVs:
HP  {pokemon['evs']['hp']}
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

# ANALYZE TEAM
# DEFENSIVE ANALYSIS
defense_report = analyze_team_defense(type_chart_df, pokemon_df, team)

def build_defense_matrix(defense_report):
    matrix_df = pd.DataFrame(
        defense_report["by_pokemon"]
    ).T
    matrix_df.index.name = "Pokemon"
    return matrix_df
    matrix_df = pd.DataFrame(
        defense_report["by_pokemon"]
    ).T
    matrix_df.index.name = "Pokemon"
    return matrix_df

def color_cell(val):
    if val == 0:
        return "background-color:#5B9BD5;color:white"
    elif val == 0.25:
        return "background-color:#6AA84F;color:white"
    elif val == 0.5:
        return "background-color:#93C47D;color:black"
    elif val == 1:
        return ""
    elif val == 2:
        return "background-color:#FFD966;color:black"
    elif val >= 4:
        return "background-color:#E06666;color:white"
    return ""

def color_net(val):
    if val > 0:
        return "background-color:#6d1b1b;color:white"
    elif val < 0:
        return "background-color:#274e13;color:white"
    return ""

matrix_df = pd.DataFrame(
    defense_report["by_pokemon"]
)
matrix_df["Net"] = [
    defense_report["by_type"][t]["net"]
    for t in matrix_df.index
]
styled_df = (
    matrix_df.style
    .format("{:.2f}")
    .map(
        color_cell,
        subset=matrix_df.columns[:-1]
    )
    .map(
        color_net,
        subset=["Net"]
    )
)

# OFFENSIVE ANALYSIS
offense_report = analyze_team_offense(type_chart_df, move_df, team)

def build_offense_matrix(
        offense_report,
        team
):
    pokemon_names = [
        p["pokemon"]
        for p in team
    ]
    rows = []
    for attack_type, data in offense_report["by_type"].items():
        row = {
            "Type": attack_type.title()
        }
        for pokemon in pokemon_names:
            row[pokemon] = (pokemon in data["can_hit"])
        row["Status"] = data["is_covered"]
        rows.append(row)
    return pd.DataFrame(rows)

offense_df = build_offense_matrix(  
    offense_report,
    team
)

def offense_cell(val):
    if val == "✓":
        return """
        background-color:#93C47D;
        color:black;
        text-align:center
        """
    if val == "✖":
        return """
        background-color:#E06666;
        color:white;
        text-align:center
        """
    
display_df = offense_df.copy()

pokemon_cols = [
    c
    for c in offense_df.columns
    if c not in ["Type","Status"]
]

for col in pokemon_cols:
    display_df[col] = display_df[col].map(
        lambda x: "✓" if x else "✖"
    )
display_df["Status"] = display_df["Status"].map(
    lambda x: "✓" if x else "✖"
)

styled = (
    display_df.style
    .map(
        offense_cell,
        subset=pokemon_cols + ["Status"]
    )
)

# PRINT REPORTS
st.subheader("Defensive Analysis")
if st.button("ShowAnalysis", key="defensive_analysis"):
    st.dataframe(
    styled_df,
    use_container_width=True
)

st.subheader("Offensive Analysis")
if st.button("Show Analysis", key="offensive_analysis"):
    st.dataframe(
    styled,
    use_container_width=True
)