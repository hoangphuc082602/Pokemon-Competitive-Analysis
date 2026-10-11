"""
Pokemon Showdown Battle Log Parser
State machine-based parser that converts raw .log files into structured data
matching the database schema. Supports batch processing to avoid RAM overflow.
"""

from __future__ import annotations

import re
import json
import os
import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
from pathlib import Path


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

class ParserState(Enum):
    INIT        = auto()   # Before any meaningful data
    HEADER      = auto()   # Reading metadata (gametype, players, poke lines)
    TEAM_PREVIEW= auto()   # Between |teampreview| and |start|
    IN_BATTLE   = auto()   # Between |start| and |win|/|tie|
    POST_BATTLE = auto()   # After win/tie


KO_TYPE_MAP = {
    # damage source -> ko_type enum value
    "brn":     "BURN",
    "psn":     "POISON",
    "tox":     "POISON",
    "Sandstorm":  "WEATHER",
    "Hail":       "WEATHER",
    "Snow":       "WEATHER",
    "sandstorm":  "WEATHER",
    "hail":       "WEATHER",
    "snow":       "WEATHER",
    "recoil":     "MOVE",   # recoil from move
    "Spikes":     "HAZARD",
    "Stealth Rock": "HAZARD",
    "Sticky Web": "HAZARD",
    "Toxic Spikes": "HAZARD",
}

# ---------------------------------------------------------------------------
# Lightweight data containers (avoid heavy ORM overhead)
# ---------------------------------------------------------------------------

@dataclass
class BattleRecord:
    battle_id: str = ""
    format: str = ""
    format_id: str = ""
    upload_time: Optional[int] = None
    rating: Optional[int] = None
    winner_name: Optional[str] = None        # raw name for resolution
    replay_path: Optional[str] = None
    turn_count: int = 0


@dataclass
class PlayerRecord:
    username: str = ""


@dataclass
class BattlePlayerRecord:
    battle_id: str = ""
    username: str = ""
    side: str = ""                           # 'p1' or 'p2'
    rating_before: Optional[int] = None
    rating_after: Optional[int] = None
    result: Optional[str] = None             # 'WIN' or 'LOSS'


@dataclass
class BattleTeamSlot:
    battle_id: str = ""
    player_side: str = ""
    slot_no: int = 0
    pokemon_name: str = ""
    is_lead: bool = False
    species_observed: str = ""      # real species/form seen in battle for this slot (resolves 'Urshifu-*')
    form_status: str = "listed"     # listed | observed | ambiguous | unobserved
    was_sent_out: bool = False      # the Pokemon entered the field at least once


@dataclass
class BattleLeadRecord:
    battle_id: str = ""
    username: str = ""
    pokemon_name: str = ""
    species: str = ""             # real species/form from |switch| details (pokemon_name is the nickname)
    lead_slot: int = 0


@dataclass
class BattleMoveRecord:
    battle_id: str = ""
    turn_no: int = 0
    username: str = ""          # resolved to player_id during ingest
    pokemon_name: str = ""
    species: str = ""             # real species/form from |switch| details (pokemon_name is the nickname)
    move_name: str = ""
    target_name: str = ""
    success: bool = True


@dataclass
class BattleDamageRecord:
    battle_id: str = ""
    turn_no: int = 0
    attacker_pokemon: str = ""
    defender_pokemon: str = ""
    attacker_species: str = ""
    defender_species: str = ""
    move_name: str = ""
    hp_before: float = 0.0
    hp_after: float = 0.0
    damage_pct: float = 0.0


@dataclass
class BattleKORecord:
    battle_id: str = ""
    turn_no: int = 0
    killer_pokemon: str = ""
    victim_pokemon: str = ""
    killer_species: str = ""
    victim_species: str = ""
    move_name: str = ""
    ko_type: str = "MOVE"


@dataclass
class BattleFaintRecord:
    battle_id: str = ""
    turn_no: int = 0
    pokemon_name: str = ""
    species: str = ""             # real species/form from |switch| details (pokemon_name is the nickname)


@dataclass
class BattleSwitchRecord:
    battle_id: str = ""
    turn_no: int = 0
    username: str = ""
    pokemon_name: str = ""
    species: str = ""             # real species/form from |switch| details (pokemon_name is the nickname)


@dataclass
class BattleWeatherRecord:
    battle_id: str = ""
    turn_no: int = 0
    weather_name: str = ""
    source_pokemon: str = ""


@dataclass
class BattleStatusRecord:
    battle_id: str = ""
    turn_no: int = 0
    pokemon_name: str = ""
    species: str = ""             # real species/form from |switch| details (pokemon_name is the nickname)
    status_code: str = ""


@dataclass
class BattleAbilityRecord:
    battle_id: str = ""
    turn_no: int = 0
    pokemon_name: str = ""
    species: str = ""             # real species/form from |switch| details (pokemon_name is the nickname)
    ability_name: str = ""


