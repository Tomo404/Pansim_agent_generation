
from pathlib import Path
from collections import Counter
from itertools import zip_longest
import csv

ROOT = Path(__file__).resolve().parent

OLD = ROOT / "data/processed/agents.csv"
NEW = ROOT / "data/processed/agents_with_workplaces_v2.csv"

KSH = (
    ROOT / "data/processed/commuting_v2/"
           "04_commuting_matrix_v2_all_domestic.csv"
)

FEOR_NAMES = (
    ROOT / "data/processed/feor_list_from_docx.csv"
)

OUT = ROOT / "data/validation/workplaces_v2"


def percent(n, total):
    return round(n * 100 / total, 2) if total else 0.0


def save(name, rows):
    if not rows:
        return

    with (OUT / name).open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=rows[0].keys()
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    for path in (OLD, NEW, KSH):
        if not path.is_file():
            raise FileNotFoundError(path)

    people = 0
    assigned = 0
    same_county = 0
    target_kept = 0
    changed_sector = 0

    changed_agent_fields = Counter()

    home_counts = Counter()
    home_local = Counter()
    home_missing = Counter()

    feor_counts = Counter()
    feor_mismatches = Counter()
    methods = Counter()

    wp_users = Counter()
    wp_size = {}
    inconsistent_wp_size = 0

    # ====================================================
    # 1. EREDETI ES UJ AGENSTABLA OSSZEHASONLITASA
    # ====================================================

    with OLD.open(
        newline="", encoding="utf-8-sig"
    ) as orig, NEW.open(
        newline="", encoding="utf-8-sig"
    ) as result:

        reader_old = csv.DictReader(orig)
        reader_new = csv.DictReader(result)

        core = (
            "agent_id",
            "county",
            "teaor_code",
            "feor_code",
            "gender",
            "age_group",
            "education",
        )

        for a, b in zip_longest(
            reader_old, reader_new
        ):
            if a is None or b is None:
                raise ValueError(
                    "Eltero sorok szama a ket agenstablan!"
                )

            people += 1

            if a["agent_id"] != b["agent_id"]:
                raise ValueError(
                    f"Megvaltozott az agenssorrend: {people}. sor"
                )

            for field in core:
                if a[field] != b[field]:
                    changed_agent_fields[field] += 1

            county = b["county"].strip()
            feor = b["feor_code"].strip()
            workplace = b["workplace_id"].strip()

            home_counts[county] += 1
            feor_counts[feor or "(hiányzik)"] += 1
            methods[b["fallback_level"]] += 1

            if not workplace:
                home_missing[county] += 1
                continue

            assigned += 1

            work_county = b["workplace_county"].strip()

            if work_county == county:
                home_local[county] += 1
                same_county += 1

            if work_county == b["target_work_county"].strip():
                target_kept += 1

            if (
                b["teaor_code"].strip().upper()
                != b["workplace_teaor_code"].strip().upper()
            ):
                changed_sector += 1
                feor_mismatches[
                    feor or "(hiányzik)"
                ] += 1

            size = int(b["workplace_size"])

            if (
                workplace in wp_size
                and wp_size[workplace] != size
            ):
                inconsistent_wp_size += 1

            wp_size[workplace] = size
            wp_users[workplace] += 1

            if people % 500_000 == 0:
                print(f"Ellenorizve: {people:,}")

    # ====================================================
    # 2. KSH MEGYEI REFERENCIA
    # ====================================================

    ksh_people = Counter()
    ksh_local = Counter()

    with KSH.open(
        newline="", encoding="utf-8-sig"
    ) as f:
        for row in csv.DictReader(f):
            home = row["residence_county"].strip()
            count = int(row["count"])

            ksh_people[home] += count

            if home == row["workplace_county"].strip():
                ksh_local[home] += count

    county_rows = []

    for county in sorted(
        set(home_counts) | set(ksh_people)
    ):
        actual_pct = percent(
            home_local[county], home_counts[county]
        )
        reference_pct = percent(
            ksh_local[county], ksh_people[county]
        )

        county_rows.append({
            "county": county,
            "agents": home_counts[county],
            "missing_workplaces": home_missing[county],
            "same_county_agents": home_local[county],
            "same_county_pct": actual_pct,
            "ksh_same_county_pct": reference_pct,
            "difference_percentage_points":
                round(actual_pct - reference_pct, 2),
        })

    save("01_county_comparison.csv", county_rows)

    # ====================================================
    # 3. FEOR KODOK ES FOGLALKOZASNEVEK
    # ====================================================

    feor_names = {}

    if FEOR_NAMES.exists():
        with FEOR_NAMES.open(
            newline="", encoding="utf-8-sig"
        ) as f:
            feor_names = {
                row["feor_code"].strip():
                    row["feor_name"].strip()
                for row in csv.DictReader(f)
            }

    feor_rows = []

    for code, count in feor_counts.most_common():
        feor_rows.append({
            "feor_code": code,
            "feor_name": feor_names.get(code, ""),
            "agents": count,
            "different_workplace_teaor":
                feor_mismatches[code],
            "different_pct": percent(
                feor_mismatches[code], count
            ),
        })

    save("02_feor_check.csv", feor_rows)

    # ====================================================
    # 4. KAPACITAS ES JELENTES
    # ====================================================

    overfilled = sum(
        wp_users[wp] > size
        for wp, size in wp_size.items()
    )

    report = [
        f"Agensek: {people:,}",
        f"Munkahellyel: {assigned:,}",
        f"Munkahely nelkul: {people-assigned:,}",
        (
            f"Sajat varmegye: {same_county:,} "
            f"({percent(same_county, people)}%)"
        ),
        (
            "KSH referencia sajat varmegye: "
            f"{percent(sum(ksh_local.values()), sum(ksh_people.values()))}%"
        ),
        (
            f"Celmegye megtartva: {target_kept:,} "
            f"({percent(target_kept, people)}%)"
        ),
        (
            f"Mas munkahelyi TEAOR: {changed_sector:,} "
            f"({percent(changed_sector, assigned)}%)"
        ),
        f"Hianyzo FEOR: {feor_counts['(hiányzik)']:,}",
        f"Kulonbozo FEOR-kodok: {len(feor_counts):,}",
        (
            "Megvaltozott eredeti agensadatok: "
            f"{dict(changed_agent_fields)}"
        ),
        f"Kapacitas feletti munkahelyek: {overfilled:,}",
        (
            "Inkonzisztens workplace_size mezok: "
            f"{inconsistent_wp_size:,}"
        ),
        f"Fallback: {dict(sorted(methods.items()))}",
        "",
        "A FEOR megorzese nem bizonyitja a FEOR es "
        "a munkahely TEAOR szakmai osszhangjat.",
    ]

    (OUT / "03_report.txt").write_text(
        "\n".join(report),
        encoding="utf-8"
    )

    print("\n".join(report))
    print("Kimenetek:", OUT)


if __name__ == "__main__":
    main()
