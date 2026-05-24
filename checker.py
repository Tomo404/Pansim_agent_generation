import pandas as pd

df = pd.read_csv("data/processed/worker_slots.csv", encoding="utf-8-sig")
print(df.columns)
print(df.loc[df["teaor_code"].isin(["E", "O", "T"]), ["teaor_code", "teaor_name"]].drop_duplicates())