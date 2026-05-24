from __future__ import annotations

from pathlib import Path
import pandas as pd


# ============================================================
# ÁLLÍTSD BE
# ============================================================
FEOR_TEAOR_FILE = Path("feor_to_teaor_mapping.csv")
FEOR_SUM_FILE = Path("data/raw/feor_sum.xlsx")
OUTPUT_FILE = Path("data/processed/teaor_to_feor_distribution.csv")


def load_feor_prior(feor_sum_path: Path) -> dict[str, float]:
    """
    Beolvassa a KSH FEOR főcsoport adatokat,
    és visszaad egy prior eloszlást 1 jegyű FEOR-ra.
    """

    df_raw = pd.read_excel(feor_sum_path, header=None)

    # A tényleges adatsorok:
    # sor elején 2022. év / NaN
    # második oszlopban a FEOR főcsoport neve
    # harmadik oszlopban az érték (1000 fő)
    df = df_raw.iloc[6:15, [1, 2]].copy()
    df.columns = ["feor_group_label", "value"]

    df = df.dropna(subset=["feor_group_label", "value"]).reset_index(drop=True)

    # 1. / 2. / ... / 9. kinyerése
    df["feor_group"] = (
        df["feor_group_label"]
        .astype(str)
        .str.extract(r"^(\d)", expand=False)
    )

    # 1000 fő -> fő
    df["value"] = pd.to_numeric(df["value"], errors="coerce") * 1000

    df = df.dropna(subset=["feor_group", "value"]).reset_index(drop=True)

    total = df["value"].sum()

    prior = {
        row.feor_group: row.value / total
        for row in df.itertuples(index=False)
    }

    print("FEOR prior (1-digit):")
    for k, v in prior.items():
        print(f"{k}: {v:.3f}")

    print("\nDEBUG FEOR GROUPS:")
    print(df[["feor_group", "feor_group_label", "value"]].to_string(index=False))

    return prior


def main() -> None:
    print("Loading FEOR→TEÁOR mapping...")
    df = pd.read_csv(FEOR_TEAOR_FILE, dtype={"feor_code": str})

    print("Loading FEOR prior...")
    feor_prior = load_feor_prior(FEOR_SUM_FILE)

    teaor_cols = [c for c in df.columns if c.startswith("teaor_")]
    teaor_codes = [c.replace("teaor_", "") for c in teaor_cols]

    print(f"TEÁOR categories: {teaor_codes}")

    rows = []

    # ============================================================
    # TEÁOR → FEOR számítás
    # ============================================================
    for teaor_col, teaor_code in zip(teaor_cols, teaor_codes):

        weights = []

        for row in df.itertuples(index=False):
            feor_code = row.feor_code
            feor_group = feor_code[0]

            prior = feor_prior.get(feor_group, 0.0)
            mapping_weight = getattr(row, teaor_col)

            score = prior * mapping_weight

            weights.append({
                "feor_code": feor_code,
                "score": score
            })

        tmp = pd.DataFrame(weights)

        total = tmp["score"].sum()

        if total == 0:
            continue

        tmp["prob"] = tmp["score"] / total
        tmp["teaor"] = teaor_code

        rows.append(tmp[["teaor", "feor_code", "prob"]])

    out_df = pd.concat(rows, ignore_index=True)

    print(f"Saving: {OUTPUT_FILE}")
    out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print("Done.")
    print("\nSample:")
    print(out_df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()