-- Parser v2.1: owner of the Pokemon for events that only name a slot (needed to attribute Tera / ability to a team).
-- Run on EMPTY tables (TRUNCATE first), then reload the four tables from the new Parquet output.
ALTER TABLE battle_tera    ADD COLUMN username VARCHAR(100) NULL;
ALTER TABLE battle_ability ADD COLUMN username VARCHAR(100) NULL;
ALTER TABLE battle_status  ADD COLUMN username VARCHAR(100) NULL;
ALTER TABLE battle_faint   ADD COLUMN username VARCHAR(100) NULL;