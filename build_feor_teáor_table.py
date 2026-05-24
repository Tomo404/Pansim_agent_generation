from __future__ import annotations

from pathlib import Path
import pandas as pd

from feor_teaor_mapping import map_feor_to_teaor


# ============================================================
# ITT MÓDOSÍTSD, ha máshol vannak a fájlok
# ============================================================
INPUT_FEOR_FILE = Path("data/processed/feor_list_from_docx.csv")
OUTPUT_FILE = Path("feor_to_teaor_mapping.csv")


def mapping_to_columns(mapping: dict[str, float]) -> dict[str, float]:
    """
    pl.
    {"J": 0.85, "M": 0.15}
    ->
    {"teaor_J": 0.85, "teaor_M": 0.15}
    """
    row = {}
    for teaor_code, weight in mapping.items():
        row[f"teaor_{teaor_code}"] = weight
    return row


def main() -> None:
    print(f"Reading FEOR list: {INPUT_FEOR_FILE}")
    df = pd.read_csv(INPUT_FEOR_FILE, dtype={"feor_code": str})

    required_cols = {"feor_code", "feor_name"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Hiányzó oszlop(ok): {missing}")

    out_rows = []

    for row in df.itertuples(index=False):
        feor_code = str(row.feor_code).strip()
        feor_name = str(row.feor_name).strip()

        mapping = map_feor_to_teaor(feor_code, feor_name)

        out_row = {
            "feor_code": feor_code,
            "feor_name": feor_name,
        }
        out_row.update(mapping_to_columns(mapping))
        out_rows.append(out_row)

    out_df = pd.DataFrame(out_rows).fillna(0.0)

    # TEÁOR oszlopok sorrendbe rendezése
    teaor_cols = sorted([c for c in out_df.columns if c.startswith("teaor_")])
    out_df = out_df[["feor_code", "feor_name"] + teaor_cols]

    print(f"Saving mapping table: {OUTPUT_FILE}")
    out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print("Done.")
    print(f"Rows written: {len(out_df)}")
    print("\nSample rows:")
    print(out_df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()