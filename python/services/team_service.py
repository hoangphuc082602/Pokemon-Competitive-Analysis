import pandas as pd
from sqlalchemy import text

from python.database.db_connection import (
    engine
)

def load_team(
    team_name
):

    query = """
    SELECT
        tp.team_pokemon_id,
        tp.pokemon_name,
        tp.ability,
        tp.item,
        tp.nature,
        tp.level,

        ev.hp as hp_ev,
        ev.atk as atk_ev,
        ev.def as def_ev,
        ev.spatk as spatk_ev,
        ev.spdef as spdef_ev,
        ev.spe as spe_ev,

        iv.hp as hp_iv,
        iv.atk as atk_iv,
        iv.def as def_iv,
        iv.spatk as spatk_iv,
        iv.spdef as spdef_iv,
        iv.spe as spe_iv

    FROM team_pokemon tp

    LEFT JOIN team_pokemon_evs ev
        ON tp.team_pokemon_id =
        ev.team_pokemon_id

    LEFT JOIN team_pokemon_ivs iv
        ON tp.team_pokemon_id =
        iv.team_pokemon_id

    JOIN team_master tm
        ON tp.team_id = tm.team_id

    WHERE tm.team_name = :team_name

    ORDER BY tp.slot
    """

    members_df = pd.read_sql(
        text(query),
        engine,
        params={
            "team_name": team_name
        }
    )

    team = []

    for _, row in members_df.iterrows():

        moves_query = """
        SELECT
            move_name
        FROM team_pokemon_moves
        WHERE team_pokemon_id = :id
        ORDER BY move_slot
        """

        moves = pd.read_sql(
            text(moves_query),
            engine,
            params={
                "id":
                    row["team_pokemon_id"]
            }
        )

        pokemon = {

            "pokemon":
                row["pokemon_name"],
            "ability":
                row["ability"],
            "item":
                row["item"],
            "nature":
                row["nature"],
            "level":
                row["level"],
            "moves":
                moves["move_name"]
                .tolist(),

            "ivs": {
                "hp":row["hp_iv"],
                "atk":row["atk_iv"],
                "def":row["def_iv"],
                "spatk":row["spatk_iv"],
                "spdef":row["spdef_iv"],
                "spe":row["spe_iv"]
            },

            "evs": {
                "hp":row["hp_ev"],
                "atk":row["atk_ev"],
                "def":row["def_ev"],
                "spatk":row["spatk_ev"],
                "spdef":row["spdef_ev"],
                "spe":row["spe_ev"]
            }
        }
        team.append(
            pokemon
        )

    return team

def load_team_by_name(
    team_name
):

    query = """
    SELECT
        team_id
    FROM team_master
    WHERE team_name = :team_name
    """

    df = pd.read_sql(
        text(query),
        engine,
        params={
            "team_name":
                team_name
        }
    )

    if df.empty:
        return None

    team_id = (df.iloc[0]["team_id"])
    return load_team(team_id)

def save_team(
    team_name,
    team
):

    conn = engine.connect()
    trans = conn.begin()

    try:
        result = conn.execute(
            text(
                """
                INSERT INTO team_master
                (team_name)
                VALUES
                (:team_name)
                """
            ),
            {
                "team_name": team_name
            }
        )

        team_id = result.lastrowid

        for slot, pokemon in enumerate(
            team,
            start=1
        ):

            result = conn.execute(
                text(
                    """
                    INSERT INTO team_pokemon
                    (
                        team_id,
                        pokemon_name,
                        slot,
                        ability,
                        item,
                        nature,
                        level
                    )
                    VALUES
                    (
                        :team_id,
                        :pokemon_name,
                        :slot,
                        :ability,
                        :item,
                        :nature,
                        :level
                    )
                    """
                ),
                {
                    "team_id": team_id,
                    "pokemon_name": pokemon["pokemon"],
                    "slot": slot,
                    "ability": pokemon["ability"],
                    "item": pokemon["item"],
                    "nature": pokemon["nature"],
                    "level": pokemon.get(
                            "level",
                            50
                        )
                }
            )

            team_pokemon_id = result.lastrowid

            for move_slot, move in enumerate(
                pokemon["moves"],
                start=1
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO team_pokemon_moves
                        (
                            team_pokemon_id,
                            move_name,
                            move_slot
                        )
                        VALUES
                        (
                            :team_pokemon_id,
                            :move_name,
                            :move_slot
                        )
                        """
                    ),
                    {
                        "team_pokemon_id":team_pokemon_id,
                        "move_name":move,
                        "move_slot":move_slot
                    }
                )

            conn.execute(
                text(
                    """
                    INSERT INTO team_pokemon_evs
                    (
                        team_pokemon_id,
                        hp,
                        atk,
                        def,
                        spatk,
                        spdef,
                        spe
                    )
                    VALUES
                    (
                        :team_pokemon_id,
                        :hp_ev,
                        :atk_ev,
                        :def_ev,
                        :spatk_ev,
                        :spdef_ev,
                        :spe_ev
                    )
                    """
                ),
                {
                    "team_pokemon_id":team_pokemon_id,
                    "hp_ev":pokemon["evs"]["hp"],
                    "atk_ev":pokemon["evs"]["atk"],
                    "def_ev":pokemon["evs"]["def"],
                    "spatk_ev":pokemon["evs"]["spatk"],
                    "spdef_ev":pokemon["evs"]["spdef"],
                    "spe_ev":pokemon["evs"]["spe"]
                }
            )

            # IVS
            conn.execute(
                text(
                    """
                    INSERT INTO team_pokemon_ivs
                    (
                        team_pokemon_id,
                        hp,
                        atk,
                        def,
                        spatk,
                        spdef,
                        spe
                    )
                    VALUES
                    (
                        :team_pokemon_id,
                        :hp_iv,
                        :atk_iv,
                        :def_iv,
                        :spatk_iv,
                        :spdef_iv,
                        :spe_iv
                    )
                    """
                ),
                {
                    "team_pokemon_id":team_pokemon_id,
                    "hp_iv":pokemon["ivs"]["hp"],
                    "atk_iv":pokemon["ivs"]["atk"],
                    "def_iv":pokemon["ivs"]["def"],
                    "spatk_iv":pokemon["ivs"]["spatk"],
                    "spdef_iv":pokemon["ivs"]["spdef"],
                    "spe_iv":pokemon["ivs"]["spe"]
                }
            )

        trans.commit()
        return team_id

    except Exception as e:

        trans.rollback()
        raise e
    finally:
        conn.close()