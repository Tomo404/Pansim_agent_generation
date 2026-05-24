from __future__ import annotations

from pathlib import Path
import pandas as pd


INPUT_AGENTS_WITH_WORKPLACES = Path("data/processed/agents_with_workplaces.csv")
OUTPUT_DIR = Path("data/validation")


def main() -> None:
    print(f"Reading: {INPUT_AGENTS_WITH_WORKPLACES}")

    df = pd.read_csv(
        INPUT_AGENTS_WITH_WORKPLACES,
        encoding="utf-8-sig",
        dtype={"feor_code": str}
    )

    assigned = df[df["workplace_id"].notna() & (df["workplace_id"] != "")].copy()
    missing = df[df["workplace_id"].isna() | (df["workplace_id"] == "")].copy()

    print("\n==============================")
    print("ASSIGNMENT TOTALS")
    print("==============================")
    print(f"Total agents:       {len(df):,}")
    print(f"Assigned agents:    {len(assigned):,}")
    print(f"Missing assignment: {len(missing):,}")
    print(f"Missing ratio:      {len(missing) / len(df):.4%}")

    assigned["is_male"] = (assigned["gender"] == "Férfi").astype(int)
    assigned["is_female"] = (assigned["gender"] == "Nő").astype(int)

    workplace_summary = (
        assigned.groupby(
            ["workplace_id", "workplace_settlement", "teaor_code", "workplace_size"],
            as_index=False
        )
        .agg(
            assigned_workers=("agent_id", "count"),
            male_workers=("is_male", "sum"),
            female_workers=("is_female", "sum"),
            unique_feor=("feor_code", "nunique"),
            unique_education=("education", "nunique"),
        )
    )

    workplace_summary["size_diff"] = (
        workplace_summary["assigned_workers"] - workplace_summary["workplace_size"]
    )

    print("\n==============================")
    print("WORKPLACE SIZE CHECK")
    print("==============================")
    print(f"Workplaces with assigned agents: {len(workplace_summary):,}")
    print(f"Total assigned workers:          {workplace_summary['assigned_workers'].sum():,}")
    print(f"Total workplace capacity used:   {workplace_summary['workplace_size'].sum():,}")

    mismatch = workplace_summary[workplace_summary["size_diff"] != 0].copy()

    print(f"Workplaces with size mismatch:   {len(mismatch):,}")

    if mismatch.empty:
        print("✅ Perfect workplace capacity match for assigned workplaces.")
    else:
        print("\nTop workplace size mismatches:")
        print(
            mismatch.sort_values("size_diff", key=lambda s: s.abs(), ascending=False)
            .head(20)
            .to_string(index=False)
        )

    print("\n==============================")
    print("TOP WORKPLACES BY ASSIGNED WORKERS")
    print("==============================")
    print(
        workplace_summary.sort_values("assigned_workers", ascending=False)
        .head(20)
        .to_string(index=False)
    )

    teaor_summary = (
        assigned.groupby("teaor_code", as_index=False)
        .agg(
            assigned_workers=("agent_id", "count"),
            unique_workplaces=("workplace_id", "nunique"),
            unique_feor=("feor_code", "nunique"),
        )
        .sort_values("assigned_workers", ascending=False)
    )

    county_summary = (
        assigned.groupby("county", as_index=False)
        .agg(
            assigned_workers=("agent_id", "count"),
            unique_workplaces=("workplace_id", "nunique"),
            unique_feor=("feor_code", "nunique"),
        )
        .sort_values("assigned_workers", ascending=False)
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    workplace_summary.to_csv(
        OUTPUT_DIR / "workplace_inverse_summary.csv",
        index=False,
        encoding="utf-8-sig"
    )

    teaor_summary.to_csv(
        OUTPUT_DIR / "workplace_inverse_by_teaor.csv",
        index=False,
        encoding="utf-8-sig"
    )

    county_summary.to_csv(
        OUTPUT_DIR / "workplace_inverse_by_county.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n==============================")
    print("SAVED")
    print("==============================")
    print("Saved:")
    print(OUTPUT_DIR / "workplace_inverse_summary.csv")
    print(OUTPUT_DIR / "workplace_inverse_by_teaor.csv")
    print(OUTPUT_DIR / "workplace_inverse_by_county.csv")

    print("\nDone.")


if __name__ == "__main__":
    main()