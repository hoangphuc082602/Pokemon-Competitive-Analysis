from sqlalchemy import inspect, text
from python.database.db_connection import engine

inspecter = inspect(engine)

tables = {
    "ability",
    "battle",
    "battle_ability",
    "battle_damage",
    "battle_faint",
    "battle_field_state",
    "battle_ko",
    "battle_leads",
    "battle_move",
    "battle_players",
    "battle_status",
    "battle_switch",
    "battle_team_slot",
    "battle_tera",
    "battle_weather",
    "damage_classes",
    "evo_methods",
    "item",
    "learn_method",
    "matchup",
    "moves",
    "nature",
    "players",
    "pokemon_abilities",
    "pokemon_battle_features",
    "pokemon_evolution",
    "pokemon_moves",
    "pokemon_species",
    "pokemon_stats",
    "pokemon_types",
    "pokemon_usage_daily",
    "pokemon_usage_stats",
    "recommended_partners",
    "stat_info",
    "team_master",
    "team_pokemon",
    "team_pokemon_evs",
    "team_pokemon_ivs",
    "team_pokemon_moves",
    "team_synergy",
    "turn_events",
    "type_effectiveness",
    "types",
    "vgc_battles",
}

with engine.connect() as conn:
    for table in tables:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM `{table}`")
        ).scalar()
        print(f"\n{table}")
        print(f"Rows: {count:,}")
        for col in inspecter.get_columns(table):
            print(
                f"  {col['name']:30}"
                f"{col['type']}"
            )