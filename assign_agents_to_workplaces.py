from __future__ import annotations

from pathlib import Path
import csv
import unicodedata
import random
import numpy as np
import pandas as pd

# ============================================================
# INPUT / OUTPUT
# ============================================================
AGENTS_FILE = Path("data/processed/agents.csv")
COMPANIES_FILE = Path("data/raw/generated_companies_calibrated.csv")
SETTLEMENT_COUNTY_FILE = Path("data/raw/telepules_hierarchia.xlsx")
COMMUTING_MATRIX_FILE = Path("data/processed/commuting_matrix.csv")
OUTPUT_FILE = Path("data/processed/agents_with_workplaces.csv")


# ============================================================
# SEGÉDFÜGGVÉNYEK
# ============================================================
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
    if pd.isna(value):
        return None

    try:
        code = int(value)
    except ValueError:
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

def build_commuting_probabilities():
    print(f"Reading commuting matrix: {COMMUTING_MATRIX_FILE}")

    df = pd.read_csv(COMMUTING_MATRIX_FILE, encoding="utf-8-sig")

    probs = {}

    for residence_county, group in df.groupby("residence_county"):

        workplace_counties = group["workplace_county"].tolist()
        counts = group["count"].tolist()

        total = sum(counts)

        weights = [c / total for c in counts]

        probs[residence_county] = (
            workplace_counties,
            weights
        )

    print(f"Built commuting probabilities for {len(probs)} counties.")

    return probs


def sample_work_county(residence_county, commute_probs):
    if residence_county not in commute_probs:
        return residence_county

    counties, weights = commute_probs[residence_county]

    return random.choices(
        counties,
        weights=weights,
        k=1
    )[0]

def take_slot_from_pool(
    key: tuple[str, str],
    pools: dict,
    pool_positions: dict,
) -> dict | None:
    slots = pools.get(key)
    pos = pool_positions.get(key, 0)

    if slots is None or pos >= len(slots):
        return None

    slot = slots[pos]
    pool_positions[key] = pos + 1
    return slot


def assign_slot_with_fallback(
    residence_county: str,
    initial_work_county: str,
    agent_teaor_code: str,
    commute_probs: dict,
    pools: dict,
    pool_positions: dict,
) -> tuple[dict | None, str | None, bool, str, bool]:
    """
    Visszatér:
    slot,
    final_work_county,
    used_fallback,
    fallback_level,
    used_teaor_fallback

    Sorrend:
    1) initial commuting target + azonos TEÁOR
    2) commuting matrix szerinti további megyék + azonos TEÁOR
    3) commuting matrix szerinti megyék + bármely TEÁOR
    4) országos fallback + azonos TEÁOR
    5) nincs találat
    """

    # 1) Elsődleges commuting célmegye + azonos TEÁOR
    key = (initial_work_county, agent_teaor_code)
    slot = take_slot_from_pool(key, pools, pool_positions)
    if slot is not None:
        return slot, initial_work_county, False, "1_initial_county_same_teaor", False

    # Commuting sorrend residence county alapján
    ranked_commute_counties = []

    if residence_county in commute_probs:
        counties, weights = commute_probs[residence_county]
        ranked_commute_counties = [
            county for county, _weight in sorted(
                zip(counties, weights),
                key=lambda x: x[1],
                reverse=True,
            )
        ]

    # Biztonság: initial legyen benne, de ne duplikáljuk
    ordered_counties = []
    for c in [initial_work_county] + ranked_commute_counties:
        if c not in ordered_counties:
            ordered_counties.append(c)

    # 2) Commuting megyék + azonos TEÁOR
    for county in ordered_counties:
        key = (county, agent_teaor_code)
        slot = take_slot_from_pool(key, pools, pool_positions)
        if slot is not None:
            return slot, county, True, "2_commuting_county_same_teaor", False

    # 3) Commuting megyék + bármely TEÁOR
    for county in ordered_counties:
        # az adott megyében bármely TEÁOR, ahol van még slot
        candidate_keys = [
            key for key, slots in pools.items()
            if key[0] == county and pool_positions.get(key, 0) < len(slots)
        ]

        if not candidate_keys:
            continue

        # Preferáljuk a nagyobb maradék kapacitású poolokat
        candidate_keys.sort(
            key=lambda k: len(pools[k]) - pool_positions.get(k, 0),
            reverse=True,
        )

        slot = take_slot_from_pool(candidate_keys[0], pools, pool_positions)
        if slot is not None:
            return slot, county, True, "3_commuting_county_any_teaor", True

    # 4) Országos fallback + azonos TEÁOR
    candidate_keys = [
        key for key, slots in pools.items()
        if key[1] == agent_teaor_code and pool_positions.get(key, 0) < len(slots)
    ]

    if candidate_keys:
        candidate_keys.sort(
            key=lambda k: len(pools[k]) - pool_positions.get(k, 0),
            reverse=True,
        )

        best_key = candidate_keys[0]
        slot = take_slot_from_pool(best_key, pools, pool_positions)
        if slot is not None:
            return slot, best_key[0], True, "4_global_same_teaor", False

    return None, None, True, "5_missing", False

