class BattleState:
    def __init__(self):
        self.turn = 0
        self.active = {
            "p1a": None,
            "p1b": None,
            "p2a": None,
            "p2b": None
        }

        self.hp = {}
        self.last_move = None
        self.last_attacker = None
        self.last_targets = []
        self.weather = None
        self.leads_recorded = False
        self.team_slot_counter = {
            "p1": 0,
            "p2": 0
        }