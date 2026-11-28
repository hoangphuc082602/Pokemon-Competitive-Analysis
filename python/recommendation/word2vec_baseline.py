"""Word2Vec teammate-embedding baseline (#48).

A baseline for the v2.0 recommendation evaluation (#46), not a validated
recommender. Training takes the team sequences to learn from (e.g. the train
split only); reading Parquet and saving the model stay in the CLI
(``src/train_word2vec.py``). Nothing runs on import.
"""
from collections.abc import Iterable, Sequence

from gensim.models import Word2Vec


def train_word2vec(
    teams: Iterable[Sequence[str]],
    *,
    vector_size: int = 128,
    window: int = 6,
    min_count: int = 100,
    sg: int = 1,
    workers: int = 8,
    epochs: int = 10,
) -> Word2Vec:
    """Train Word2Vec on ``teams`` (one list of Pokémon names per team).

    ``teams`` must be re-iterable (a list or an object whose ``__iter__``
    starts a fresh pass, like ``TeamGenerator``): the vocabulary and the
    training each read the whole corpus. The defaults are the current
    baseline's hyper-parameters.
    """
    if iter(teams) is teams:
        raise TypeError(
            "teams must be re-iterable (got a one-shot iterator): "
            "build_vocab and train each need a full pass"
        )

    model = Word2Vec(
        vector_size=vector_size,
        window=window,
        min_count=min_count,
        workers=workers,
        sg=sg,
    )

    print("Building vocab...")
    model.build_vocab(teams)
    print(f"Vocabulary size: {len(model.wv)}")

    print("Training...")
    model.train(teams, total_examples=model.corpus_count, epochs=epochs)
    return model
