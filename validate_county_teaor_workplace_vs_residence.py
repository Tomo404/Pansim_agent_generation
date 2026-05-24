from __future__ import annotations

from pathlib import Path
import unicodedata
import pandas as pd


# ============================================================
# INPUTOK
# ============================================================
RESIDENCE_WORKER_SLOTS = Path("data/processed/worker_slots.csv")
WORKPLACE_COMPANIES = Path("data/raw/generated_companies_calibrated.csv")

# Csak akkor kell, ha a generated_companies_calibrated.csv-ben nincs county oszlop.
# Elvárt oszlopok: settlement_norm, county
SETTLEMENT_TO_COUNTY = Path("data/raw/settlement_distribution_summary.xlsx")

OUTPUT_DIR = Path("data/validation")


def normalize_name(name: str) -> str:
    if pd.isna(name):
        return ""

    name = str(name).lower().strip()
    name = "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    )
    return name

def normalize_county(county: str) -> str:
    """
    County név egységesítése:
    - fováros / főváros -> Budapest
    - Pest -> Pest vármegye
    - Baranya -> Baranya vármegye
    """
    if pd.isna(county):
        return ""

    raw = str(county).strip()
    norm = normalize_name(raw)

    if norm in {"fovaros", "fováros", "budapest"}:
        return "Budapest"

    county_map = {
        "baranya": "Baranya vármegye",
        "bacs-kiskun": "Bács-Kiskun vármegye",
        "bekes": "Békés vármegye",
        "borsod-abauj-zemplen": "Borsod-Abaúj-Zemplén vármegye",
        "csongrad-csanad": "Csongrád-Csanád vármegye",
        "fejer": "Fejér vármegye",
        "gyor-moson-sopron": "Győr-Moson-Sopron vármegye",
        "hajdu-bihar": "Hajdú-Bihar vármegye",
        "heves": "Heves vármegye",
        "jasz-nagykun-szolnok": "Jász-Nagykun-Szolnok vármegye",
        "komarom-esztergom": "Komárom-Esztergom vármegye",
        "nograd": "Nógrád vármegye",
        "pest": "Pest vármegye",
        "somogy": "Somogy vármegye",
        "szabolcs-szatmar-bereg": "Szabolcs-Szatmár-Bereg vármegye",
        "tolna": "Tolna vármegye",
        "vas": "Vas vármegye",
        "veszprem": "Veszprém vármegye",
        "zala": "Zala vármegye",
    }

    return county_map.get(norm, raw)

def teaor_numeric_to_section(value) -> str | None:
    """
    TEÁOR kétjegyű/numerikus alágazati kód -> fő TEÁOR betű.
    Pl. 1/01 -> A, 10 -> C, 62 -> J.
    """
    if pd.isna(value):
        return None

    try:
        code = int(value)
    except ValueError:
        # ha már betű lenne
        text = str(value).strip().upper()
        if len(text) == 1 and text.isalpha():
            return text
        return None

    if 1 <= code <= 3:
        return "A"
    if 5 <= code <= 9:
        return "B"
    if 10 <= code <= 33:
        return "C"
    if code == 35:
        return "D"
    if 36 <= code <= 39:
        return "E"
    if 41 <= code <= 43:
        return "F"
    if 45 <= code <= 47:
        return "G"
    if 49 <= code <= 53:
        return "H"
    if 55 <= code <= 56:
        return "I"
    if 58 <= code <= 63:
        return "J"
    if 64 <= code <= 66:
        return "K"
    if code == 68:
        return "L"
    if 69 <= code <= 75:
        return "M"
    if 77 <= code <= 82:
        return "N"
    if code == 84:
        return "O"
    if code == 85:
        return "P"
    if 86 <= code <= 88:
        return "Q"
    if 90 <= code <= 93:
        return "R"
    if 94 <= code <= 96:
        return "S"
    if 97 <= code <= 98:
        return "T"
    if code == 99:
        return "U"

    return None

def load_residence_county_teaor() -> pd.DataFrame:
    """
    worker_slots.csv:
    county + teaor_code szerint összesít.
    Ez a lakhely/census irányú eloszlás.
    """
    print("Loading residence-side worker slots...")

    df = pd.read_csv(
        RESIDENCE_WORKER_SLOTS,
        usecols=["county", "teaor_code"],
        encoding="utf-8-sig",
    )
    df["county"] = df["county"].apply(normalize_county)

    out = (
        df.groupby(["county", "teaor_code"], as_index=False)
        .size()
        .rename(columns={"size": "residence_workers"})
    )

    return out


