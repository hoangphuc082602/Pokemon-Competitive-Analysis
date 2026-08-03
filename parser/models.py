from dataclasses import dataclass, field

@dataclass
class ParsedBattle:

    battle = {}

    battle_players = field(default_factory=list)
    battle_teams = field(default_factory=list)
    battle_moves = field(default_factory=list)
    battle_switches = field(default_factory=list)
    battle_faints = field(default_factory=list)
    battle_teras = field(default_factory=list)
    battle_kos = field(default_factory=list)