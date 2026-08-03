import pandas as pd

# =====================================================
# DEFENSIVE ABILITIES
# =====================================================

DEFENSIVE_ABILITY_IMMUNITIES = {
    "levitate": ["ground"],
    "flash-fire": ["fire"],
    "water-absorb": ["water"],
    "volt-absorb": ["electric"],
    "lightning-rod": ["electric"],
    "motor-drive": ["electric"],
    "sap-sipper": ["grass"],
    "storm-drain": ["water"],
    "dry-skin": ["water"],
    "earth-eater": ["ground"],
    "well-baked-body": ["fire"],
    "wind-rider": ["flying"]
}

DEFENSIVE_ABILITY_RESISTANCES = {
    "thick-fat": {
        "fire": 0.5,
        "ice": 0.5
    },
    "heatproof": {
        "fire": 0.5
    },
    "purifying-salt": {
        "ghost": 0.5
    }
}

# =====================================================
# OFFENSIVE ABILITIES
# =====================================================

OFFENSIVE_ABILITY_BYPASS = {

    "scrappy": {
        "normal": ["ghost"],
        "fighting": ["ghost"]
    },

    "mold-breaker": {}
}

OFFENSIVE_TYPE_OVERRIDE = {
    "normalize": "normal",
    "pixilate": "fairy",
    "refrigerate": "ice",
    "aerilate": "flying",
    "galvanize": "electric"
}

# =====================================================
# SHARED HELPERS
# =====================================================

def get_pokemon_types(
    pokemon_df,
    pokemon_name
):

    row = pokemon_df[
        pokemon_df["pokemon"]
        ==
        pokemon_name
    ]

    if row.empty:
        return []

    row = row.iloc[0]

    return [
        t.lower()
        for t in [
            row["type_1"],
            row["type_2"]
        ]
        if pd.notna(t)
    ]


def _lookup_effectiveness(
    type_chart_df,
    attack_type,
    defense_type
):

    result = type_chart_df[
        (type_chart_df["attack_type"] == attack_type.lower())
        &
        (type_chart_df["defense_type"] == defense_type.lower())
    ]

    if result.empty:
        return 1.0
    return float(
        result.iloc[0]["multiplier"]
    )

# =====================================================
# DEFENSIVE
# =====================================================

def calculate_defensive_multiplier(
    type_chart_df,
    pokemon_df,
    attacking_type,
    defender,
    ignore_defender_ability=False
):

    attacking_type = attacking_type.lower()

    defender_types = get_pokemon_types(
        pokemon_df,
        defender["pokemon"]
    )

    ability = (
        defender
        .get("ability", "")
        .lower()
    )

    # Ability Immunity

    if not ignore_defender_ability:
        immune_types = (
            DEFENSIVE_ABILITY_IMMUNITIES
            .get(
                ability,
                []
            )
        )
        if attacking_type in immune_types:
            return 0.0

    multiplier = 1

    for defense_type in defender_types:
        multiplier *= (
            _lookup_effectiveness(
                type_chart_df,
                attacking_type,
                defense_type
            )
        )

    if multiplier == 0:
        return 0

    # Ability Resistance

    if not ignore_defender_ability:
        resist_map = (
            DEFENSIVE_ABILITY_RESISTANCES
            .get(
                ability,
                {}
            )
        )

        if attacking_type in resist_map:
            multiplier *= (
                resist_map[
                    attacking_type
                ]
            )

    return round(multiplier,2)


