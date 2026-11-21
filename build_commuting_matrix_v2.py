
from pathlib import Path
from collections import Counter
import csv
import pandas as pd

# ============================================================
# build_commuting_matrix_v2.py
# KSH-ingazasi Excel ujrafeldolgozasa.
# A regi commuting_matrix.csv NEM lesz felulirva.
# ============================================================

ROOT = Path(__file__).resolve().parent

INPUT_FILE = (
    ROOT / "data/raw/hier_foglalkoztatott_ingazas.xlsx"
)

OUTPUT_FOLDER = ROOT / "data/processed/commuting_v2"

CATEGORY_HOME = "Lakóhelyén foglalkoztatott"
CATEGORY_LOCAL = "Lakóhely településén foglalkoztatott"
CATEGORY_COMMUTE = "Más magyarországi településen foglalkoztatott"
CATEGORY_FOREIGN = "Külföldön foglalkoztatott"
CATEGORY_VARIABLE = "Változó településen foglalkoztatott"

CATEGORIES = (
    CATEGORY_HOME,
    CATEGORY_LOCAL,
    CATEGORY_COMMUTE,
    CATEGORY_FOREIGN,
    CATEGORY_VARIABLE,
)

FIXED_DOMESTIC = {
    CATEGORY_HOME,
    CATEGORY_LOCAL,
    CATEGORY_COMMUTE,
}

EXPECTED_DOMESTIC = 4_596_079
EXPECTED_FOREIGN = 122_581


# ============================================================
# 1. SEGEDFUGGVENYEK
# ============================================================

def clean(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def parse_count(value, excel_row, excel_col):
    if value is None or pd.isna(value):
        return 0

    if str(value).strip() == "":
        return 0

    try:
        number = float(value)

        if number < 0 or not number.is_integer():
            raise ValueError("Negativ vagy nem egesz szam")

        return int(number)

    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Hibas darabszam az Excel {excel_row}. soraban, "
            f"{excel_col}. oszlopaban: {value!r}"
        ) from error


def save_dict_rows(path, columns, rows):
    with path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns
        )
        writer.writeheader()
        writer.writerows(rows)

    print("Mentve:", path.name)


def percent(part, total):
    if total == 0:
        return 0.0
    return 100.0 * part / total


# ============================================================
# 2. EXCEL BEOLVASASA
# ============================================================

