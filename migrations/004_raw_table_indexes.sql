-- OPTIONAL. Indexes on the raw battle tables, for looking up one replay (drill-down, debugging, a replay viewer).
-- The aggregate tables do NOT need them: they are computed from the Parquet output and carry their own indexes
-- (written by python/analytics/sql_output.py).
--
-- Cost: each index on a 14-83M row table takes minutes to tens of minutes and several GB of disk. Create them one at
-- a time, in this order, and stop when the lookups you need are fast. Run them when nothing else is loading.

CREATE UNIQUE INDEX idx_battle_battle_id         ON battle (battle_id);
CREATE INDEX idx_battle_players_battle_id        ON battle_players (battle_id);
CREATE INDEX idx_battle_team_slot_battle_id      ON battle_team_slot (battle_id);
CREATE INDEX idx_battle_leads_battle_id          ON battle_leads (battle_id);
CREATE INDEX idx_battle_switch_battle_id         ON battle_switch (battle_id);
CREATE INDEX idx_battle_tera_battle_id           ON battle_tera (battle_id);
CREATE INDEX idx_battle_ability_battle_id        ON battle_ability (battle_id);
CREATE INDEX idx_battle_status_battle_id         ON battle_status (battle_id);
CREATE INDEX idx_battle_weather_battle_id        ON battle_weather (battle_id);
CREATE INDEX idx_battle_faint_battle_id          ON battle_faint (battle_id);
CREATE INDEX idx_battle_ko_battle_id             ON battle_ko (battle_id);
-- the three largest, last:
CREATE INDEX idx_battle_move_battle_id           ON battle_move (battle_id);
CREATE INDEX idx_battle_damage_battle_id         ON battle_damage (battle_id);
CREATE INDEX idx_battle_field_state_battle_id    ON battle_field_state (battle_id);

-- Check a lookup uses the index (the plan should show the idx_* key, not a full scan):
-- EXPLAIN SELECT * FROM battle_leads WHERE battle_id = 'gen9vgc2025regi-2000000000';