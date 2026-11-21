
from pathlib import Path
from collections import Counter, defaultdict
import csv
import re
import unicodedata
import pandas as pd


# ============================================================
# WORKPLACE CAPACITY V2
# A későbbi új munkahelykiosztás előkészítése.
# CSAK ELLENŐRZÉS - nem módosít ágens- vagy munkahelyfájlokat.
# ============================================================

ROOT = Path(__file__).resolve().parent

COMPANIES_CSV = (
    ROOT / "data/raw/generated_companies_calibrated.csv"
)

HIERARCHY_XLSX = (
    ROOT / "data/raw/telepules_hierarchia.xlsx"
)

COMMUTING_DETAIL_CSV = (
    ROOT / "data/processed/commuting_v2/"
           "02_kategoria_es_telepulestipus_v2.csv"
)

COMMUTING_COUNTY_CSV = (
    ROOT / "data/processed/commuting_v2/"
           "06_varmegyei_merleg_v2.csv"
)

RESIDENTS_CSV = (
    ROOT / "data/processed/"
           "01_settlement_residents_commuting_29d.csv"
)

OUTPUT_FOLDER = (
    ROOT / "data/processed/workplace_capacity_v2"
)

HOME = "Lakóhelyén foglalkoztatott"
LOCAL = "Lakóhely településén foglalkoztatott"
COMMUTE = "Más magyarországi településen foglalkoztatott"
VARIABLE = "Változó településen foglalkoztatott"

CATEGORIES = (HOME, LOCAL, COMMUTE, VARIABLE)

EXPECTED_DOMESTIC_WORKERS = 4_596_079
EXPECTED_KSH_AREAS = 3_177


# ============================================================
# 1. NORMALIZÁLÁS
# ============================================================

def clean(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize(value):
    text = unicodedata.normalize(
        "NFC", clean(value)
    ).casefold()

    text = re.sub(
        r"[^\w\s-]", " ", text,
        flags=re.UNICODE
    )

    return re.sub(r"\s+", " ", text).strip()


def city_key(value):
    text = normalize(value)

    # Budapest 23 kerülete települési szinten
    # egyetlen Budapestként szerepel.
    if text.startswith("budapest"):
        return "budapest"

    corrections = {
        "kömlo": "kömlő",
        "kömöro": "kömörő",
        "kömlod": "kömlőd",
    }

    return corrections.get(text, text)


def ascii_key(value):
    text = unicodedata.normalize("NFD", value)

    return "".join(
        char for char in text
        if not unicodedata.combining(char)
    )


def county_key(value):
    text = ascii_key(normalize(value))

    text = re.sub(
        r"\s+(varmegye|megye)$",
        "",
        text
    )

    # Budapest es a fovaros minden ismert elnevezese
    if text in {
        "budapest",
        "fovaros",
        "budapest fovaros",
    }:
        return "budapest"

    return text



def type_key(value):
    text = ascii_key(normalize(value))

    if text in {
        "fovaros",
        "budapest",
        "budapest fovaros",
    }:
        return "fovaros"

    if text.startswith("megyei jogu varos"):
        return "megyei jogu varos"

    if text.startswith("egyeb varos"):
        return "egyeb varos"

    if text.startswith("kozseg"):
        return "kozseg"

    return text



def ksh_key(value):
    text = clean(value)

    if not text:
        return ""

    try:
        return str(int(float(text)))
    except ValueError:
        return text

print("\nNORMALIZÁLÁSI TESZT")
print("Budapest:", county_key("Budapest"))
print("Főváros:", county_key("Főváros"))
print("Főváros településtípus:", type_key("Főváros"))
print("Megyei jogú város(ok):", type_key("Megyei jogú város(ok)"))

def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"Nem találom a fájlt: {path}"
        )

    handle = path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    )

    return handle, csv.DictReader(handle)


def save_csv(filename, columns, rows):
    path = OUTPUT_FOLDER / filename

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=columns
        )
        writer.writeheader()
        writer.writerows(rows)

    print("Mentve:", path.name)


