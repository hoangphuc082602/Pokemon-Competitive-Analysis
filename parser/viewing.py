import pandas as pd

df = pd.read_parquet("data/output/battle_faint.parquet")

print(df.iloc[0].to_dict())