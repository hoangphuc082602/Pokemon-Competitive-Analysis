from sqlalchemy import create_engine, inspect, text
engine = create_engine("mysql+pymysql://root:123456@localhost/pokemon_analytics")

inspecter = inspect(engine)

tables = {
    "players",
    "battle",
    "battle_move",
    "battle_switch",
    "battle_damage",
    "battle_weather",
    "battle_ability",
    "battle_faint",
    "battle_ko",
    "battle_players",
    "battle_team_slot",
    "battle_status",
    "battle_tera",
    "battle_leads",
    "pokemon_battle_features",
    "pokemon_usage_daily",
    "pokemon_usage_stats",
    "recommended_partners",
    "turn_events",
    "team_synergy",
    "vgc_battles"
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