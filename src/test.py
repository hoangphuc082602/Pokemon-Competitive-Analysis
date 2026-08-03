from team_generator import TeamGenerator

gen = TeamGenerator(
    "data/output/battle_team_slot.parquet"
)

for i, team in enumerate(gen):

    print(team)

    if i == 5:
        break