def get_fallback_county_for_teaor(
    residence_county: str,
    teaor_code: str,
    commute_probs: dict,
    pools: dict,
    pool_positions: dict,
) -> str | None:
    """
    Ha a kisorsolt target county-ben nincs szabad slot az adott TEÁOR-ra,
    akkor keresünk másik megyét, ahol még van kapacitás.

    Sorrend:
    1) commuting mátrix szerinti célmegyék nagyobb valószínűségtől kisebb felé
    2) országos fallback: bármely county, ahol van szabad TEÁOR slot
    """

    # 1) Commuting alapú fallback sorrend
    if residence_county in commute_probs:
        counties, weights = commute_probs[residence_county]

        ranked = sorted(
            zip(counties, weights),
            key=lambda x: x[1],
            reverse=True,
        )

        for county, _weight in ranked:
            key = (county, teaor_code)
            slots = pools.get(key)
            pos = pool_positions.get(key, 0)

            if slots is not None and pos < len(slots):
                return county

    # 2) Országos fallback ugyanarra a TEÁOR-ra
    for key, slots in pools.items():
        county, pool_teaor = key

        if pool_teaor != teaor_code:
            continue

        pos = pool_positions.get(key, 0)

        if pos < len(slots):
            return county

    # 3) Sehol nincs ilyen TEÁOR kapacitás
    return None

# ============================================================
# COMPANY POOL ÉPÍTÉS
# ============================================================
def load_companies_with_county() -> pd.DataFrame:
    print(f"Reading companies: {COMPANIES_FILE}")
    companies = pd.read_csv(COMPANIES_FILE, encoding="utf-8-sig")

    required = {"settlement", "teaor", "company_size"}
    missing = required - set(companies.columns)
    if missing:
        raise ValueError(f"Hiányzó oszlop(ok) a céges fájlban: {missing}")

    companies["company_size"] = pd.to_numeric(
        companies["company_size"],
        errors="coerce"
    ).fillna(0).astype(int)

    companies = companies[companies["company_size"] > 0].copy()

    print(f"Reading settlement hierarchy: {SETTLEMENT_COUNTY_FILE}")
    mapping = pd.read_excel(SETTLEMENT_COUNTY_FILE)

    required_mapping = {
        "Helység megnevezése",
        "Vármegye megnevezése",
        "Településtípus",
    }
    missing_mapping = required_mapping - set(mapping.columns)
    if missing_mapping:
        raise ValueError(f"Hiányzó oszlop(ok) a településhierarchia fájlban: {missing_mapping}")

    companies["settlement_norm"] = companies["settlement"].apply(normalize_name)

    # Budapest kerületek explicit kezelése
    companies["county"] = None
    companies["settlement_pretty"] = companies["settlement"].astype(str).str.strip()
    companies["settlement_type"] = None

    is_budapest = companies["settlement_norm"].str.startswith("budapest")

    companies.loc[is_budapest, "county"] = "Budapest"

    # A céges fájlban sokszor így szerepel: budapest 13 kerulet
    # Ezt emberileg olvashatóbb formára hozzuk:
    companies.loc[is_budapest, "settlement_pretty"] = (
        companies.loc[is_budapest, "settlement_norm"]
        .str.replace("budapest ", "Budapest ", regex=False)
        .str.replace(" kerulet", ". kerület", regex=False)
    )

    companies.loc[is_budapest, "settlement_type"] = "Főváros"

    # Településhierarchia mapping
    mapping["settlement_norm"] = mapping["Helység megnevezése"].apply(normalize_name)
    mapping["county_mapped"] = mapping["Vármegye megnevezése"].apply(normalize_county)
    mapping["settlement_pretty_mapped"] = mapping["Helység megnevezése"].astype(str).str.strip()
    mapping["settlement_type_mapped"] = mapping["Településtípus"].astype(str).str.strip()

    mapping = mapping[
        [
            "settlement_norm",
            "county_mapped",
            "settlement_pretty_mapped",
            "settlement_type_mapped",
        ]
    ].drop_duplicates()

    companies = companies.merge(
        mapping,
        on="settlement_norm",
        how="left"
    )

    companies["county"] = companies["county"].fillna(companies["county_mapped"])
    companies["settlement_pretty"] = companies["settlement_pretty_mapped"].fillna(companies["settlement_pretty"])
    companies["settlement_type"] = companies["settlement_type"].fillna(companies["settlement_type_mapped"])

    companies = companies.drop(
        columns=[
            "county_mapped",
            "settlement_pretty_mapped",
            "settlement_type_mapped",
        ]
    )

    missing_county = companies["county"].isna().sum()
    if missing_county > 0:
        missing_workers = companies.loc[companies["county"].isna(), "company_size"].sum()
        print(f"WARNING: {missing_county:,} company rows without county ({missing_workers:,} workers). These will be ignored.")

    missing_type = companies["settlement_type"].isna().sum()
    if missing_type > 0:
        print(f"WARNING: {missing_type:,} company rows without settlement_type.")

    companies["teaor_code"] = companies["teaor"].apply(teaor_numeric_to_section)

    missing_teaor = companies["teaor_code"].isna().sum()
    if missing_teaor > 0:
        print(f"WARNING: {missing_teaor:,} company rows without TEÁOR section. These will be ignored.")

    companies = companies.dropna(subset=["county", "teaor_code"]).copy()

    companies = companies.reset_index(drop=True)
    companies["workplace_id"] = ["WP_" + str(i + 1).zfill(9) for i in range(len(companies))]

    return companies