@dataclass
class BattleTeraRecord:
    battle_id: str = ""
    turn_no: int = 0
    pokemon_name: str = ""
    species: str = ""             # real species/form from |switch| details (pokemon_name is the nickname)
    tera_type: str = ""


@dataclass
class BattleFieldStateRecord:
    battle_id: str = ""
    turn_no: int = 0
    p1_left: str = ""
    p1_right: str = ""
    p2_left: str = ""
    p2_right: str = ""


@dataclass
class ParsedBattle:
    """All data extracted from a single battle log."""
    battle: BattleRecord = field(default_factory=BattleRecord)
    players: list[PlayerRecord] = field(default_factory=list)
    battle_players: list[BattlePlayerRecord] = field(default_factory=list)
    team_slots: list[BattleTeamSlot] = field(default_factory=list)
    leads: list[BattleLeadRecord] = field(default_factory=list)
    moves: list[BattleMoveRecord] = field(default_factory=list)
    damages: list[BattleDamageRecord] = field(default_factory=list)
    kos: list[BattleKORecord] = field(default_factory=list)
    faints: list[BattleFaintRecord] = field(default_factory=list)
    switches: list[BattleSwitchRecord] = field(default_factory=list)
    weathers: list[BattleWeatherRecord] = field(default_factory=list)
    statuses: list[BattleStatusRecord] = field(default_factory=list)
    abilities: list[BattleAbilityRecord] = field(default_factory=list)
    teras: list[BattleTeraRecord] = field(default_factory=list)
    field_states: list[BattleFieldStateRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_pokemon_name(raw: str) -> str:
    """'p1a: Ogerpon' -> 'Ogerpon', also strips form suffixes for storage."""
    if ": " in raw:
        raw = raw.split(": ", 1)[1]
    # Remove common trailing details like ', M', ', F', ', shiny'
    raw = re.sub(r",\s*(M|F|shiny|shiny M|shiny F)$", "", raw, flags=re.IGNORECASE)
    return raw.strip()


def _species_from_details(details: str) -> str:
    """'Urshifu-Rapid-Strike, L50, M' -> 'Urshifu-Rapid-Strike' (the form, not the nickname)."""
    return details.split(",", 1)[0].strip()


def _match_species(preview_name: str, species_pool) -> list[str]:
    """Species from ``species_pool`` matching a team-preview name; 'Urshifu-*' matches Urshifu and Urshifu-<form>."""
    n = preview_name.lower()
    if n.endswith("-*"):
        base = n[:-2]
        return sorted(sp for sp in species_pool if sp.lower() == base or sp.lower().startswith(base + "-"))
    return sorted(sp for sp in species_pool if sp.lower() == n)


def _parse_hp(hp_str: str) -> Optional[float]:
    """'87/100' -> 87.0, '0 fnt' -> 0.0, '100/100' -> 100.0"""
    if not hp_str:
        return None
    hp_str = hp_str.strip()
    if hp_str in ("0 fnt", "fnt", "0"):
        return 0.0
    m = re.match(r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)", hp_str)
    if m:
        cur, mx = float(m.group(1)), float(m.group(2))
        return round(cur / mx * 100, 2) if mx else 0.0
    m2 = re.match(r"(\d+(?:\.\d+)?)$", hp_str)
    if m2:
        return float(m2.group(1))
    return None


def _side_from_slot(slot_str: str) -> str:
    """'p1a' -> 'p1', 'p2b' -> 'p2'"""
    return slot_str[:2] if len(slot_str) >= 2 else slot_str


def _generate_battle_id(log_text: str, filepath: Optional[str] = None) -> str:
    """Generate a stable battle_id from filepath or log hash."""
    if filepath:
        stem = Path(filepath).stem
        # Showdown replay files are named like 'gen92v2doubles-1234567890'
        if re.match(r"[\w\-]+-\d+", stem):
            return stem
    # Fallback: hash first 500 chars of log
    digest = hashlib.md5(log_text[:500].encode()).hexdigest()[:12]
    return f"battle-{digest}"


# ---------------------------------------------------------------------------
# State Machine Parser
# ---------------------------------------------------------------------------

class BattleLogParser:
    """
    Parses a single Pokemon Showdown battle log using a finite state machine.

    States:
        INIT          -> waiting for first pipe token
        HEADER        -> reading metadata before |start|
        TEAM_PREVIEW  -> |teampreview| seen, reading preview data
        IN_BATTLE     -> |start| seen, processing turn-by-turn actions
        POST_BATTLE   -> |win| or |tie| seen
    """

    def __init__(self, battle_id: Optional[str] = None, replay_path: Optional[str] = None):
        self._battle_id = battle_id or ""
        self._replay_path = replay_path

        # FSM state
        self._state: ParserState = ParserState.INIT

        # Working data
        self._result = ParsedBattle()
        self._current_turn: int = 0

        # Player side -> username mapping  {p1: "PlayerA", p2: "PlayerB"}
        self._side_to_name: dict[str, str] = {}
        # username -> side
        self._name_to_side: dict[str, str] = {}
        # Team slots per side  {p1: [slot1_name, slot2_name,...], p2:[...]}
        self._poke_preview: dict[str, list[str]] = {"p1": [], "p2": []}
        # Active pokemon on field  {p1a: name, p1b: name, p2a: name, p2b: name}
        self._active: dict[str, str] = {}
        self._active_species: dict[str, str] = {}                 # slot -> species currently on the field
        self._name_species: dict[tuple[str, str], str] = {}
        self._switched_species: dict[str, set[str]] = {"p1": set(), "p2": set()}   # species that entered the field
        self._lead_slots_seen: set[str] = set()                   # slots already filled by an opening lead
        # Last move context for linking damage/KO
        self._last_move: dict[str, str] = {}   # slot -> move_name
        self._last_move_target: dict[str, str] = {}  # slot -> target_slot
        # HP tracking  {slot: current_pct}
        self._hp: dict[str, float] = {}
        # Pending damage records waiting for KO confirmation
        self._pending_damage: dict[str, BattleDamageRecord] = {}
        # Rating info from |rated| line
        self._rating: Optional[int] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, log_text: str) -> ParsedBattle:
        lines = log_text.splitlines()
        for line in lines:
            self._process_line(line.strip())
        self._finalize()
        return self._result

    # ------------------------------------------------------------------
    # FSM dispatcher
    # ------------------------------------------------------------------

    def _process_line(self, line: str) -> None:
        if not line.startswith("|"):
            return

        # Split on first few pipes
        parts = line.split("|")
        # parts[0] is always empty string (before first |)
        if len(parts) < 2:
            return

        token = parts[1] if len(parts) > 1 else ""

        # --- State transitions ---
        if token == "start":
            self._state = ParserState.IN_BATTLE
            return
        if token == "teampreview":
            self._state = ParserState.TEAM_PREVIEW
            return
        if token in ("win", "tie"):
            self._handle_win(token, parts)
            self._state = ParserState.POST_BATTLE
            return
        if token == "turn":
            self._state = ParserState.IN_BATTLE
            self._handle_turn(parts)
            return

        # --- Route to appropriate handler based on current state ---
        if self._state in (ParserState.INIT, ParserState.HEADER, ParserState.TEAM_PREVIEW):
            self._handle_header_token(token, parts)
        elif self._state == ParserState.IN_BATTLE:
            self._handle_battle_token(token, parts)
        # POST_BATTLE: only pick up name changes etc. – not needed for schema

    # ------------------------------------------------------------------
    # Header / metadata handlers
    # ------------------------------------------------------------------

    def _handle_header_token(self, token: str, parts: list[str]) -> None:
        if token == "t:":
            # |t:|<unix_timestamp>
            if len(parts) > 2:
                try:
                    self._result.battle.upload_time = int(parts[2])
                except ValueError:
                    pass

        elif token == "gametype":
            pass  # Could store doubles/singles but schema doesn't have a field

        elif token == "player":
            # |player|p1|PlayerName|avatar|rating
            if len(parts) < 4:
                return
            side = parts[2]           # p1 / p2
            username = parts[3].strip()
            if not username:
                return                # '|player|p1|' = the player left
            known = next((b for b in self._result.battle_players if b.side == side), None)
            if known:                 # re-join / avatar change: keep one row per side
                if known.rating_before is None:
                    known.rating_before = self._player_rating(parts)
                return
            self._side_to_name[side] = username
            self._name_to_side[username] = side

            rating_val = self._player_rating(parts)

            bp = BattlePlayerRecord(
                battle_id=self._battle_id,
                username=username,
                side=side,
                rating_before=rating_val,
            )
            self._result.battle_players.append(bp)
            self._result.players.append(PlayerRecord(username=username))

        elif token == "rated":
            # |rated|<rating>  OR just |rated|  (tournament flag)
            if len(parts) > 2 and parts[2].strip().lstrip("-").isdigit():
                self._rating = int(parts[2])

        elif token == "poke":
            # |poke|p1|Archaludon, M|
            if len(parts) < 4:
                return
            side = parts[2]
            raw_name = parts[3].split(",")[0].strip()
            self._poke_preview[side].append(raw_name)

        elif token == "tier":
            # |tier|[Gen 9] 2v2 Doubles
            if len(parts) > 2:
                tier_str = "|".join(parts[2:])
                self._result.battle.format = tier_str
                # format_id: lowercase, strip brackets/spaces
                fid = re.sub(r"[\[\]\s]+", "", tier_str).lower()
                self._result.battle.format_id = fid

        elif token == "switch":
            # During team preview phase, first switches are the leads
            if self._state == ParserState.TEAM_PREVIEW:
                self._handle_switch(parts, is_lead=True)

    # ------------------------------------------------------------------
    # In-battle event handlers
    # ------------------------------------------------------------------

    def _handle_turn(self, parts: list[str]) -> None:
        if len(parts) > 2:
            try:
                self._current_turn = int(parts[2])
                self._result.battle.turn_count = self._current_turn
            except ValueError:
                pass
        # Snapshot field state at start of each turn
        self._record_field_state()

    def _handle_battle_token(self, token: str, parts: list[str]) -> None:
        dispatch = {
            "switch":   self._handle_switch,
            "drag":     self._handle_switch,   # drag == involuntary switch
            "detailschange": self._handle_details_change,   # permanent form change (Mega, Primal, ...)
            "replace":  self._handle_details_change,        # Illusion ends
            "move":     self._handle_move,
            "-damage":  self._handle_damage,
            "-heal":    self._handle_heal,
            "faint":    self._handle_faint,
            "-weather": self._handle_weather,
            "-status":  self._handle_status,
            "-ability": self._handle_ability,
            "-terastallize": self._handle_tera,
            "-fail":    self._handle_fail,
        }
        handler = dispatch.get(token)
        if handler:
            handler(parts)

    # --- switch / drag ---
    def _handle_switch(self, parts: list[str], is_lead: bool = False) -> None:
        # |switch|p1a: Ogerpon|Ogerpon-Cornerstone, F|100/100
        if len(parts) < 4:
            return
        slot_raw = parts[2]          # 'p1a: Ogerpon'
        side_slot = slot_raw.split(":")[0].strip()   # 'p1a'
        pokemon_name = _strip_pokemon_name(slot_raw)
        side = _side_from_slot(side_slot)

        # Update active roster
        self._active[side_slot] = pokemon_name
        species = _species_from_details(parts[3])
        self._active_species[side_slot] = species
        self._name_species[(side, pokemon_name)] = species
        if side in self._switched_species:
            self._switched_species[side].add(species)

        # HP
        if len(parts) > 4:
            hp = _parse_hp(parts[4])
            if hp is not None:
                self._hp[side_slot] = hp

        lead_slot = ord(side_slot[-1]) - ord('a') + 1 if side_slot else 1

        # Leads = switches before turn 1 begins (turn_no==0, IN_BATTLE) or TEAM_PREVIEW
        is_opening_lead = (
            is_lead
            or self._state == ParserState.TEAM_PREVIEW
            or (self._state == ParserState.IN_BATTLE and self._current_turn == 0)
        )

        if is_opening_lead and side_slot in self._lead_slots_seen:
            is_opening_lead = False   # turn-0 replacement (e.g. Eject Pack after Intimidate) is a switch, not a lead
        if is_opening_lead:
            self._lead_slots_seen.add(side_slot)
            username = self._side_to_name.get(side, "")
            self._result.leads.append(BattleLeadRecord(
                battle_id=self._battle_id,
                username=username,
                pokemon_name=pokemon_name,
                species=species,
                lead_slot=lead_slot,
            ))
            return  # opening deployment is not a mid-game switch

        # Mid-game switch
        username = self._side_to_name.get(side, "")
        self._result.switches.append(BattleSwitchRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            username=username,
            pokemon_name=pokemon_name,
            species=species,
        ))

    @staticmethod
    def _player_rating(parts: list[str]) -> Optional[int]:
        # |player|p1|NAME|AVATAR|RATING : parts[4] is the avatar id, never a rating
        if len(parts) > 5 and parts[5].strip().lstrip("-").isdigit():
            return int(parts[5])
        return None

    # --- details change ---
    def _handle_details_change(self, parts: list[str]) -> None:
        # |detailschange|p1a: Charizard|Charizard-Mega-X, L50, M
        if len(parts) < 4:
            return
        side_slot = parts[2].split(":")[0].strip()
        species = _species_from_details(parts[3])
        self._active_species[side_slot] = species
        self._name_species[(_side_from_slot(side_slot), _strip_pokemon_name(parts[2]))] = species

    def _species_of(self, raw: str) -> str:
        """Species for an ident like 'p1a: Name': by active slot first, then by (side, nickname)."""
        side_slot = raw.split(":")[0].strip()
        name = _strip_pokemon_name(raw)
        if self._active.get(side_slot) == name and side_slot in self._active_species:
            return self._active_species[side_slot]
        return self._name_species.get((_side_from_slot(side_slot), name), "")

    # --- move ---
    def _handle_move(self, parts: list[str]) -> None:
        # |move|p1a: Ogerpon|Ivy Cudgel|p2a: Torkoal|[anim] Ivy Cudgel Rock
        if len(parts) < 5:
            return
        slot_raw = parts[2]
        side_slot = slot_raw.split(":")[0].strip()
        pokemon_name = _strip_pokemon_name(slot_raw)
        move_name = parts[3]
        target_raw = parts[4] if len(parts) > 4 else ""
        target_name = _strip_pokemon_name(target_raw) if target_raw else ""

        side = _side_from_slot(side_slot)
        username = self._side_to_name.get(side, "")

        # Check for miss/fail flags
        success = True
        for p in parts[5:]:
            if p.strip() in ("[miss]", "[notarget]"):
                success = False
                break

        self._result.moves.append(BattleMoveRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            username=username,
            pokemon_name=pokemon_name,
            species=self._species_of(slot_raw),
            move_name=move_name,
            target_name=target_name,
            success=success,
        ))

        # Store for damage attribution
        self._last_move[side_slot] = move_name
        if target_raw and ":" in target_raw:
            self._last_move_target[side_slot] = target_raw.split(":")[0].strip()

    # --- damage ---
    def _handle_damage(self, parts: list[str]) -> None:
        # |-damage|p1a: Ogerpon|13/100|[from] move: ...|[of] p2a: ...
        if len(parts) < 4:
            return
        slot_raw = parts[2]
        side_slot = slot_raw.split(":")[0].strip()
        defender = _strip_pokemon_name(slot_raw)
        hp_str = parts[3]

        hp_after = _parse_hp(hp_str)
        hp_before = self._hp.get(side_slot, 100.0)
        if hp_after is None:
            return
        damage_pct = round(hp_before - hp_after, 2)

        # Determine attacker + move
        # Check [of] tag to find attacker slot
        attacker = ""
        attacker_species = ""
        move_name = ""
        source_tag = ""
        for p in parts[4:]:
            p = p.strip()
            if p.startswith("[of]"):
                atk_raw = p.replace("[of]", "").strip()
                attacker = _strip_pokemon_name(atk_raw)
                attacker_species = self._species_of(atk_raw)
            if p.startswith("[from]"):
                source_tag = p.replace("[from]", "").strip()

        if not attacker:
            # Try to infer from last move – find the opposing side that last moved
            opp_side = "p2" if side_slot.startswith("p1") else "p1"
            for slot_key, mv in self._last_move.items():
                if slot_key.startswith(opp_side):
                    attacker = self._active.get(slot_key, "")
                    attacker_species = self._active_species.get(slot_key, "")
                    move_name = mv
                    break

        if not move_name and attacker:
            # Find attacker slot to get their last move
            for slot_key, name in self._active.items():
                if name == attacker:
                    move_name = self._last_move.get(slot_key, source_tag or "")
                    break
        if not move_name:
            move_name = source_tag or ""

        dmg = BattleDamageRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            attacker_pokemon=attacker,
            defender_pokemon=defender,
            attacker_species=attacker_species,
            defender_species=self._species_of(slot_raw),
            move_name=move_name,
            hp_before=hp_before,
            hp_after=hp_after,
            damage_pct=damage_pct,
        )
        self._result.damages.append(dmg)

        # Update HP and store pending for possible KO
        self._hp[side_slot] = hp_after
        if hp_after == 0.0:
            self._pending_damage[side_slot] = dmg

    # --- heal ---
    def _handle_heal(self, parts: list[str]) -> None:
        if len(parts) < 4:
            return
        slot_raw = parts[2]
        side_slot = slot_raw.split(":")[0].strip()
        hp_after = _parse_hp(parts[3])
        if hp_after is not None:
            self._hp[side_slot] = hp_after

    # --- faint ---
    def _handle_faint(self, parts: list[str]) -> None:
        # |faint|p1a: Ogerpon
        if len(parts) < 3:
            return
        slot_raw = parts[2]
        side_slot = slot_raw.split(":")[0].strip()
        pokemon_name = _strip_pokemon_name(slot_raw)

        self._result.faints.append(BattleFaintRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            pokemon_name=pokemon_name,
            species=self._species_of(slot_raw),
        ))

        # Resolve KO from pending damage
        pending = self._pending_damage.pop(side_slot, None)
        if pending:
            ko_type = "MOVE"
            move_lower = pending.move_name.lower()
            for key, ktype in KO_TYPE_MAP.items():
                if key.lower() in move_lower:
                    ko_type = ktype
                    break
            self._result.kos.append(BattleKORecord(
                battle_id=self._battle_id,
                turn_no=self._current_turn,
                killer_pokemon=pending.attacker_pokemon,
                victim_pokemon=pokemon_name,
                killer_species=pending.attacker_species,
                victim_species=pending.defender_species,
                move_name=pending.move_name,
                ko_type=ko_type,
            ))

    # --- weather ---
    def _handle_weather(self, parts: list[str]) -> None:
        # |-weather|SunnyDay|[from] ability: Drought|[of] p2a: Torkoal
        if len(parts) < 3:
            return
        weather_name = parts[2]
        if weather_name in ("none", "None"):
            return
        source = ""
        for p in parts[3:]:
            p = p.strip()
            if p.startswith("[of]"):
                source = _strip_pokemon_name(p.replace("[of]", "").strip())
        # upkeep lines: |-weather|SunnyDay|[upkeep]  -> skip
        for p in parts[3:]:
            if "[upkeep]" in p:
                return

        self._result.weathers.append(BattleWeatherRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            weather_name=weather_name,
            source_pokemon=source,
        ))

    # --- status ---
    def _handle_status(self, parts: list[str]) -> None:
        # |-status|p1a: Ogerpon|brn
        if len(parts) < 4:
            return
        pokemon_name = _strip_pokemon_name(parts[2])
        status_code = parts[3].strip()
        self._result.statuses.append(BattleStatusRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            pokemon_name=pokemon_name,
            species=self._species_of(parts[2]),
            status_code=status_code,
        ))

    # --- ability ---
    def _handle_ability(self, parts: list[str]) -> None:
        # |-ability|p1b: Archaludon|Stamina|boost
        if len(parts) < 4:
            return
        pokemon_name = _strip_pokemon_name(parts[2])
        ability_name = parts[3].strip()
        self._result.abilities.append(BattleAbilityRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            pokemon_name=pokemon_name,
            species=self._species_of(parts[2]),
            ability_name=ability_name,
        ))

    # --- tera ---
    def _handle_tera(self, parts: list[str]) -> None:
        # |-terastallize|p1a: Ogerpon|Grass
        if len(parts) < 4:
            return
        pokemon_name = _strip_pokemon_name(parts[2])
        tera_type = parts[3].strip()
        self._result.teras.append(BattleTeraRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            pokemon_name=pokemon_name,
            species=self._species_of(parts[2]),
            tera_type=tera_type,
        ))

    # --- fail / miss ---
    def _handle_fail(self, parts: list[str]) -> None:
        # Mark last move as failed
        if len(parts) < 3:
            return
        slot_raw = parts[2]
        side_slot = slot_raw.split(":")[0].strip()
        if self._result.moves:
            last = self._result.moves[-1]
            if last.pokemon_name == _strip_pokemon_name(slot_raw):
                last.success = False

    # --- win/tie ---
    def _handle_win(self, token: str, parts: list[str]) -> None:
        if token == "win" and len(parts) > 2:
            winner_name = parts[2].strip()
            self._result.battle.winner_name = winner_name
            for bp in self._result.battle_players:
                if bp.username == winner_name:
                    bp.result = "WIN"
                else:
                    bp.result = "LOSS"

    # --- field state snapshot ---
    def _record_field_state(self) -> None:
        fs = BattleFieldStateRecord(
            battle_id=self._battle_id,
            turn_no=self._current_turn,
            p1_left=self._active.get("p1a", ""),
            p1_right=self._active.get("p1b", ""),
            p2_left=self._active.get("p2a", ""),
            p2_right=self._active.get("p2b", ""),
        )
        self._result.field_states.append(fs)

    # ------------------------------------------------------------------
    # Finalize: post-process & fill team slots
    # ------------------------------------------------------------------

    def _finalize(self) -> None:
        b = self._result.battle
        b.battle_id = self._battle_id
        b.replay_path = self._replay_path
        if self._rating:
            b.rating = self._rating

        # Build team slots from preview data. Match by species (not nickname) so nicknamed and
        # form-masked Pokemon ('Urshifu-*') are recognised as leads / sent out.
        lead_species: dict[str, set[str]] = {"p1": set(), "p2": set()}
        for lead in self._result.leads:
            side = self._name_to_side.get(lead.username, "")
            if side and lead.species:
                lead_species[side].add(lead.species)

        for side, pokemons in self._poke_preview.items():
            for idx, name in enumerate(pokemons, start=1):
                sent = _match_species(name, self._switched_species.get(side, set()))
                masked = name.endswith("-*")
                if not masked:
                    status, observed = "listed", name
                elif len(sent) == 1:
                    status, observed = "observed", sent[0]
                else:
                    status, observed = ("ambiguous" if sent else "unobserved"), ""
                self._result.team_slots.append(BattleTeamSlot(
                    battle_id=self._battle_id,
                    player_side=side,
                    slot_no=idx,
                    pokemon_name=name,
                    is_lead=bool(_match_species(name, lead_species.get(side, set()))),
                    species_observed=observed,
                    form_status=status,
                    was_sent_out=bool(sent),
                ))

        # Deduplicate leads (same pokemon can appear twice from preview + start)
        seen_leads = set()
        unique_leads = []
        for lead in self._result.leads:
            key = (lead.username, lead.pokemon_name, lead.lead_slot)
            if key not in seen_leads:
                seen_leads.add(key)
                unique_leads.append(lead)
        self._result.leads = unique_leads


