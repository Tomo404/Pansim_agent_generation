import pandas as pd
import unicodedata
from pathlib import Path


# ============================================================
# EZT ÁLLÍTSD BE
# ============================================================
INPUT_CSV = Path("data/raw/generated_companies_calibrated.csv")
OUTPUT_CSV = Path("data/processed/settlement_distribution_final.csv")


# ------------------------------------------------------------
# TELEPÜLÉS NORMALIZÁLÁS
# ------------------------------------------------------------
def normalize_name(name: str) -> str:
    """
    pl:
    Pécs -> pecs
    Üröm -> urom
    """
    if pd.isna(name):
        return ""

    name = str(name).lower().strip()

    # ékezetek eltávolítása
    name = "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    )

    return name


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    print("Loading generated companies...")
    df = pd.read_csv(INPUT_CSV)

    # ⚠️ FONTOS: ezt lehet, hogy át kell írnod
    # attól függően, hogy nálad mi a column neve
    # pl: "settlement", "city", stb
    SETTLEMENT_COL = "settlement"
    WORKERS_COL = "company_size"

    print("Normalizing settlement names...")
    df["settlement_norm"] = df[SETTLEMENT_COL].apply(normalize_name)

    print("Aggregating workers per settlement...")
    summary = (
        df.groupby("settlement_norm")[WORKERS_COL]
        .sum()
        .reset_index()
        .rename(columns={WORKERS_COL: "total_workers"})
    )

    total = summary["total_workers"].sum()

    print(f"\nTotal workers: {total:,}")

    # sanity check
    if total < 4_300_000:
        print("⚠️ WARNING: túl alacsony! Valószínűleg nem calibrated adat.")
    elif total > 5_000_000:
        print("⚠️ WARNING: túl magas! Valami duplikáció lehet.")

    print("\nSaving...")
    summary.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"Saved to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()