def load_workplace_county_teaor() -> pd.DataFrame:
    """
    generated_companies_calibrated.csv:
    county + teaor szerint összesít.
    Ez a munkahely/cégközpont irányú eloszlás.
    """
    print("Loading workplace-side generated companies...")

    df = pd.read_csv(WORKPLACE_COMPANIES, encoding="utf-8-sig")

    print("Columns in workplace file:")
    print(df.columns.tolist())

    SETTLEMENT_COL = "settlement"
    TEAOR_COL = "teaor"
    WORKERS_COL = "company_size"

    for col in [SETTLEMENT_COL, TEAOR_COL, WORKERS_COL]:
        if col not in df.columns:
            raise ValueError(f"Hiányzó oszlop a céges fájlban: {col}")

    df[WORKERS_COL] = pd.to_numeric(df[WORKERS_COL], errors="coerce").fillna(0)

    # ------------------------------------------------------------
    # COUNTY HOZZÁRENDELÉS
    # ------------------------------------------------------------
    if "county" in df.columns:
        print("Found county column in workplace file.")
        df["county"] = df["county"].apply(normalize_county)

    else:
        print("No county column found in workplace file.")
        print(f"Loading settlement→county mapping: {SETTLEMENT_TO_COUNTY}")

        if SETTLEMENT_TO_COUNTY.suffix.lower() in [".xlsx", ".xls"]:
            mapping = pd.read_excel(SETTLEMENT_TO_COUNTY)
        else:
            mapping = pd.read_csv(SETTLEMENT_TO_COUNTY, encoding="utf-8-sig")

        print("Columns in mapping file:")
        print(mapping.columns.tolist())

        required = {"settlement", "county"}
        missing = required - set(mapping.columns)
        if missing:
            raise ValueError(f"A mapping fájlból hiányzik: {missing}")

        df["settlement_norm"] = df[SETTLEMENT_COL].apply(normalize_name)
        # Budapest kerületek explicit kezelése
        df.loc[
            df["settlement_norm"].str.startswith("budapest"),
            "county"
        ] = "Budapest"

        mapping["settlement_norm"] = mapping["settlement"].apply(normalize_name)
        mapping["county"] = mapping["county"].apply(normalize_county)

        mapping = mapping[["settlement_norm", "county"]].drop_duplicates()

        df = df.merge(
            mapping,
            on="settlement_norm",
            how="left",
            suffixes=("", "_mapped"),
        )

        # Ha már explicit beállítottuk Budapestet, azt tartsuk meg.
        # Egyébként használjuk a mappingből jövő county-t.
        if "county_mapped" in df.columns:
            df["county"] = df["county"].fillna(df["county_mapped"])
            df = df.drop(columns=["county_mapped"])

        missing_county = df["county"].isna().sum()
        if missing_county > 0:
            missing_workers = df.loc[df["county"].isna(), WORKERS_COL].sum()
            print(f"WARNING: {missing_county:,} company rows did not get a county.")
            print(f"WARNING: these unmatched rows contain {missing_workers:,.0f} workers.")

            print("\nTop unmatched settlements by worker count:")
            unmatched = (
                df.loc[df["county"].isna()]
                .groupby(SETTLEMENT_COL, as_index=False)[WORKERS_COL]
                .sum()
                .sort_values(WORKERS_COL, ascending=False)
                .head(30)
            )
            print(unmatched.to_string(index=False))

    # ------------------------------------------------------------
    # TEÁOR NUMERIKUS KÓD → TEÁOR BETŰ
    # ------------------------------------------------------------
    df["teaor_code"] = df[TEAOR_COL].apply(teaor_numeric_to_section)

    unmapped_teaor = df["teaor_code"].isna().sum()
    if unmapped_teaor > 0:
        print(f"WARNING: {unmapped_teaor:,} company rows did not get a TEÁOR section code.")
        print("Unmapped TEÁOR examples:")
        print(
            df.loc[df["teaor_code"].isna(), TEAOR_COL]
            .drop_duplicates()
            .head(20)
            .to_string(index=False)
        )

    # ------------------------------------------------------------
    # ÖSSZESÍTÉS
    # ------------------------------------------------------------
    out = (
        df.dropna(subset=["county", "teaor_code"])
        .groupby(["county", "teaor_code"], as_index=False)[WORKERS_COL]
        .sum()
        .rename(columns={WORKERS_COL: "workplace_workers"})
    )

    out["workplace_workers"] = out["workplace_workers"].round().astype(int)

    return out

