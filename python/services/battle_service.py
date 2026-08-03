from python.calculations.damage_calc_v2 import calculate_damage

class BattleService:
    @staticmethod
    def calculate_damage(attacker, defender, move, type_chart_df):
        return calculate_damage(
            attacker,
            defender,
            move,
            type_chart_df
        )