def build_assignment_pools(companies: pd.DataFrame) -> dict[tuple[str, str], list[dict]]:
    """
    Minden (county, teaor_code) kombinációhoz felépítünk egy workplace-slot listát.
    Ha egy cég company_size=5, akkor 5 slot kerül a listába ugyanazzal a workplace_id-val.

    Ez memóriaigényesebb, de 4.6M slotnál még általában kezelhető.
    """
    pools: dict[tuple[str, str], list[dict]] = {}

    print("Building workplace slot pools...")

    for row in companies.itertuples(index=False):
        key = (row.county, row.teaor_code)

        slot_info = {
            "workplace_id": row.workplace_id,
            "workplace_county": row.county,
            "workplace_teaor_code": row.teaor_code,
            "workplace_settlement": row.settlement_pretty,
            "workplace_settlement_type": row.settlement_type,
            "workplace_size": row.company_size,
        }

        if key not in pools:
            pools[key] = []

        pools[key].extend([slot_info] * int(row.company_size))

    # shuffle, hogy ne mindig ugyanazok a cégek töltsék be először
    rng = np.random.default_rng(42)
    for key, slots in pools.items():
        rng.shuffle(slots)

    print(f"Built pools for {len(pools)} county×TEÁOR combinations.")
    return pools


# ============================================================
# ASSIGNMENT
# ============================================================
def assign_agents_to_workplaces() -> None:
    companies = load_companies_with_county()
    pools = build_assignment_pools(companies)
    commute_probs = build_commuting_probabilities()
    # workplace kapacitás megye szerint
    county_capacity = {}

    for (county, teaor), slots in pools.items():
        county_capacity[county] = county_capacity.get(county, 0) + len(slots)

    total_capacity = sum(county_capacity.values())

    # normalizált súlyok
    county_weights = {
        c: county_capacity[c] / total_capacity
        for c in county_capacity
    }

    pool_positions = {key: 0 for key in pools.keys()}

    print(f"Reading agents and writing output: {OUTPUT_FILE}")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    total_written = 0
    missing_assignment = 0

    with open(AGENTS_FILE, "r", encoding="utf-8-sig", newline="") as fin, \
            open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as fout:

        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames or []

        new_fields = [
            "target_work_county",
            "final_work_county",
            "used_fallback",
            "fallback_level",
            "used_teaor_fallback",
            "workplace_id",
            "workplace_county",
            "workplace_teaor_code",
            "workplace_settlement",
            "workplace_settlement_type",
            "workplace_size",
        ]

        writer = csv.DictWriter(fout, fieldnames=fieldnames + new_fields)
        writer.writeheader()

        for row in reader:
            county = normalize_county(row["county"])
            teaor_code = row["teaor_code"]

            # 🔥 ÚJ: commuting alapú county választás
            initial_work_county = sample_work_county(
                county,
                commute_probs
            )

            slot, final_work_county, used_fallback, fallback_level, used_teaor_fallback = assign_slot_with_fallback(
                residence_county=county,
                initial_work_county=initial_work_county,
                agent_teaor_code=teaor_code,
                commute_probs=commute_probs,
                pools=pools,
                pool_positions=pool_positions,
            )

            if slot is None:
                row.update({
                    "target_work_county": initial_work_county,
                    "final_work_county": "",
                    "used_fallback": used_fallback,
                    "fallback_level": fallback_level,
                    "used_teaor_fallback": used_teaor_fallback,
                    "workplace_id": "",
                    "workplace_county": "",
                    "workplace_teaor_code": "",
                    "workplace_settlement": "",
                    "workplace_settlement_type": "",
                    "workplace_size": "",
                })
                missing_assignment += 1
            else:
                row["target_work_county"] = initial_work_county
                row["final_work_county"] = final_work_county
                row["used_fallback"] = used_fallback
                row["fallback_level"] = fallback_level
                row["used_teaor_fallback"] = used_teaor_fallback
                row.update(slot)

            writer.writerow(row)
            total_written += 1

            if total_written % 500_000 == 0:
                print(f"Written: {total_written:,}")

    print("\nDone.")
    print(f"Agents written: {total_written:,}")
    print(f"Missing workplace assignment: {missing_assignment:,}")
    print(f"Missing ratio: {missing_assignment / total_written:.4%}")


def main() -> None:
    assign_agents_to_workplaces()


if __name__ == "__main__":
    main()