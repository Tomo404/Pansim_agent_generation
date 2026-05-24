from __future__ import annotations

from pathlib import Path
import pandas as pd


# ============================================================
# ITT MÓDOSÍTSD, ha máshol vannak a fájlok
# ============================================================
INPUT_AGGREGATED = Path("data/processed/demographics_with_feor.csv")
INPUT_WORKER_SLOTS = Path("data/processed/worker_slots.csv")


KEY_COLS = [
    "county",
    "teaor_code",
    "teaor_name",
    "gender",
    "age_group",
    "education",
    "feor_code",
]


def load_aggregated() -> pd.DataFrame:
    df = pd.read_csv(INPUT_AGGREGATED, encoding="utf-8-sig", dtype={"feor_code": str})
    df = df[KEY_COLS + ["count"]].copy()
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    return df


def load_and_reaggregate_worker_slots() -> pd.DataFrame:
    df = pd.read_csv(INPUT_WORKER_SLOTS, encoding="utf-8-sig", dtype={"feor_code": str})

    required = set(KEY_COLS + ["worker_slot_id"])
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Hiányzó oszlop(ok) a worker_slots.csv-ben: {missing}")

    grouped = (
        df.groupby(KEY_COLS, as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )

    grouped["count"] = grouped["count"].astype(int)
    return grouped


def compare_tables(original_df: pd.DataFrame, regenerated_df: pd.DataFrame) -> pd.DataFrame:
    merged = original_df.merge(
        regenerated_df,
        on=KEY_COLS,
        how="outer",
        suffixes=("_original", "_regenerated"),
    )

    merged["count_original"] = merged["count_original"].fillna(0).astype(int)
    merged["count_regenerated"] = merged["count_regenerated"].fillna(0).astype(int)
    merged["diff"] = merged["count_regenerated"] - merged["count_original"]

    return merged


def main() -> None:
    print("Loading original aggregated table...")
    original_df = load_aggregated()

    print("Loading worker slots and re-aggregating...")
    regenerated_df = load_and_reaggregate_worker_slots()

    print("\n==============================")
    print("TOTAL CHECK")
    print("==============================")
    total_original = int(original_df["count"].sum())
    total_regenerated = int(regenerated_df["count"].sum())

    print(f"Original total:    {total_original:,}")
    print(f"Regenerated total: {total_regenerated:,}")
    print(f"Difference:        {total_regenerated - total_original:,}")

    print("\n==============================")
    print("ROW-LEVEL COMPARISON")
    print("==============================")

    comparison = compare_tables(original_df, regenerated_df)

    mismatch_df = comparison[comparison["diff"] != 0].copy()

    print(f"Original aggregated rows:    {len(original_df):,}")
    print(f"Re-aggregated rows:         {len(regenerated_df):,}")
    print(f"Compared rows (outer join): {len(comparison):,}")
    print(f"Mismatching rows:           {len(mismatch_df):,}")

    if mismatch_df.empty:
        print("\n✅ PERFECT MATCH: a worker_slots.csv visszaadja az aggregált inputot.")
    else:
        print("\n⚠️ VAN ELTÉRÉS.")
        print(f"Max abs difference: {mismatch_df['diff'].abs().max():,}")

        print("\nTop 20 mismatches:")
        top_mismatch = mismatch_df.reindex(
            mismatch_df["diff"].abs().sort_values(ascending=False).index
        ).head(20)

        print(
            top_mismatch[
                KEY_COLS + ["count_original", "count_regenerated", "diff"]
            ].to_string(index=False)
        )

    print("\n==============================")
    print("QUICK SANITY CHECKS")
    print("==============================")
    print(f"Unique counties:     {original_df['county'].nunique()}")
    print(f"Unique TEÁOR codes:  {original_df['teaor_code'].nunique()}")
    print(f"Unique FEOR codes:   {original_df['feor_code'].nunique()}")

    print("\nDone.")


if __name__ == "__main__":
    main()