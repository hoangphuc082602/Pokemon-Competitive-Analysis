from python.models.team_builder import build_pokemon

class PokemonService:
    @staticmethod
    def create_pokemon(pokemon_df,
    nature_df,
    pokemon_name,
    level,
    nature,
    ability,
    item,
    moves,
    ivs,
    evs):
        return build_pokemon(
            pokemon_df,
            nature_df,
            pokemon_name,
            level,
            nature,
            ability,
            item,
            moves,
            ivs,
            evs
        )
