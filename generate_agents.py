from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np
import csv

# ============================================================
# INPUT / OUTPUT
# ============================================================

INPUT_FILE = Path("data/processed/demographics_with_feor.csv")
OUTPUT_FILE = Path("data/processed/agents.csv")

# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print(f"Reading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")

    total_slots = int(df["count"].sum())
    print(f"Total agents to generate: {total_slots:,}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing: {OUTPUT_FILE}")

    chunk_size = 100_000
    current_id = 1
    buffer = []

    with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "agent_id",
            "county",
            "teaor_code",
            "feor_code",
            "gender",
            "age_group",
            "education",
        ])

        for i, row in df.iterrows():
            count = int(row["count"])

            for _ in range(count):

                writer.writerow([
                    current_id,
                    row["county"],
                    row["teaor_code"],
                    row["feor_code"],
                    row["gender"],
                    row["age_group"],
                    row["education"],
                ])

                current_id += 1

            if i % 10000 == 0:
                print(f"Processed rows: {i}")

        # maradék
        if buffer:
            for b in buffer:
                f.write(",".join(map(str, b)) + "\n")

    print("\nDone.")
    print(f"Total generated: {current_id - 1:,}")


if __name__ == "__main__":
    main()