def compare(residence: pd.DataFrame, workplace: pd.DataFrame) -> pd.DataFrame:
    merged = residence.merge(
        workplace,
        on=["county", "teaor_code"],
        how="outer",
    )

    merged["residence_workers"] = merged["residence_workers"].fillna(0).astype(int)
    merged["workplace_workers"] = merged["workplace_workers"].fillna(0).astype(int)

    merged["diff_workplace_minus_residence"] = (
        merged["workplace_workers"] - merged["residence_workers"]
    )

    merged["relative_diff"] = merged.apply(
        lambda r: r["diff_workplace_minus_residence"] / r["residence_workers"]
        if r["residence_workers"] > 0 else None,
        axis=1,
    )

    return merged


def save_outputs(comparison: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    detail_path = OUTPUT_DIR / "county_teaor_workplace_vs_residence.csv"
    comparison.to_csv(detail_path, index=False, encoding="utf-8-sig")

    county_summary = (
        comparison.groupby("county", as_index=False)[
            ["residence_workers", "workplace_workers", "diff_workplace_minus_residence"]
        ]
        .sum()
    )

    county_summary["relative_diff"] = county_summary.apply(
        lambda r: r["diff_workplace_minus_residence"] / r["residence_workers"]
        if r["residence_workers"] > 0 else None,
        axis=1,
    )

    county_path = OUTPUT_DIR / "county_workplace_vs_residence_summary.csv"
    county_summary.to_csv(county_path, index=False, encoding="utf-8-sig")

    teaor_summary = (
        comparison.groupby("teaor_code", as_index=False)[
            ["residence_workers", "workplace_workers", "diff_workplace_minus_residence"]
        ]
        .sum()
    )

    teaor_summary["relative_diff"] = teaor_summary.apply(
        lambda r: r["diff_workplace_minus_residence"] / r["residence_workers"]
        if r["residence_workers"] > 0 else None,
        axis=1,
    )

    teaor_path = OUTPUT_DIR / "teaor_workplace_vs_residence_summary.csv"
    teaor_summary.to_csv(teaor_path, index=False, encoding="utf-8-sig")

    print(f"\nSaved detail: {detail_path}")
    print(f"Saved county summary: {county_path}")
    print(f"Saved TEÁOR summary: {teaor_path}")


def main() -> None:
    residence = load_residence_county_teaor()
    workplace = load_workplace_county_teaor()

    print("\n==============================")
    print("TOTALS")
    print("==============================")
    print(f"Residence/census-side total: {residence['residence_workers'].sum():,}")
    print(f"Workplace/company-side total: {workplace['workplace_workers'].sum():,}")

    comparison = compare(residence, workplace)

    print("\n==============================")
    print("TOP COUNTY DIFFERENCES")
    print("==============================")
    county_summary = (
        comparison.groupby("county", as_index=False)[
            ["residence_workers", "workplace_workers", "diff_workplace_minus_residence"]
        ]
        .sum()
    )

    county_summary["abs_diff"] = county_summary["diff_workplace_minus_residence"].abs()

    print(
        county_summary.sort_values("abs_diff", ascending=False)
        .head(20)
        .to_string(index=False)
    )

    print("\n==============================")
    print("TOP COUNTY × TEÁOR DIFFERENCES")
    print("==============================")
    tmp = comparison.copy()
    tmp["abs_diff"] = tmp["diff_workplace_minus_residence"].abs()

    print(
        tmp.sort_values("abs_diff", ascending=False)
        .head(30)[
            [
                "county",
                "teaor_code",
                "residence_workers",
                "workplace_workers",
                "diff_workplace_minus_residence",
                "relative_diff",
            ]
        ]
        .to_string(index=False)
    )

    save_outputs(comparison)

    print("\nDone.")


if __name__ == "__main__":
    main()