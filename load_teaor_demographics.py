from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# ITT MÓDOSÍTSD, ha máshova rakod a fájlt
# ============================================================
INPUT_XLSX = Path("data/raw/hier_foglalkoztatott_nemzetgazdasagi_agazat.xlsx")
OUTPUT_DIR = Path("data/processed")

# ============================================================
# TEÁOR név-normalizálás
# A hosszú, pontosvesszős neveket egységes standard formára húzzuk.
# ============================================================
def normalize_teaor_name(raw_name: str) -> str:
    name = str(raw_name).strip()
    name = " ".join(name.split())  # többszörös whitespace-ek eltüntetése

    if name.startswith("Vízellátás"):
        return "Vízellátás; szennyvíz gyűjtése, kezelése, hulladékgazdálkodás, szennyeződésmentesítés"

    if name.startswith("Közigazgatás, védelem"):
        return "Közigazgatás, védelem; kötelező társadalombiztosítás"

    if name.startswith("Háztartás munkaadói tevékenysége"):
        return "Háztartás munkaadói tevékenysége; termék előállítása, szolgáltatás végzése saját fogyasztásra"

    return name

# ============================================================
# TEÁOR név -> betű megfeleltetés
# A "Területen kívüli szervezet" szándékosan nincs benne.
# ============================================================
TEAOR_NAME_TO_CODE = {
    "Mezőgazdaság, erdőgazdálkodás, halászat": "A",
    "Bányászat, kőfejtés": "B",
    "Feldolgozóipar": "C",
    "Villamosenergia-, gáz-, gőzellátás, légkondicionálás": "D",
    "Vízellátás; szennyvíz gyűjtése, kezelése, hulladékgazdálkodás, szennyeződésmentesítés": "E",
    "Építőipar": "F",
    "Kereskedelem, gépjárműjavítás": "G",
    "Szállítás, raktározás": "H",
    "Szálláshely-szolgáltatás, vendéglátás": "I",
    "Információ, kommunikáció": "J",
    "Pénzügyi, biztosítási tevékenység": "K",
    "Ingatlanügyletek": "L",
    "Szakmai, tudományos, műszaki tevékenység": "M",
    "Adminisztratív és szolgáltatást támogató tevékenység": "N",
    "Közigazgatás, védelem; kötelező társadalombiztosítás": "O",
    "Oktatás": "P",
    "Humán-egészségügyi, szociális ellátás": "Q",
    "Művészet, szórakoztatás, szabad idő": "R",
    "Egyéb szolgáltatás": "S",
    "Háztartás munkaadói tevékenysége; termék előállítása, szolgáltatás végzése saját fogyasztásra": "T",
}


def read_raw_sheet(xlsx_path: Path) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name="Adattábla", header=None)
    return df


