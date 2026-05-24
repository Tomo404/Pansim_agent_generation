from __future__ import annotations

from pathlib import Path
import pandas as pd

INPUT_FILE = Path("data/processed/agents_with_workplaces.csv")
OUTPUT_FILE = Path("data/validation/missing_assignment_summary.csv")


def main() -> None:
    print(f"Reading: {INPUT_FILE}")

    df = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8-sig",
        dtype={"feor_code": str},
    )

    missing = df[df["workplace_id"].isna() | (df["workplace_id"] == "")].copy()
    assigned = df[df["workplace_id"].notna() & (df["workplace_id"] != "")].copy()

    print("\n==============================")
    print("TOTALS")
    print("==============================")
    print(f"Total agents:    {len(df):,}")
    print(f"Assigned:        {len(assigned):,}")
    print(f"Missing:         {len(missing):,}")
    print(f"Missing ratio:   {len(missing) / len(df):.4%}")

    print("\n==============================")
    print("TOP MISSING BY TARGET COUNTY × TEÁOR")
    print("==============================")

    by_target = (
        missing.groupby(["target_work_county", "teaor_code"], as_index=False)
        .size()
        .rename(columns={"size": "missing_agents"})
        .sort_values("missing_agents", ascending=False)
    )

    print(by_target.head(30).to_string(index=False))

    print("\n==============================")
    print("TOP MISSING BY RESIDENCE COUNTY × TEÁOR")
    print("==============================")

    by_residence = (
        missing.groupby(["county", "teaor_code"], as_index=False)
        .size()
        .rename(columns={"size": "missing_agents"})
        .sort_values("missing_agents", ascending=False)
    )

    print(by_residence.head(30).to_string(index=False))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    by_target.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print("\nSaved:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()