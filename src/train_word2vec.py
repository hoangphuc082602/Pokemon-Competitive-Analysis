"""CLI: train the Word2Vec baseline on the whole team-slot Parquet and save it.

Run from the repository root: ``python src/train_word2vec.py`` (or
``python -m src.train_word2vec``). Training itself is
``python.recommendation.word2vec_baseline.train_word2vec``; nothing runs on import.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # run as a script: only src/ is on sys.path
    sys.path.append(str(ROOT))

from python.recommendation.word2vec_baseline import train_word2vec  # noqa: E402
from src.team_generator import TeamGenerator  # noqa: E402

PARQUET_PATH = "data/output/battle_team_slot.parquet"
MODEL_PATH = "models/pokemon_embedding.model"


def main(parquet_path: str = PARQUET_PATH, model_path: str = MODEL_PATH) -> None:
    model = train_word2vec(TeamGenerator(parquet_path))
    model.save(model_path)
    print("Done")


if __name__ == "__main__":
    main()