def main():
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"Nem talalom a KSH Excelt: {INPUT_FILE}\n"
            "A kod legyen az agent_generation projekt gyokereben."
        )

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    print("Forras:", INPUT_FILE)

    df = pd.read_excel(
        INPUT_FILE,
        header=None,
        engine="openpyxl",
    )

    print(
        "Excel merete:",
        df.shape[0], "sor x",
        df.shape[1], "oszlop"
    )

    # --------------------------------------------------------
    # F1-tol: lakóhelyi varmegye + telepulestipus.
    # A fejlecben osszevont cellak vannak.
    # --------------------------------------------------------

    home_info_by_col = {}
    active_home_county = ""

    for col in range(5, df.shape[1]):
        header_county = clean(df.iat[0, col])

        if header_county:
            active_home_county = header_county

        if active_home_county:
            home_info_by_col[col] = (
                active_home_county,
                clean(df.iat[1, col]),
            )

    valid_counties = {
        county
        for county, _ in home_info_by_col.values()
    }

    if len(valid_counties) != 20:
        raise ValueError(
            "20 hazai varmegye/fovaros helyett "
            f"{len(valid_counties)} fejlecet talaltam: "
            f"{sorted(valid_counties)}"
        )

    # ========================================================
    # 3. FLOW-K FELDOLGOZASA
    # ========================================================

    categories = Counter()

    by_home_type_category_and_work = Counter()
    by_home_work_category = Counter()

    by_home_work_all_domestic = Counter()
    by_home_work_fixed_domestic = Counter()

    # Regi kod szerinti irany,
    # kizarolag osszehasonlitasra.
    legacy_orientation = Counter()

    unusual = Counter()

    current_work_county = ""

    for row_no, values in enumerate(
        df.itertuples(index=False, name=None),
        start=1,
    ):
        if row_no <= 2:
            continue

        # D oszlop: munkavegzes helye.
        if clean(values[3]):
            current_work_county = clean(values[3])

        # E oszlop: ingazasi kategoria.
        category = clean(values[4])

        if not category:
            continue

        if category not in CATEGORIES:
            unusual[("unknown_category", category)] += 1
            continue

        if not current_work_county:
            raise ValueError(
                f"Hianyzik a D oszlop megyéje: sor {row_no}"
            )

        # F oszloptol: lakohelyi varmegye.
        for col, (
            home_county,
            home_type,
        ) in home_info_by_col.items():

            count = parse_count(
                values[col],
                row_no,
                col + 1,
            )

            if count == 0:
                continue

            categories[category] += count

            by_home_type_category_and_work[
                (
                    home_county,
                    home_type,
                    current_work_county,
                    category,
                )
            ] += count

            by_home_work_category[
                (
                    home_county,
                    current_work_county,
                    category,
                )
            ] += count

            # -----------------------------------------------
            # KULFOLDI FOGLALKOZTATOTTAK
            # -----------------------------------------------

            if category == CATEGORY_FOREIGN:
                if current_work_county != "Külföld":
                    unusual[
                        (
                            "foreign_category_nonforeign_D",
                            current_work_county,
                        )
                    ] += count

                continue

            # -----------------------------------------------
            # REGI IRANY OSSZEHASONLITASHOZ
            # -----------------------------------------------

            legacy_orientation[
                (
                    current_work_county,
                    home_county,
                )
            ] += count

            # -----------------------------------------------
            # BELFOLDI MUNKAHELYEK
            # -----------------------------------------------

            if current_work_county not in valid_counties:
                unusual[
                    (
                        "domestic_category_noncounty_D",
                        current_work_county,
                    )
                ] += count
                continue

            by_home_work_all_domestic[
                (
                    home_county,
                    current_work_county,
                )
            ] += count

            if category in FIXED_DOMESTIC:
                by_home_work_fixed_domestic[
                    (
                        home_county,
                        current_work_county,
                    )
                ] += count

            # Ha sajat telepulesen dolgozik,
            # a varmegye sem lehet kulonbozo.
            if (
                category in {CATEGORY_HOME, CATEGORY_LOCAL}
                and home_county != current_work_county
            ):
                unusual[
                    ("local_category_cross_county", category)
                ] += count

        if row_no % 3000 == 0:
            print(
                f"Feldolgozott Excel-sorok: {row_no:,}"
            )

    # ========================================================
    # 4. KATEGORIAK ORSZAGOS OSSZESITESE
    # ========================================================

    category_rows = [
        {
            "ingazas_tipus": key,
            "count": categories[key],
            "share_of_all_percent": round(
                percent(
                    categories[key],
                    sum(categories.values()),
                ),
                4,
            ),
        }
        for key in CATEGORIES
    ]

    save_dict_rows(
        OUTPUT_FOLDER / "01_ingazasi_kategoriak_v2.csv",
        [
            "ingazas_tipus",
            "count",
            "share_of_all_percent",
        ],
        category_rows,
    )

    # ========================================================
    # 5. RESZLETES FLOW KATEGORIA ES TELEPULESTIPUS SZERINT
    # ========================================================

    detailed_rows = [
        {
            "residence_county": home,
            "residence_settlement_type": home_type,
            "workplace_county": work,
            "ingazas_tipus": category,
            "count": count,
        }
        for (
            home,
            home_type,
            work,
            category,
        ), count in sorted(
            by_home_type_category_and_work.items()
        )
    ]

    save_dict_rows(
        OUTPUT_FOLDER / "02_kategoria_es_telepulestipus_v2.csv",
        [
            "residence_county",
            "residence_settlement_type",
            "workplace_county",
            "ingazas_tipus",
            "count",
        ],
        detailed_rows,
    )

    # ========================================================
    # 6. MEGYEI FLOW KATEGORIANKENT
    # ========================================================

    tagged_rows = [
        {
            "residence_county": home,
            "workplace_county": work,
            "ingazas_tipus": category,
            "count": count,
        }
        for (
            home,
            work,
            category,
        ), count in sorted(by_home_work_category.items())
    ]

    save_dict_rows(
        OUTPUT_FOLDER / "03_megyei_flow_kategoriankent_v2.csv",
        [
            "residence_county",
            "workplace_county",
            "ingazas_tipus",
            "count",
        ],
        tagged_rows,
    )

    # ========================================================
    # 7. KETFELE BELFOLDI MATRIX
    # ========================================================

    def write_matrix(path, matrix):
        rows = [
            {
                "residence_county": home,
                "workplace_county": work,
                "count": count,
            }
            for (
                home,
                work,
            ), count in sorted(matrix.items())
        ]

        save_dict_rows(
            path,
            [
                "residence_county",
                "workplace_county",
                "count",
            ],
            rows,
        )

    # Minden belfoldi kategoria,
    # a valtozo munkavegzesi hellyel egyutt.
    write_matrix(
        OUTPUT_FOLDER / "04_commuting_matrix_v2_all_domestic.csv",
        by_home_work_all_domestic,
    )

    # Csak fix munkavegzesi helyu kategoriak.
    write_matrix(
        OUTPUT_FOLDER / "05_commuting_matrix_v2_fixed_only.csv",
        by_home_work_fixed_domestic,
    )

    # ========================================================
    # 8. VARMEGYEI MERLEGEK
    # ========================================================

    residence_totals = Counter()
    workplace_totals = Counter()

    for (
        home,
        work,
    ), count in by_home_work_all_domestic.items():

        residence_totals[home] += count
        workplace_totals[work] += count

    county_rows = []

    for county in sorted(valid_counties):
        local = by_home_work_all_domestic[
            (county, county)
        ]

        county_rows.append({
            "county": county,
            "residence_total": residence_totals[county],
            "workplace_total": workplace_totals[county],
            "same_county": local,
            "same_county_percent": round(
                percent(
                    local,
                    residence_totals[county],
                ),
                4,
            ),
            "net_inflow": (
                workplace_totals[county]
                - residence_totals[county]
            ),
        })

    save_dict_rows(
        OUTPUT_FOLDER / "06_varmegyei_merleg_v2.csv",
        [
            "county",
            "residence_total",
            "workplace_total",
            "same_county",
            "same_county_percent",
            "net_inflow",
        ],
        county_rows,
    )

    # ========================================================
    # 9. REGI ES UJ IRANY OSSZEHASONLITASA
    # ========================================================

    def get_pair(matrix, home, work):
        return matrix.get((home, work), 0)

    cases = [
        ("Pest vármegye", "Budapest"),
        ("Budapest", "Pest vármegye"),
    ]

    direction_rows = []

    for home, work in cases:
        direction_rows.append({
            "residence": home,
            "workplace": work,
            "old_code_interpretation": get_pair(
                legacy_orientation,
                home,
                work,
            ),
            "new_interpretation": get_pair(
                by_home_work_all_domestic,
                home,
                work,
            ),
        })

    save_dict_rows(
        OUTPUT_FOLDER / "07_irany_osszehasonlitas_v2.csv",
        [
            "residence",
            "workplace",
            "old_code_interpretation",
            "new_interpretation",
        ],
        direction_rows,
    )

    # ========================================================
    # 10. ORSZAGOS VALIDACIO
    # ========================================================

    total_all = sum(categories.values())

    total_domestic = (
        total_all - categories[CATEGORY_FOREIGN]
    )

    total_assignable = sum(
        by_home_work_all_domestic.values()
    )

    total_fixed = sum(
        by_home_work_fixed_domestic.values()
    )

    diagonal = sum(
        count
        for (
            home,
            work,
        ), count in by_home_work_all_domestic.items()
        if home == work
    )

    local_category_total = (
        categories[CATEGORY_HOME]
        + categories[CATEGORY_LOCAL]
    )

    foreign_other_D = sum(
        count
        for (name, _), count in unusual.items()
        if name == "foreign_category_nonforeign_D"
    )

    noncounty_domestic = sum(
        count
        for (name, _), count in unusual.items()
        if name == "domestic_category_noncounty_D"
    )

    cross_local = sum(
        count
        for (name, _), count in unusual.items()
        if name == "local_category_cross_county"
    )

    report = [
        "COMMUTING MATRIX V2 - KSH ELLENORZES",
        "",
        f"Excel: {INPUT_FILE}",
        f"Forras osszesen: {total_all:,}",
        (
            f"Belfoldi dolgozok: {total_domestic:,} "
            f"(vart: {EXPECTED_DOMESTIC:,})"
        ),
        (
            f"Kulfoldi dolgozok: {categories[CATEGORY_FOREIGN]:,} "
            f"(vart: {EXPECTED_FOREIGN:,})"
        ),
        f"Megyehez rendelheto belfoldi: {total_assignable:,}",
        f"Fix munkahely-kategoria: {total_fixed:,}",
        (
            "Valtozo telepulesen dolgozik: "
            f"{categories[CATEGORY_VARIABLE]:,}"
        ),
        (
            "Sajat telepulesen vagy otthon dolgozik: "
            f"{local_category_total:,} "
            f"({percent(local_category_total, total_all):.2f}% az osszesbol)"
        ),
        (
            "Sajat MEGYEBEN dolgozik: "
            f"{diagonal:,} "
            f"({percent(diagonal, total_assignable):.2f}%)"
        ),
        "",
        "IRANY OSSZEHASONLITASA:",
        (
            "Pest -> Budapest: "
            "regi="
            f"{get_pair(legacy_orientation, 'Pest vármegye', 'Budapest'):,}, "
            "uj="
            f"{get_pair(by_home_work_all_domestic, 'Pest vármegye', 'Budapest'):,}"
        ),
        (
            "Budapest -> Pest: "
            "regi="
            f"{get_pair(legacy_orientation, 'Budapest', 'Pest vármegye'):,}, "
            "uj="
            f"{get_pair(by_home_work_all_domestic, 'Budapest', 'Pest vármegye'):,}"
        ),
        "",
        (
            "Kulfoldinek jelolt, de D nem Kulfold: "
            f"{foreign_other_D:,}"
        ),
        (
            "Belfoldi kategoria, de D nem magyar megye: "
            f"{noncounty_domestic:,}"
        ),
        (
            "Helyben dolgozik, de eltero megye: "
            f"{cross_local:,}"
        ),
        "",
        "FIGYELEM: a 04-es es 05-os fajl meg ellenorzesi kimenet.",
        "A kovetkezo kiosztasi kodhoz csak a validacio utan kotjuk.",
        "A valtozo munkahelyu dolgozokat kulon kell kezelni.",
    ]

    report_path = (
        OUTPUT_FOLDER / "08_report_hu_v2.txt"
    )

    report_path.write_text(
        "\n".join(report),
        encoding="utf-8",
    )

    print("\n".join(report))

    print()
    print("KESZ.")
    print("A regi commuting_matrix.csv valtozatlan.")
    print("Kimeneti mappa:", OUTPUT_FOLDER)


if __name__ == "__main__":
    main()