# ============================================================
# 2. PONTOS EGÉSZ DARABSZÁM KIOSZTÁSA
# ============================================================

def allocate_exact(total, weights):
    weights = [
        max(0, int(weight))
        for weight in weights
    ]

    denominator = sum(weights)

    if denominator == 0:
        raise ValueError(
            "Nincs ingázási célérték az adott cellában."
        )

    raw = [
        total * weight / denominator
        for weight in weights
    ]

    allocated = [int(value) for value in raw]

    remaining = total - sum(allocated)

    order = sorted(
        range(len(weights)),
        key=lambda i: (
            -(raw[i] - allocated[i]),
            i
        )
    )

    for index in order[:remaining]:
        allocated[index] += 1

    return allocated


# ============================================================
# 3. TEÁOR SZEKCIÓ
# ============================================================

def teaor_section(value):
    text = clean(value).upper()

    if len(text) == 1 and "A" <= text <= "U":
        return text

    match = re.match(r"^(\d{1,2})", text)

    if not match:
        return "UNKNOWN"

    number = int(match.group(1))

    intervals = [
        (1, 3, "A"),
        (5, 9, "B"),
        (10, 33, "C"),
        (35, 35, "D"),
        (36, 39, "E"),
        (41, 43, "F"),
        (45, 47, "G"),
        (49, 53, "H"),
        (55, 56, "I"),
        (58, 63, "J"),
        (64, 66, "K"),
        (68, 68, "L"),
        (69, 75, "M"),
        (77, 82, "N"),
        (84, 84, "O"),
        (85, 85, "P"),
        (86, 88, "Q"),
        (90, 93, "R"),
        (94, 96, "S"),
        (97, 98, "T"),
        (99, 99, "U"),
    ]

    for lower, upper, section in intervals:
        if lower <= number <= upper:
            return section

    return "UNKNOWN"


# ============================================================
# 4. FŐPROGRAM
# ============================================================

