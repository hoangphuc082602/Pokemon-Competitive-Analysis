from gensim.models import Word2Vec

model = Word2Vec.load(
    "models/pokemon_embedding.model"
)

result = model.wv.most_similar(
    "Flutter M ane",
    topn=20
)

for pokemon, score in result:

    print(
        pokemon,
        round(score,4)
    )