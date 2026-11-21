
from pathlib import Path
from collections import Counter
import csv

# ============================================================
# COMMUTING RULES V2
# KSH-alapu ingazasi szabalyok a nyari generalashoz.
#
# FONTOS:
# - Nem olvas 29d vagy 144-es adatokat.
# - Nem oszt ki munkahelyeket.
# - Nem irja felul a regi commuting_matrix.csv-t.
# ============================================================

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "data/processed/commuting_v2"

DETAIL = BASE / "02_kategoria_es_telepulestipus_v2.csv"
COUNTY_CHECK = BASE / "03_megyei_flow_kategoriankent_v2.csv"
MATRIX_CHECK = BASE / "04_commuting_matrix_v2_all_domestic.csv"

HOME = "Lakóhelyén foglalkoztatott"
LOCAL = "Lakóhely településén foglalkoztatott"
COMMUTER = "Más magyarországi településen foglalkoztatott"
VARIABLE = "Változó településen foglalkoztatott"
FOREIGN = "Külföldön foglalkoztatott"

DOMESTIC = (HOME, LOCAL, COMMUTER, VARIABLE)

EXPECTED = {
    HOME: 317245,
    LOCAL: 2427801,
    COMMUTER: 1581405,
    VARIABLE: 269628,
    FOREIGN: 122581,
}


def load_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f"Hiányzik: {path}")

    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as f:
        return list(csv.DictReader(f))


def write_csv(name, fields, rows):
    target = BASE / name

    with target.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Mentve: {target.name} ({len(rows)} sor)"
    )


