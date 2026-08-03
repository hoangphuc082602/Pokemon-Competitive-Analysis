from python.services.battle_service import (
    BattleService
)

class BattleSimulator:

    @staticmethod
    def simulate_turn(
        attacker,
        defender,
        move,
        type_chart_df
    ):

        result = (
            BattleService.run_damage_calc(
                attacker,
                defender,
                move,
                type_chart_df
            )
        )

        return result