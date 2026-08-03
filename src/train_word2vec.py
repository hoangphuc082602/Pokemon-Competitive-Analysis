from gensim.models import Word2Vec
from team_generator import TeamGenerator

generator = TeamGenerator(
    "data/output/battle_team_slot.parquet"
)

model = Word2Vec(
    vector_size=128,
    window=6,
    min_count=100,
    workers=8,
    sg=1
)

print("Building vocab...")

model.build_vocab(generator)

print(
    f"Vocabulary size: "
    f"{len(model.wv)}"
)

generator = TeamGenerator(
    "data/output/battle_team_slot.parquet"
)

print("Training...")

model.train(
    generator,
    total_examples=model.corpus_count,
    epochs=10
)

model.save(
    "models/pokemon_embedding.model"
)

print("Done")