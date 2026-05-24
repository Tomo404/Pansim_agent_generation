from __future__ import annotations

from pathlib import Path
import csv
import pandas as pd


# ============================================================
# ITT MÓDOSÍTSD, ha máshol vannak a fájlok
# ============================================================
INPUT_FILE = Path("data/processed/demographics_with_feor.csv")
OUTPUT_FILE = Path("data/processed/worker_slots.csv")


def main() -> None:
    print(f"Reading aggregated table: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, dtype={"feor_code": str}, encoding="utf-8-sig")

    required_cols = {
        "county",
        "teaor_code",
        "teaor_name",
        "gender",
        "age_group",
        "education",
        "feor_code",
        "count",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Hiányzó oszlop(ok): {missing}")

    total_slots = int(df["count"].sum())
    print(f"Total slots to generate: {total_slots:,}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing output: {OUTPUT_FILE}")

    slot_id = 1
    written = 0

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        # fejléc
        writer.writerow([
            "worker_slot_id",
            "county",
            "teaor_code",
            "teaor_name",
            "gender",
            "age_group",
            "education",
            "feor_code",
        ])

        for row in df.itertuples(index=False):
            n = int(row.count)

            for _ in range(n):
                writer.writerow([
                    slot_id,
                    row.county,
                    row.teaor_code,
                    row.teaor_name,
                    row.gender,
                    row.age_group,
                    row.education,
                    row.feor_code,
                ])
                slot_id += 1
                written += 1

                if written % 500_000 == 0:
                    print(f"Written: {written:,}")

    # Kis minta külön Excelbe, hogy könnyen meg lehessen nézni
    print("Saving sample Excel file...")
    sample_df = pd.read_csv(OUTPUT_FILE, nrows=10000, encoding="utf-8-sig")
    sample_df.to_excel("data/processed/worker_slots_sample.xlsx", index=False)

    print("\nDone.")
    print(f"Rows written: {written:,}")
    print(f"Last worker_slot_id: {slot_id - 1:,}")


if __name__ == "__main__":
    main()