def analyze_team_defense(
    type_chart_df,
    pokemon_df,
    team
):

    assert isinstance(team, list)

    all_types = sorted(
        type_chart_df["attack_type"]
        .unique()
        .tolist()
    )

    by_pokemon = {}

    for mon in team:
        assert isinstance(mon, dict)
        pokemon_name = mon["pokemon"]
        by_pokemon[pokemon_name] = {
            attack_type:
            calculate_defensive_multiplier(
                type_chart_df,
                pokemon_df,
                attack_type,
                mon
            )
            for attack_type in all_types
        }

    by_type = {}

    for attack_type in all_types:
        buckets = {
            "4x": 0,
            "2x": 0,
            "1x": 0,
            "0.5x": 0,
            "0.25x": 0,
            "0x": 0
        }

        for mon in team:
            pokemon_name = mon["pokemon"]

            multiplier = (
                by_pokemon[pokemon_name]
                [
                    attack_type
                ]
            )

            if multiplier >= 4:
                buckets["4x"] += 1
            elif multiplier == 2:
                buckets["2x"] += 1
            elif multiplier == 1:
                buckets["1x"] += 1
            elif multiplier == 0.5:
                buckets["0.5x"] += 1
            elif multiplier == 0.25:
                buckets["0.25x"] += 1
            elif multiplier == 0:
                buckets["0x"] += 1

        net = (
            buckets["4x"] * 2
            +
            buckets["2x"]
        ) - (
            buckets["0.5x"]
            +
            buckets["0.25x"] * 2
            +
            buckets["0x"] * 2
        )

        by_type[attack_type] = {
            **buckets,
            "net": net
        }

    return {
        "by_pokemon":by_pokemon,

        "by_type":by_type,

        "summary": {
            "4x_weaknesses": [
                t
                for t in all_types
                if by_type[t]["4x"] > 0
            ],

            "well_covered": [
                t
                for t in all_types
                if (
                    by_type[t]["2x"] == 0
                    and
                    by_type[t]["4x"] == 0
                )
            ]
        }
    }

# OFFENSIVE
def get_move_type(
    moves_df,
    move_name
):

    row = moves_df[
        moves_df["move_name"]
        ==
        move_name.lower()
    ]

    if row.empty:
        return None
    return str(
        row.iloc[0]["type"]
    ).lower()

def resolve_move_types(
    moves_df,
    pokemon
):

    ability = (
        pokemon
        .get(
            "ability",
            ""
        )
        .lower()
    )
    override_type = (
        OFFENSIVE_TYPE_OVERRIDE
        .get(
            ability
        )
    )

    result = []

    for move in pokemon["moves"]:
        move_type = (
            get_move_type(
                moves_df,
                move
            )
        )
        if move_type is None:
            continue

        if ability == "normalize":
            move_type = "normal"
        elif (
            override_type
            and
            move_type == "normal"
        ):
            move_type = override_type
        result.append(
            move_type
        )

    return result


def analyze_pokemon_offense(
    type_chart_df,
    moves_df,
    pokemon
):

    all_types = sorted(
        type_chart_df["attack_type"]
        .unique()
        .tolist()
    )

    move_types = (
        resolve_move_types(
            moves_df,
            pokemon
        )
    )

    result = {}

    for defending_type in all_types:
        covered = False
        for move_type in move_types:
            multiplier = (
                _lookup_effectiveness(
                    type_chart_df,
                    move_type,
                    defending_type
                )
            )
            if multiplier >= 2:
                covered = True
                break
        result[
            defending_type
        ] = covered
    return result


def analyze_team_offense(
    type_chart_df,
    moves_df,
    team
):
    all_types = sorted(
        type_chart_df["attack_type"]
        .unique()
        .tolist()
    )

    by_pokemon = {
        mon["pokemon"]:
        analyze_pokemon_offense(
            type_chart_df,
            moves_df,
            mon
        )
        for mon in team
    }

    by_type = {}

    for defense_type in all_types:
        can_hit = [
            mon["pokemon"]
            for mon in team
            if by_pokemon[mon["pokemon"]]
            [
                defense_type
            ]
        ]

        cannot_hit = [
            mon["pokemon"]
            for mon in team
            if not by_pokemon[mon["pokemon"]]
            [
                defense_type
            ]
        ]

        by_type[
            defense_type
        ] = {
            "can_hit":
            can_hit,
            "cannot_hit":
            cannot_hit,
            "coverage_count":
            len(can_hit),
            "is_covered":
            len(can_hit) > 0
        }

    covered = [
        t
        for t in all_types
        if by_type[t]["is_covered"]
    ]

    not_covered = [
        t
        for t in all_types
        if not by_type[t]["is_covered"]
    ]

    return {

        "by_pokemon":by_pokemon,
        "by_type":by_type,

        "summary": {
            "covered_types":covered,
            "not_covered_types":not_covered,
            "coverage_count":len(covered),
            "not_covered_count":len(not_covered)
        }
    }