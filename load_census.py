from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd


# ============================================================
# ITT MÓDOSÍTSD, ha máshova rakod a fájlt
# ============================================================
INPUT_XLSX = Path("data/raw/ksh-census2022-WBS014-export.xlsx")
OUTPUT_DIR = Path("data/processed")


def read_raw_sheet(xlsx_path: Path) -> pd.DataFrame:
    """
    Beolvassa az Adattábla sheetet header nélkül.
    """
    df = pd.read_excel(xlsx_path, sheet_name="Adattábla", header=None)
    return df


def clean_wbs014(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    A KSH exportból tiszta, long-form DataFrame-et készít.

    Kimeneti oszlopok:
    - age_group
    - county
    - gender
    - occupation_group
    - count
    """
    # A táblában:
    # 0 = korcsoport
    # 1 = vármegye, régió
    # 2 = nem
    # 3..12 = foglalkozási főcsoportok
    #
    # Az első 3 sor meta/header jellegű:
    # row 0 -> cím
    # row 1 -> év (2022)
    # row 2 -> foglalkozási főcsoport fejlécek
    occupation_headers = df_raw.iloc[2, 3:].tolist()

    data = df_raw.iloc[3:, :].copy()
    data.columns = ["age_group", "county", "gender"] + occupation_headers

    # A KSH export hierarchikus, ezért forward fill kell
    data["age_group"] = data["age_group"].ffill()
    data["county"] = data["county"].ffill()

    # Szövegek tisztítása
    for col in ["age_group", "county", "gender"]:
        data[col] = data[col].astype(str).str.strip()

    # "nan" stringek vissza NaN-ra
    data = data.replace({"nan": np.nan, "NaN": np.nan})

    # Csak a tényleges sorok maradjanak
    data = data.dropna(subset=["gender"])

    # Long form
    long_df = data.melt(
        id_vars=["age_group", "county", "gender"],
        var_name="occupation_group",
        value_name="count"
    )

    # Számokra alakítás
    long_df["count"] = pd.to_numeric(long_df["count"], errors="coerce")

    # Hiányzó / nem numerikus értékek kezelése
    # Most 0-ra tesszük, mert a KSH exportban lehet üres cella
    long_df["count"] = long_df["count"].fillna(0).astype(int)

    # Felesleges whitespace-ek leszedése
    for col in ["age_group", "county", "gender", "occupation_group"]:
        long_df[col] = long_df[col].astype(str).str.strip()

    # Biztonsági szűrés
    long_df = long_df[
        (long_df["age_group"] != "")
        & (long_df["county"] != "")
        & (long_df["gender"] != "")
        & (long_df["occupation_group"] != "")
    ].reset_index(drop=True)

    return long_df


def build_dimension_vectors(long_df: pd.DataFrame) -> dict[str, list[str]]:
    """
    A dimenziók egyedi értékeit külön listákba gyűjti.
    """
    vectors = {
        "age_groups": sorted(long_df["age_group"].unique().tolist()),
        "counties": sorted(long_df["county"].unique().tolist()),
        "genders": sorted(long_df["gender"].unique().tolist()),
        "occupation_groups": long_df["occupation_group"].drop_duplicates().tolist(),
    }
    return vectors


def build_tensor(long_df: pd.DataFrame, vectors: dict[str, list[str]]) -> np.ndarray:
    """
    4D tensor:
    [age_group, county, gender, occupation_group] -> count
    """
    age_to_idx = {v: i for i, v in enumerate(vectors["age_groups"])}
    county_to_idx = {v: i for i, v in enumerate(vectors["counties"])}
    gender_to_idx = {v: i for i, v in enumerate(vectors["genders"])}
    occ_to_idx = {v: i for i, v in enumerate(vectors["occupation_groups"])}

    tensor = np.zeros(
        (
            len(vectors["age_groups"]),
            len(vectors["counties"]),
            len(vectors["genders"]),
            len(vectors["occupation_groups"]),
        ),
        dtype=np.int32,
    )

    for row in long_df.itertuples(index=False):
        a = age_to_idx[row.age_group]
        c = county_to_idx[row.county]
        g = gender_to_idx[row.gender]
        o = occ_to_idx[row.occupation_group]
        tensor[a, c, g, o] = row.count

    return tensor


def save_outputs(
    long_df: pd.DataFrame,
    vectors: dict[str, list[str]],
    tensor: np.ndarray,
    output_dir: Path,
) -> None:
    """
    Mentések:
    - CSV
    - JSON metadata
    - NPY tensor
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    long_df.to_csv(output_dir / "wbs014_long.csv", index=False, encoding="utf-8-sig")

    with open(output_dir / "wbs014_vectors.json", "w", encoding="utf-8") as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)

    np.save(output_dir / "wbs014_tensor.npy", tensor)

    # Opcionális: index map-ek külön is
    index_maps = {
        "age_group_to_idx": {v: i for i, v in enumerate(vectors["age_groups"])},
        "county_to_idx": {v: i for i, v in enumerate(vectors["counties"])},
        "gender_to_idx": {v: i for i, v in enumerate(vectors["genders"])},
        "occupation_group_to_idx": {
            v: i for i, v in enumerate(vectors["occupation_groups"])
        },
        "tensor_shape": list(tensor.shape),
    }

    with open(output_dir / "wbs014_index_maps.json", "w", encoding="utf-8") as f:
        json.dump(index_maps, f, ensure_ascii=False, indent=2)


def main() -> None:
    print(f"Reading: {INPUT_XLSX}")
    raw_df = read_raw_sheet(INPUT_XLSX)

    print("Cleaning table...")
    long_df = clean_wbs014(raw_df)

    print("Building vectors...")
    vectors = build_dimension_vectors(long_df)

    print("Building tensor...")
    tensor = build_tensor(long_df, vectors)

    print("Saving outputs...")
    save_outputs(long_df, vectors, tensor, OUTPUT_DIR)

    print("\nDone.")
    print(f"Rows in long table: {len(long_df)}")
    print(f"Tensor shape: {tensor.shape}")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()