def build_county_matrix(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    A 4 településtípus oszlopot összeadja vármegyei szintre.
    A county nevek a 0. sorban vannak minden 4. oszlop elején.
    """
    county_frames = []

    # A tényleges adat sorok a 2. sortól indulnak
    data_rows = df_raw.iloc[2:, :].copy()

    for col_start in range(4, df_raw.shape[1], 4):
        county_name = df_raw.iloc[0, col_start]

        if pd.isna(county_name):
            continue

        county_name = str(county_name).strip()

        cols = list(range(col_start, min(col_start + 4, df_raw.shape[1])))

        county_values = (
            data_rows[cols]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .sum(axis=1)
        )

        county_frames.append(
            pd.DataFrame({
                "county": county_name,
                "count": county_values.values
            })
        )

    county_df = pd.concat(county_frames, axis=0, ignore_index=True)
    return county_df


def build_metadata(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    A sorokhoz tartozó dimenziók:
    - gender
    - age_group
    - education
    - teaor_name
    """
    meta = df_raw.iloc[2:, 0:4].copy()
    meta.columns = ["gender", "age_group", "education", "teaor_name"]

    # Hierarchikus címkék kitöltése
    meta["gender"] = meta["gender"].ffill()
    meta["age_group"] = meta["age_group"].ffill()
    meta["education"] = meta["education"].ffill()

    # Sztring tisztítás
    for col in ["gender", "age_group", "education", "teaor_name"]:
        meta[col] = meta[col].astype(str).str.strip()
        meta[col] = meta[col].replace({"nan": np.nan, "NaN": np.nan})

    # teaor_name itt minden sorban van, de biztos ami biztos
    meta = meta.dropna(subset=["teaor_name"]).reset_index(drop=True)

    return meta


def clean_and_merge(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    A teljes táblából long-form DataFrame-et készít:
    county, gender, age_group, education, teaor_name, teaor_code, count
    """
    meta = build_metadata(df_raw)

    # Vármegyei összegzés
    county_frames = []

    data_rows = df_raw.iloc[2:, :].copy().reset_index(drop=True)

    for col_start in range(4, df_raw.shape[1], 4):
        county_name = df_raw.iloc[0, col_start]

        if pd.isna(county_name):
            continue

        county_name = str(county_name).strip()
        cols = list(range(col_start, min(col_start + 4, df_raw.shape[1])))

        county_values = (
            data_rows[cols]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .sum(axis=1)
            .reset_index(drop=True)
        )

        tmp = meta.copy()
        tmp["county"] = county_name
        tmp["count"] = county_values

        county_frames.append(tmp)

    long_df = pd.concat(county_frames, ignore_index=True)

    # TEÁOR név normalizálása
    long_df["teaor_name"] = long_df["teaor_name"].apply(normalize_teaor_name)

    # U sor eldobása
    long_df = long_df[long_df["teaor_name"] != "Területen kívüli szervezet"].copy()

    # TEÁOR betű hozzárendelése
    long_df["teaor_code"] = long_df["teaor_name"].map(TEAOR_NAME_TO_CODE)

    unmapped = long_df[long_df["teaor_code"].isna()]["teaor_name"].drop_duplicates().tolist()
    if unmapped:
        print("\nWARNING: unmapped TEÁOR names:")
        for x in unmapped:
            print(f"  - {x}")

    print("\nDEBUG normalized TEÁOR names:")
    for x in sorted(long_df["teaor_name"].drop_duplicates().tolist()):
        print(f"  - {x}")

    long_df = long_df.dropna(subset=["teaor_code"]).copy()

    # Count számmá alakítás
    long_df["count"] = pd.to_numeric(long_df["count"], errors="coerce").fillna(0).astype(int)

    # Most egyelőre a 0 sorokat eldobjuk, hogy kisebb legyen a tábla
    long_df = long_df[long_df["count"] > 0].reset_index(drop=True)

    return long_df


def save_outputs(long_df: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    long_df.to_csv(
        output_dir / "teaor_demographics_long.csv",
        index=False,
        encoding="utf-8-sig",
        sep="|"
    )

    long_df.to_excel(
        output_dir / "teaor_demographics_long.xlsx",
        index=False
    )

    summary = {
        "rows": int(len(long_df)),
        "total_count": int(long_df["count"].sum()),
        "counties": sorted(long_df["county"].drop_duplicates().tolist()),
        "genders": sorted(long_df["gender"].drop_duplicates().tolist()),
        "age_groups": sorted(long_df["age_group"].drop_duplicates().tolist()),
        "educations": sorted(long_df["education"].drop_duplicates().tolist()),
        "teaor_codes": sorted(long_df["teaor_code"].drop_duplicates().tolist()),
    }

    with open(output_dir / "teaor_demographics_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def main() -> None:
    print(f"Reading: {INPUT_XLSX}")
    raw_df = read_raw_sheet(INPUT_XLSX)

    print("Cleaning and reshaping...")
    long_df = clean_and_merge(raw_df)

    print("Saving outputs...")
    save_outputs(long_df, OUTPUT_DIR)

    print("\nDone.")
    print(f"Rows: {len(long_df)}")
    print(f"Total count: {long_df['count'].sum():,}")
    print(f"Counties: {long_df['county'].nunique()}")
    print(f"TEÁOR codes: {sorted(long_df['teaor_code'].unique().tolist())}")

    print("\nSample:")
    print(long_df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()