# ---------------------------------------------------------------------------
# Batch Runner
# ---------------------------------------------------------------------------

class BatchParser:
    """
    Parses multiple log files in configurable batch sizes.
    Yields ParsedBattle objects one at a time to keep RAM bounded.
    """

    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self._stats = {
            "total_files": 0,
            "parsed": 0,
            "errors": 0,
        }

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    def parse_files(self, file_paths: list[str]):
        """Generator: yields ParsedBattle for each file."""
        self._stats = {"total_files": len(file_paths), "parsed": 0, "errors": 0}
        batch: list[str] = []
        for fp in file_paths:
            batch.append(fp)
            if len(batch) >= self.batch_size:
                yield from self._process_batch(batch)
                batch = []
        if batch:
            yield from self._process_batch(batch)

    def parse_directory(self, directory: str, pattern: str = "*.log"):
        """Parse all matching files in a directory tree."""
        paths = list(Path(directory).rglob(pattern))
        print(f"[BatchParser] Found {len(paths)} files matching '{pattern}' in '{directory}'")
        yield from self.parse_files([str(p) for p in paths])

    def _process_batch(self, paths: list[str]):
        for fp in paths:
            parsed = self._parse_one(fp)
            if parsed:
                yield parsed

    def _parse_one(self, filepath: str) -> Optional[ParsedBattle]:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                log_text = f.read()
            battle_id = _generate_battle_id(log_text, filepath)
            parser = BattleLogParser(battle_id=battle_id, replay_path=filepath)
            result = parser.parse(log_text)
            self._stats["parsed"] += 1
            return result
        except Exception as e:
            self._stats["errors"] += 1
            print(f"[ERROR] Failed to parse {filepath}: {e}")
            return None

    def parse_text(self, log_text: str, battle_id: Optional[str] = None) -> ParsedBattle:
        """Parse a single log string directly (useful for testing)."""
        bid = battle_id or _generate_battle_id(log_text)
        parser = BattleLogParser(battle_id=bid)
        return parser.parse(log_text)