def main():
    detail = load_csv(DETAIL)

    category_totals = Counter()
    group_categories = Counter()
    group_work_categories = Counter()

    county_check_new = Counter()
    all_domestic_new = Counter()

    # ========================================================
    # 1. KSH ADATOK BEOLVASASA
    # ========================================================

    for row in detail:
        home = row["residence_county"].strip()
        kind = row["residence_settlement_type"].strip()
        work = row["workplace_county"].strip()
        category = row["ingazas_tipus"].strip()
        count = int(row["count"])

        if (
            category not in (*DOMESTIC, FOREIGN)
            or count < 0
        ):
            raise ValueError(
                f"Hibas KSH kategoria/darabszam: {row}"
            )

        if not home or not kind or not work:
            raise ValueError(
                f"Hianyos foldrajzi kulcs: {row}"
            )

        # Helyben dolgozok nem lehetnek mas megyeben.
        if (
            category in (HOME, LOCAL)
            and work != home
        ):
            raise ValueError(
                f"Helyben dolgozo mas megyeben: {row}"
            )

        if category == FOREIGN and work != "Külföld":
            raise ValueError(
                f"Kulfoldi kategoria hibas munkahellyel: {row}"
            )

        if category != FOREIGN and work == "Külföld":
            raise ValueError(
                f"Belfoldi kategoria kulfoldi munkahellyel: {row}"
            )

        category_totals[category] += count

        group_categories[
            (home, kind, category)
        ] += count

        group_work_categories[
            (home, kind, category, work)
        ] += count

        county_check_new[
            (home, work, category)
        ] += count

        if category != FOREIGN:
            all_domestic_new[
                (home, work)
            ] += count

    # ========================================================
    # 2. ORSZAGOS VALIDACIO
    # ========================================================

    if dict(category_totals) != EXPECTED:
        raise ValueError(
            "KSH orszagos letszamelteres: "
            f"{category_totals}"
        )

    # Ellenorzes a korabbi 03-as tablaval.
    county_check_old = Counter()

    for row in load_csv(COUNTY_CHECK):
        key = (
            row["residence_county"],
            row["workplace_county"],
            row["ingazas_tipus"],
        )
        county_check_old[key] += int(row["count"])

    if county_check_new != county_check_old:
        raise ValueError(
            "A 02-es es 03-as megyei "
            "kategoriak elternek!"
        )

    # Ellenorzes a korabbi 04-es matrixszal.
    matrix_old = Counter()

    for row in load_csv(MATRIX_CHECK):
        key = (
            row["residence_county"],
            row["workplace_county"],
        )
        matrix_old[key] += int(row["count"])

    if all_domestic_new != matrix_old:
        raise ValueError(
            "A 02-es es 04-es megyei "
            "matrixok elternek!"
        )

    # ========================================================
    # 3. KATEGORIA-VALOSZINUSEGEK
    # ========================================================

    groups = sorted({
        (home, kind)
        for home, kind, _ in group_categories
    })

    if len(groups) != 58:
        raise ValueError(
            f"58 csoport helyett {len(groups)}"
        )

    category_rows = []
    commute_rows = []
    variable_rows = []
    audit_rows = []

    for home, kind in groups:

        domestic_total = sum(
            group_categories[(home, kind, c)]
            for c in DOMESTIC
        )

        if domestic_total == 0:
            raise ValueError(
                f"Ures belfoldi csoport: {home}, {kind}"
            )

        for category in DOMESTIC:
            count = group_categories[
                (home, kind, category)
            ]

            category_rows.append({
                "residence_county": home,
                "residence_settlement_type": kind,
                "commuting_category": category,
                "census_count": count,
                "probability_among_domestic":
                    f"{count / domestic_total:.12f}",
            })

        # ====================================================
        # 4. MUNKAHELYI CELMEGYE
        # ====================================================

        for category, target_rows in (
            (COMMUTER, commute_rows),
            (VARIABLE, variable_rows),
        ):

            category_total = group_categories[
                (home, kind, category)
            ]

            if category_total == 0:
                continue

            for (
                h, k, c, work
            ), count in sorted(
                group_work_categories.items()
            ):
                if (
                    h != home
                    or k != kind
                    or c != category
                    or count == 0
                ):
                    continue

                target_rows.append({
                    "residence_county": home,
                    "residence_settlement_type": kind,
                    "workplace_county": work,
                    "census_count": count,
                    "probability_within_category":
                        f"{count / category_total:.12f}",
                })

        audit_rows.append({
            "residence_county": home,
            "residence_settlement_type": kind,
            "domestic_total": domestic_total,
            "home": group_categories[
                (home, kind, HOME)
            ],
            "local": group_categories[
                (home, kind, LOCAL)
            ],
            "commuter": group_categories[
                (home, kind, COMMUTER)
            ],
            "variable": group_categories[
                (home, kind, VARIABLE)
            ],
            "foreign_separate": group_categories[
                (home, kind, FOREIGN)
            ],
        })

    # ========================================================
    # 5. KIMENETEK
    # ========================================================

    write_csv(
        "09_commuting_category_probabilities_v2.csv",
        [
            "residence_county",
            "residence_settlement_type",
            "commuting_category",
            "census_count",
            "probability_among_domestic",
        ],
        category_rows,
    )

    write_csv(
        "10_commuter_destinations_v2.csv",
        [
            "residence_county",
            "residence_settlement_type",
            "workplace_county",
            "census_count",
            "probability_within_category",
        ],
        commute_rows,
    )

    write_csv(
        "11_variable_destinations_REFERENCE_v2.csv",
        [
            "residence_county",
            "residence_settlement_type",
            "workplace_county",
            "census_count",
            "probability_within_category",
        ],
        variable_rows,
    )

    write_csv(
        "12_commuting_groups_audit_v2.csv",
        [
            "residence_county",
            "residence_settlement_type",
            "domestic_total",
            "home",
            "local",
            "commuter",
            "variable",
            "foreign_separate",
        ],
        audit_rows,
    )

    # ========================================================
    # 6. OSSZEFOGLALO
    # ========================================================

    same_county_commuters = sum(
        count
        for (
            home, _, cat, work
        ), count in group_work_categories.items()
        if cat == COMMUTER and home == work
    )

    summary = [
        "COMMUTING RULES V2",
        "",
        f"KSH csoportok: {len(groups)}",
        "Belfoldi dolgozok: 4,596,079",
        "Kulfoldi dolgozok: 122,581",
        "",
        f"HOME: {category_totals[HOME]:,}",
        f"LOCAL: {category_totals[LOCAL]:,}",
        f"COMMUTER: {category_totals[COMMUTER]:,}",
        f"VARIABLE: {category_totals[VARIABLE]:,}",
        "",
        "Ingázók azonos megye mas telepulesere: "
        f"{same_county_commuters:,}",
        "Ingázók mas megyebe: "
        f"{category_totals[COMMUTER] - same_county_commuters:,}",
        "",
        "02 vs 03: OK",
        "02 vs 04: OK",
        "29d / 144 nem szerepel a bemenetek kozott.",
        "",
        "A tenyleges munkahelykiosztas meg hatravan.",
    ]

    report = BASE / "13_commuting_rules_report_v2.txt"

    report.write_text(
        "\n".join(summary),
        encoding="utf-8"
    )

    print()
    print("\n".join(summary))
    print()
    print("KESZ - commuting szabalyok eloallitva.")


if __name__ == "__main__":
    main()