def main():

    required_files = [
        COMPANIES_CSV,
        HIERARCHY_XLSX,
        COMMUTING_DETAIL_CSV,
        COMMUTING_COUNTY_CSV,
        RESIDENTS_CSV,
    ]

    for path in required_files:
        if not path.is_file():
            raise FileNotFoundError(
                f"Hiányzik a bemenet: {path}"
            )

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    print("WORKPLACE CAPACITY V2")
    print("Bemenetek ellenőrizve.")

    # ========================================================
    # 5. TELEPÜLÉSHIERARCHIA
    # ========================================================

    hierarchy = pd.read_excel(
        HIERARCHY_XLSX,
        engine="openpyxl"
    )

    needed = {
        "Helység megnevezése",
        "Helység KSH kódja",
        "Vármegye megnevezése",
        "Településtípus",
    }

    missing = needed - set(hierarchy.columns)

    if missing:
        raise ValueError(
            f"Hiányzó hierarchiaoszlopok: {sorted(missing)}"
        )

    by_ksh = {}
    by_city = defaultdict(set)
    city_names = {}
    ascii_to_city = defaultdict(set)

    for _, row in hierarchy.iterrows():

        name = clean(row["Helység megnevezése"])
        city = city_key(name)

        county = county_key(
            row["Vármegye megnevezése"]
        )

        settlement_type = type_key(
            row["Településtípus"]
        )

        ksh = ksh_key(
            row["Helység KSH kódja"]
        )

        if not city or not county or not ksh:
            continue

        by_ksh[ksh] = (
            county,
            city,
            settlement_type,
            name
        )

        by_city[city].add(county)

        city_names[(county, city)] = (
            "Budapest"
            if city == "budapest"
            else name
        )

        ascii_to_city[
            ascii_key(city)
        ].add(city)

    print(
        "Hierarchia KSH-területek:",
        len(by_ksh)
    )

    # ========================================================
    # 6. KSH INGÁZÁSI ARÁNYOK
    # ========================================================

    ksh_weights = defaultdict(Counter)
    source_categories = Counter()

    handle, reader = read_csv(
        COMMUTING_DETAIL_CSV
    )

    with handle:
        for row in reader:

            category = clean(
                row["ingazas_tipus"]
            )

            if category not in CATEGORIES:
                continue

            county = county_key(
                row["residence_county"]
            )

            settlement_type = type_key(
                row["residence_settlement_type"]
            )

            count = int(row["count"])

            ksh_weights[
                (county, settlement_type)
            ][category] += count

            source_categories[category] += count

    county_weights = defaultdict(Counter)

    for (county, settlement_type), counts in (
        ksh_weights.items()
    ):
        county_weights[county].update(counts)

    # KSH cél: hány ember dolgozik az adott megyében?
    county_ksh_targets = {}

    handle, reader = read_csv(
        COMMUTING_COUNTY_CSV
    )

    with handle:
        for row in reader:
            county = county_key(row["county"])

            county_ksh_targets[county] = int(
                row["workplace_total"]
            )

    # ========================================================
    # 7. NYÁRI LAKÓHELYI FOGLALKOZTATOTTAK
    # ========================================================

    resident_by_city = Counter()
    resident_types = defaultdict(Counter)

    missing_home_ksh = []
    total_residents = 0
    ksh_rows = 0

    handle, reader = read_csv(RESIDENTS_CSV)

    with handle:
        for row in reader:

            ksh_rows += 1

            count = int(
                row["domestic_employed_residents"]
            )

            total_residents += count

            ksh = ksh_key(row["home_ksh"])
            info = by_ksh.get(ksh)

            if info is None:
                missing_home_ksh.append({
                    "home_ksh": ksh,
                    "settlement_label": clean(
                        row.get("city_from_pois")
                    ),
                    "domestic_workers": count
                })
                continue

            county, city, settlement_type, _ = info

            key = (county, city)

            resident_by_city[key] += count
            resident_types[key][settlement_type] += count

    print(
        "Nyári belföldi dolgozók:",
        f"{total_residents:,}"
    )

    # ========================================================
    # 8. MUNKAHELYKAPACITÁSOK
    # ========================================================

    capacity_city = Counter()
    capacity_county = Counter()
    capacity_teaor = Counter()

    unknown_capacity = Counter()
    unknown_names = Counter()
    matching = Counter()

    workplaces = 0
    total_company_capacity = 0

    handle, reader = read_csv(COMPANIES_CSV)

    with handle:
        for row in reader:

            try:
                size = int(
                    float(
                        clean(row["company_size"]) or "0"
                    )
                )
            except ValueError:
                matching["invalid_company_size"] += 1
                continue

            if size <= 0:
                continue

            workplaces += 1
            total_company_capacity += size

            raw_city = city_key(row["settlement"])

            possible_counties = by_city.get(
                raw_city, set()
            )

            match_method = "exact_name"

            # Csak egyértelmű ékezetmentes fallback.
            if len(possible_counties) != 1:

                candidates = ascii_to_city.get(
                    ascii_key(raw_city),
                    set()
                )

                if len(candidates) == 1:

                    proposed = next(iter(candidates))

                    if len(by_city.get(proposed, set())) == 1:
                        raw_city = proposed
                        possible_counties = by_city[proposed]
                        match_method = "unique_ascii_name"

            if len(possible_counties) != 1:

                reason = (
                    "ambiguous_county"
                    if len(possible_counties) > 1
                    else "unknown_city"
                )

                unknown_capacity[reason] += size

                unknown_names[
                    (reason, clean(row["settlement"]))
                ] += size

                continue

            county = next(iter(possible_counties))

            matching[match_method] += size

            key = (county, raw_city)

            capacity_city[key] += size
            capacity_county[county] += size

            section = teaor_section(row["teaor"])

            capacity_teaor[
                (county, section)
            ] += size

    print(
        "Munkahelyek:",
        f"{workplaces:,}"
    )

    print(
        "Összes munkahelykapacitás:",
        f"{total_company_capacity:,}"
    )

    print(
        "Településre feloldott kapacitás:",
        f"{sum(capacity_city.values()):,}"
    )

    # ========================================================
    # 9. TELEPÜLÉSI INGÁZÁSI CÉLÉRTÉKEK BECSLÉSE
    # ========================================================

    home_targets = Counter()
    local_targets = Counter()
    commuter_targets = Counter()
    variable_targets = Counter()

    source_fallback = Counter()

    for key, types in resident_types.items():

        county, city = key

        home = 0
        local = 0
        commuter = 0
        variable = 0

        for settlement_type, count in types.items():

            weights = ksh_weights.get(
                (county, settlement_type)
            )

            if not weights or sum(weights.values()) == 0:

                weights = county_weights.get(county)

                source_fallback[
                    (county, settlement_type)
                ] += count

            if not weights or sum(weights.values()) == 0:
                raise ValueError(
                    "Hiányzó KSH célérték: "
                    f"{county}, {settlement_type}"
                )

            allocation = allocate_exact(
                count,
                [weights[c] for c in CATEGORIES]
            )

            home += allocation[0]
            local += allocation[1]
            commuter += allocation[2]
            variable += allocation[3]

        home_targets[key] = home
        local_targets[key] = local

        commuter_targets[key] = commuter
        variable_targets[key] = variable

    # ========================================================
    # 10. TELEPÜLÉSI KAPACITÁSELLENŐRZÉS
    # ========================================================

    city_rows = []

    county_demand = Counter()
    county_local = Counter()
    county_home = Counter()
    county_variable = Counter()

    county_best_local = Counter()
    county_shortfall = Counter()

    for key, residents in sorted(
        resident_by_city.items()
    ):

        county, city = key

        capacity = capacity_city[key]
        local_target = local_targets[key]

        possible_local = min(
            local_target,
            capacity
        )

        local_shortfall = max(
            0,
            local_target - capacity
        )

        county_demand[county] += residents
        county_local[county] += local_target

        county_home[county] += home_targets[key]
        county_variable[county] += variable_targets[key]

        county_best_local[county] += possible_local
        county_shortfall[county] += local_shortfall

        city_rows.append({
            "county": county,
            "city": city_names.get(key, city),
            "resident_domestic_workers": residents,
            "estimated_home_based": home_targets[key],
            "estimated_onsite_local_target": local_target,
            "estimated_commuters": commuter_targets[key],
            "estimated_variable": variable_targets[key],
            "mapped_company_capacity_in_city": capacity,
            "max_possible_local_onsite": possible_local,
            "local_shortfall_with_mapped_capacity": local_shortfall,
        })

    save_csv(
        "01_settlement_capacity_v2.csv",
        list(city_rows[0]),
        city_rows
    )

    # ========================================================
    # 11. VÁRMEGYEI KAPACITÁSMÉRLEG
    # ========================================================

    source_home_by_county = Counter()

    for (county, settlement_type), counts in (
        ksh_weights.items()
    ):
        source_home_by_county[county] += counts[HOME]

    county_rows = []

    all_counties = sorted(
        set(county_demand)
        | set(capacity_county)
        | set(county_ksh_targets)
    )

    for county in all_counties:

        original_target = county_ksh_targets.get(
            county, 0
        )

        # Modellfeltevés: az otthoni munkavégzéshez
        # nem szükséges külön fizikai munkahely-slot.
        onsite_target = max(
            0,
            original_target - source_home_by_county[county]
        )

        county_rows.append({
            "county": county,
            "residents_domestic_workers": county_demand[county],
            "estimated_home_based": county_home[county],
            "estimated_onsite_local_target": county_local[county],
            "estimated_variable_last": county_variable[county],
            "company_capacity_mapped": capacity_county[county],
            "ksh_total_domestic_workplace_county": original_target,
            "ksh_estimated_nonhome_worksite_target": onsite_target,
            "mapped_capacity_minus_nonhome_target":
                capacity_county[county] - onsite_target,
            "max_possible_onsite_local": county_best_local[county],
            "local_shortfall_with_mapped_capacity": county_shortfall[county],
        })

    save_csv(
        "02_county_capacity_v2.csv",
        list(county_rows[0]),
        county_rows
    )

    # ========================================================
    # 12. TEÁOR-KAPACITÁSOK
    # ========================================================

    teaor_rows = []

    for (county, section), count in sorted(
        capacity_teaor.items()
    ):
        teaor_rows.append({
            "county": county,
            "teaor_section": section,
            "slots": count
        })

    save_csv(
        "03_county_teaor_capacity_v2.csv",
        ["county", "teaor_section", "slots"],
        teaor_rows
    )

    # ========================================================
    # 13. FEL NEM OLDOTT MUNKAHELYEK
    # ========================================================

    unresolved_rows = []

    for (reason, settlement), count in (
        unknown_names.most_common()
    ):
        unresolved_rows.append({
            "reason": reason,
            "settlement_label": settlement,
            "unresolved_slots": count
        })

    save_csv(
        "04_unresolved_company_locations_v2.csv",
        [
            "reason",
            "settlement_label",
            "unresolved_slots"
        ],
        unresolved_rows
    )

    # ========================================================
    # 14. ORSZÁGOS JELENTÉS
    # ========================================================

    report = [
        "WORKPLACE CAPACITY V2",
        "Ellenőrzés - nem újragenerálás",
        "",
        f"Nyári lakóhelyi KSH-területek: {ksh_rows:,}",
        f"Nyári belföldi dolgozók: {total_residents:,}",
        f"Elvárt belföldi dolgozók: {EXPECTED_DOMESTIC_WORKERS:,}",
        f"Feloldatlan lakóhely-KSH-k: {len(missing_home_ksh):,}",
        "",
        f"Eredeti munkahelyek: {workplaces:,}",
        f"Eredeti munkahelykapacitás: {total_company_capacity:,}",
        f"Településre feloldott kapacitás: {sum(capacity_city.values()):,}",
        f"Feloldatlan munkahelykapacitás: {sum(unknown_capacity.values()):,}",
        "",
        f"Becsült HOME: {sum(home_targets.values()):,}",
        f"Becsült LOCAL: {sum(local_targets.values()):,}",
        f"Becsült COMMUTER: {sum(commuter_targets.values()):,}",
        f"Becsült VARIABLE: {sum(variable_targets.values()):,}",
        "",
        "LOCAL hiány csak a feloldott kapacitás alapján:",
        f"{sum(county_shortfall.values()):,}",
        "",
        "County x settlement_type helyett county fallback:",
        f"{sum(source_fallback.values()):,} dolgozó",
        "",
        "FONTOS MEGJEGYZÉSEK:",
        "- A települési ingázási kategóriák becslések.",
        "- Az eredeti KSH-tábla vármegye és településtípus szerinti.",
        "- A helyi kapacitás felső korlát, nem kész hozzárendelés.",
        "- A feloldatlan településnevek torzíthatják a hiánybecslést.",
        "- Az otthon dolgozók fizikai slot nélküli kezelése modellfeltevés.",
        "- A változó településen dolgozók kiosztása utoljára történne.",
        "- TEÁOR szerint itt csak a munkahelyi kínálatot mérjük.",
        "- Az eredeti fájlok változatlanok.",
    ]

    report_text = "\n".join(report)

    (
        OUTPUT_FOLDER / "05_report_hu_v2.txt"
    ).write_text(
        report_text,
        encoding="utf-8"
    )

    if missing_home_ksh:
        save_csv(
            "06_unresolved_home_ksh_v2.csv",
            [
                "home_ksh",
                "settlement_label",
                "domestic_workers"
            ],
            missing_home_ksh
        )

    print()
    print(report_text)

    if total_residents != EXPECTED_DOMESTIC_WORKERS:
        print(
            "FIGYELMEZTETÉS: a belföldi dolgozók "
            "száma eltér a 144-es referenciaértékétől!"
        )

    if ksh_rows != EXPECTED_KSH_AREAS:
        print(
            "FIGYELMEZTETÉS: a KSH-területek száma "
            "eltér a korábban ellenőrzött értéktől!"
        )

    print()
    print("KÉSZ.")
    print("Kimenet:", OUTPUT_FOLDER)


if __name__ == "__main__":
    main()