# ---------------------------------------------------------------------------
# In-Memory "Database" for inspection
# ---------------------------------------------------------------------------

class InMemoryDB:
    """
    Stores parsed results as lists of dicts matching the SQL schema.
    Allows inspection of data before export.
    """

    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "battle": [],
            "battle_players": [],
            "players": [],
            "battle_team_slot": [],
            "battle_leads": [],
            "battle_move": [],
            "battle_damage": [],
            "battle_ko": [],
            "battle_faint": [],
            "battle_switch": [],
            "battle_weather": [],
            "battle_status": [],
            "battle_ability": [],
            "battle_tera": [],
            "battle_field_state": [],
        }
        self._player_cache = set()
    def ingest(self, parsed: ParsedBattle) -> None:
        """Ingest a ParsedBattle into the in-memory tables."""
        battle = parsed.battle

        # Resolve player IDs
        for pl in parsed.players:
            if pl.username not in self._player_cache:
                self._player_cache.add(pl.username)
                self.tables["players"].append({
                    "username": pl.username
                })

        # battle
        self.tables["battle"].append({
            "battle_id": battle.battle_id,
            "format": battle.format,
            "format_id": battle.format_id,
            "upload_time": battle.upload_time,
            "rating": battle.rating,
            "winner_name": battle.winner_name,
            "replay_path": battle.replay_path,
            "turn_count": battle.turn_count,
        })

        # battle_players
        for bp in parsed.battle_players:
            if battle.winner_name:
                bp.result = "WIN" if bp.username == battle.winner_name else "LOSS"
            self.tables["battle_players"].append({
                "battle_id": bp.battle_id,
                "username": bp.username,
                "side": bp.side,
                "rating_before": bp.rating_before,
                "rating_after": bp.rating_after,
                "result": bp.result,
            })

        # battle_team_slot
        for ts in parsed.team_slots:
            self.tables["battle_team_slot"].append({
                "battle_id": ts.battle_id,
                "player_side": ts.player_side,
                "slot_no": ts.slot_no,
                "pokemon_name": ts.pokemon_name,
                "is_lead": int(ts.is_lead),
                "species_observed": ts.species_observed,
                "form_status": ts.form_status,
                "was_sent_out": int(ts.was_sent_out),
            })

        # battle_leads
        for lead in parsed.leads:
            self.tables["battle_leads"].append({
                "battle_id": lead.battle_id,
                "username": lead.username,
                "pokemon_name": lead.pokemon_name,
                "species": lead.species,
                "lead_slot": lead.lead_slot,
            })

        # battle_move
        for mv in parsed.moves:
            self.tables["battle_move"].append({
                "battle_id": mv.battle_id,
                "turn_no": mv.turn_no,
                "username":mv.username,
                "pokemon_name": mv.pokemon_name,
                "species": mv.species,
                "move_name": mv.move_name,
                "target_name": mv.target_name,
                "success": int(mv.success),
            })

        # battle_damage
        for dmg in parsed.damages:
            self.tables["battle_damage"].append({
                "battle_id": dmg.battle_id,
                "turn_no": dmg.turn_no,
                "attacker_pokemon": dmg.attacker_pokemon,
                "defender_pokemon": dmg.defender_pokemon,
                "attacker_species": dmg.attacker_species,
                "defender_species": dmg.defender_species,
                "move_name": dmg.move_name,
                "hp_before": dmg.hp_before,
                "hp_after": dmg.hp_after,
                "damage_pct": dmg.damage_pct,
            })

        # battle_ko
        for ko in parsed.kos:
            self.tables["battle_ko"].append({
                "battle_id": ko.battle_id,
                "turn_no": ko.turn_no,
                "killer_pokemon": ko.killer_pokemon,
                "victim_pokemon": ko.victim_pokemon,
                "killer_species": ko.killer_species,
                "victim_species": ko.victim_species,
                "move_name": ko.move_name,
                "ko_type": ko.ko_type,
            })

        # battle_faint
        for f in parsed.faints:
            self.tables["battle_faint"].append({
                "battle_id": f.battle_id,
                "turn_no": f.turn_no,
                "pokemon_name": f.pokemon_name,
                "species": f.species,
            })

        # battle_switch
        for sw in parsed.switches:
            self.tables["battle_switch"].append({
                "battle_id": sw.battle_id,
                "turn_no": sw.turn_no,
                "username": sw.username,
                "pokemon_name": sw.pokemon_name,
                "species": sw.species,
            })

        # battle_weather
        for w in parsed.weathers:
            self.tables["battle_weather"].append({
                "battle_id": w.battle_id,
                "turn_no": w.turn_no,
                "weather_name": w.weather_name,
                "source_pokemon": w.source_pokemon,
            })

        # battle_status
        for st in parsed.statuses:
            self.tables["battle_status"].append({
                "battle_id": st.battle_id,
                "turn_no": st.turn_no,
                "pokemon_name": st.pokemon_name,
                "species": st.species,
                "status_code": st.status_code,
            })

        # battle_ability
        for ab in parsed.abilities:
            self.tables["battle_ability"].append({
                "battle_id": ab.battle_id,
                "turn_no": ab.turn_no,
                "pokemon_name": ab.pokemon_name,
                "species": ab.species,
                "ability_name": ab.ability_name,
            })

        # battle_tera
        for te in parsed.teras:
            self.tables["battle_tera"].append({
                "battle_id": te.battle_id,
                "turn_no": te.turn_no,
                "pokemon_name": te.pokemon_name,
                "species": te.species,
                "tera_type": te.tera_type,
            })

        # battle_field_state
        for fs in parsed.field_states:
            self.tables["battle_field_state"].append({
                "battle_id": fs.battle_id,
                "turn_no": fs.turn_no,
                "p1_left": fs.p1_left,
                "p1_right": fs.p1_right,
                "p2_left": fs.p2_left,
                "p2_right": fs.p2_right,
            })

    def row_counts(self) -> dict[str, int]:
        return {t: len(rows) for t, rows in self.tables.items()}

    def export_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.tables, f, indent=2, default=str)
        print(f"[Export] JSON written to {path}")

    def export_sql_inserts(self, path: str) -> None:
        """Export as SQL INSERT statements, safe for MySQL."""
        def escape(v):
            if v is None:
                return "NULL"
            if isinstance(v, bool):
                return "1" if v else "0"
            if isinstance(v, (int, float)):
                return str(v)
            s = str(v).replace("\\", "\\\\").replace("'", "\\'")
            return f"'{s}'"

        with open(path, "w", encoding="utf-8") as f:
            f.write("SET FOREIGN_KEY_CHECKS=0;\n\n")
            for table, rows in self.tables.items():
                if not rows:
                    continue
                cols = list(rows[0].keys())
                col_str = ", ".join(f"`{c}`" for c in cols)
                f.write(f"-- Table: {table}\n")
                for row in rows:
                    vals = ", ".join(escape(row.get(c)) for c in cols)
                    f.write(f"INSERT INTO `{table}` ({col_str}) VALUES ({vals});\n")
                f.write("\n")
            f.write("SET FOREIGN_KEY_CHECKS=1;\n")
        print(f"[Export] SQL written to {path}")