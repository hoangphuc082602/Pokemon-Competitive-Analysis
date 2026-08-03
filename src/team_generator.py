import pyarrow.dataset as ds

class TeamGenerator:

    def __init__(self, parquet_path):

        self.parquet_path = parquet_path

    def __iter__(self):

        dataset = ds.dataset(
            self.parquet_path,
            format="parquet"
        )

        scanner = dataset.scanner(
            columns=[
                "battle_id",
                "player_side",
                "slot_no",
                "pokemon_name"
            ],
            batch_size=50000
        )

        current_key = None
        current_team = []

        for batch in scanner.to_batches():

            df = batch.to_pandas()

            df = df.sort_values(
                [
                    "battle_id",
                    "player_side",
                    "slot_no"
                ]
            )

            for row in df.itertuples():

                key = (
                    row.battle_id,
                    row.player_side
                )

                if current_key is None:
                    current_key = key

                if key != current_key:

                    if len(current_team) > 0:
                        yield current_team

                    current_team = []
                    current_key = key

                current_team.append(
                    row.pokemon_name
                )

        if current_team:
            yield current_team