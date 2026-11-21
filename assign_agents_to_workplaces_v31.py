"""V3.1 - KSH ingazasi iranyokat vedo munkahely-kiosztas."""

from pathlib import Path
from collections import Counter
import csv
import random

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

import assign_agents_to_workplaces_v3 as v3


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

COMPANIES = (
    ROOT / "data/raw/generated_companies_county_calibrated_v2.csv"
)

OUT_DIR = ROOT / "data/processed"

OUT_AGENTS = OUT_DIR / "agents_with_workplaces_v31.csv"
OUT_REPORT = OUT_DIR / "workplace_assignment_v31_report.txt"
OUT_COUNTIES = OUT_DIR / "workplace_counties_v31.csv"
OUT_OD = OUT_DIR / "workplace_od_v31.csv"
OUT_COMPARE = OUT_DIR / "workplace_od_v31_vs_ksh.csv"

OLD_OD = OUT_DIR / "workplace_od_v3_recalibrated.csv"

SEED = 20261121


# ============================================================
# 1. KSH OD-MATRIX KIEGYENSULYOZASA
# ============================================================

def balance_od(ksh, residents, capacities):

    n = len(residents)

    shortage = int(residents.sum() - capacities.sum())

    if shortage < 0:
        raise ValueError(
            "Tobb worker slot van, mint dolgozo. "
            "Ehhez kulon ures-slot kezeles kell."
        )

    target_cols = np.append(
        capacities, shortage
    ).astype(np.int64)

    # A KSH orszagos sajat megyei aranyat megorizzuk.
    target_local = int(round(
        residents.sum() * np.trace(ksh) / ksh.sum()
    ))

    def fit(diagonal_multiplier):

        weights = ksh.astype(float).copy()

        weights[np.diag_indices(n)] *= diagonal_multiplier

        # Kulon oszlop a kapacitas nelkul maradt dolgozoknak.
        missing_weight = np.maximum(
            ksh.sum(axis=1) * max(shortage, 1) / ksh.sum(),
            0.01
        )

        weights = np.column_stack(
            (weights, missing_weight)
        )

        if shortage == 0:
            weights[:, -1] = 0.0

        x = weights

        # Iterative Proportional Fitting (IPF / RAS).
        for it in range(6000):

            rows = x.sum(axis=1)

            if np.any(rows <= 0):
                raise RuntimeError("IPF: ures sor")

            x *= (residents / rows)[:, None]

            cols = x.sum(axis=0)

            factor = np.divide(
                target_cols,
                cols,
                out=np.zeros_like(cols),
                where=cols > 0
            )

            x *= factor[None, :]

            if it % 25 == 0:
                error = np.max(
                    np.abs(x.sum(axis=1) - residents)
                )
                if error < 1e-6:
                    break

        if np.max(
            np.abs(x.sum(axis=1) - residents)
        ) >= 1e-4:
            raise RuntimeError(
                "A megyei OD kiegyensulyozas nem konvergalt"
            )

        return x

    # A sajat megyei kapcsolatok sulyanak beallitasa.
    lo, hi = 0.01, 100.0

    if (
        np.trace(fit(lo)[:, :n]) > target_local
        or np.trace(fit(hi)[:, :n]) < target_local
    ):
        raise RuntimeError(
            "Az orszagos KSH helyi arany nem erheto el."
        )

    for _ in range(34):

        mid = (lo + hi) / 2
        x = fit(mid)

        if np.trace(x[:, :n]) < target_local:
            lo = mid
        else:
            hi = mid

    real = fit((lo + hi) / 2)

    # ========================================================
    # 2. EGESZ DOLGOZOI LETSZAMOKRA KEREKITES
    # ========================================================

    whole = np.floor(
        real + 1e-8
    ).astype(np.int64)

    row_need = residents - whole.sum(axis=1)
    col_need = target_cols - whole.sum(axis=0)

    if np.any(row_need < 0) or np.any(col_need < 0):
        raise AssertionError("Hibas kerekitest megelozo maradek")

    count = n * (n + 1)
    indices = np.arange(count)

    matrix = coo_matrix(
        (
            np.ones(2 * count),
            (
                np.r_[
                    indices // (n + 1),
                    n + indices % (n + 1)
                ],
                np.r_[indices, indices]
            )
        ),
        shape=(2 * n + 1, count)
    ).tocsr()

    fraction = (real - whole).ravel()

    solved = linprog(
        c=1 - 2 * fraction,
        A_eq=matrix,
        b_eq=np.r_[row_need, col_need],
        bounds=(0, 1),
        method="highs"
    )

    if not solved.success:
        raise RuntimeError(
            "OD-kerekites sikertelen: " + solved.message
        )

    rounded = whole + np.rint(
        solved.x
    ).astype(np.int64).reshape(n, n + 1)

    if not np.array_equal(
        rounded.sum(axis=1), residents
    ):
        raise AssertionError("Hibas OD sorosszegek")

    if not np.array_equal(
        rounded.sum(axis=0), target_cols
    ):
        raise AssertionError("Hibas OD oszloposszegek")

    return rounded, target_local


# ============================================================
# 3. KORABBI V3 OD BEOLVASASA OSSZEHASONLITASHOZ
# ============================================================

def get_old_od(counties):

    n = len(counties)
    result = np.zeros((n, n), dtype=np.int64)

    if not OLD_OD.is_file():
        return None

    index = {
        county: i
        for i, county in enumerate(counties)
    }

    with OLD_OD.open(
        newline="", encoding="utf-8-sig"
    ) as f:

        for row in csv.DictReader(f):

            home = v3.base.normalize_county(
                row["residence_county"]
            )

            work = v3.base.normalize_county(
                row["workplace_county"]
            )

            result[index[home], index[work]] += int(
                row["count"]
            )

    return result


# ============================================================
# 4. MUNKAHELYEK KIOSZTASA
# ============================================================

def run():

    for file in (
        COMPANIES,
        v3.AGENTS,
        v3.COMMUTING
    ):
        if not file.is_file():
            raise FileNotFoundError(file)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # A rekalibralt cegek hasznalata.
    v3.base.COMPANIES_FILE = COMPANIES

    counties, county_id, ksh = v3.read_ksh()

    residents, agent_count = v3.count_agents(
        county_id
    )

    workplaces, pools, capacity = v3.load_workplaces(
        county_id
    )

    plan, target_local = balance_od(
        ksh, residents, capacity
    )

    n = len(counties)
    shortage = agent_count - int(capacity.sum())

    print(
        "KSH sajat megyei arany:",
        round(100 * np.trace(ksh) / ksh.sum(), 3), "%"
    )

    print(
        "V3.1 tervezett sajat megyei arany:",
        round(
            100 * np.trace(plan[:, :n]) / agent_count,
            3
        ), "%"
    )

    print(
        "Tervezett munkahely nelkul maradok:",
        int(plan[:, -1].sum())
    )

    # ========================================================
    # PASS 1 - SAJAT MEGYEI DOLGOZOK
    # ========================================================

    assigned_wp = np.full(
        agent_count, -1, dtype=np.int32
    )

    methods = np.zeros(
        agent_count, dtype=np.uint8
    )

    target = np.full(
        agent_count, -1, dtype=np.int8
    )

    take = v3.make_assignment_pools(pools)

    rng = random.Random(SEED)

    left_total = residents.copy()
    left_local = np.diag(plan[:, :n]).copy()

    with v3.AGENTS.open(
        newline="", encoding="utf-8-sig"
    ) as f:

        for idx, row in enumerate(csv.DictReader(f)):

            home_i = county_id[
                v3.base.normalize_county(row["county"])
            ]

            if rng.randrange(
                int(left_total[home_i])
            ) < int(left_local[home_i]):

                wp, teaor_fallback = take(
                    home_i,
                    row["teaor_code"].strip().upper()
                )

                assigned_wp[idx] = wp
                target[idx] = home_i

                methods[idx] = (
                    2 if teaor_fallback else 1
                )

                left_local[home_i] -= 1

            left_total[home_i] -= 1

    if np.any(left_local != 0):
        raise AssertionError(
            "Nem teljesult a helyi megyei kvota"
        )

    # ========================================================
    # PASS 2 - MEGYEK KOZOTTI INGAZAS
    # ========================================================

    remaining = plan.copy()

    np.fill_diagonal(
        remaining[:, :n], 0
    )

    with v3.AGENTS.open(
        newline="", encoding="utf-8-sig"
    ) as f:

        for idx, row in enumerate(csv.DictReader(f)):

            if assigned_wp[idx] >= 0:
                continue

            home_i = county_id[
                v3.base.normalize_county(row["county"])
            ]

            choices = remaining[home_i]
            total = int(choices.sum())

            if total < 1:
                raise AssertionError(
                    "Elfogyott a megyei OD-kvota"
                )

            draw = rng.randrange(total)

            destination = int(
                np.searchsorted(
                    np.cumsum(choices),
                    draw,
                    side="right"
                )
            )

            remaining[home_i, destination] -= 1

            if destination == n:
                # Nincs szabad worker slot.
                continue

            wp, teaor_fallback = take(
                destination,
                row["teaor_code"].strip().upper()
            )

            assigned_wp[idx] = wp
            target[idx] = destination

            methods[idx] = (
                4 if teaor_fallback else 3
            )

    if np.any(remaining):
        raise AssertionError(
            "Fel nem hasznalt OD-kvota"
        )

    # ========================================================
    # PASS 3 - VEGEREDMENY MENTESE
    # ========================================================

    actual = np.zeros(
        (n, n), dtype=np.int64
    )

    missing_by_county = Counter()
    use = Counter()
    method_counts = Counter()

    assigned = 0

    with (
        v3.AGENTS.open(
            newline="", encoding="utf-8-sig"
        ) as fin,
        OUT_AGENTS.open(
            "w", newline="", encoding="utf-8-sig"
        ) as fout
    ):

        reader = csv.DictReader(fin)
        columns = reader.fieldnames or []

        writer = csv.DictWriter(
            fout,
            fieldnames=columns + v3.NEW_FIELDS
        )

        writer.writeheader()

        for idx, row in enumerate(reader):

            code = int(methods[idx])

            method_counts[v3.METHOD[code]] += 1

            wp_idx = int(assigned_wp[idx])

            home = v3.base.normalize_county(
                row["county"]
            )

            if wp_idx < 0:

                missing_by_county[home] += 1

                row.update({
                    c: "" for c in v3.NEW_FIELDS
                })

                row.update({
                    "fallback_level": v3.METHOD[0],
                    "used_fallback": True,
                    "used_teaor_fallback": False
                })

            else:

                (
                    wp_id,
                    work,
                    sector,
                    settlement,
                    settlement_type,
                    size
                ) = workplaces[wp_idx]

                use[wp_idx] += 1

                actual[
                    county_id[home],
                    county_id[work]
                ] += 1

                assigned += 1

                row.update({
                    "target_work_county":
                        counties[int(target[idx])],
                    "final_work_county": work,
                    "used_fallback": code in (2, 4),
                    "fallback_level": v3.METHOD[code],
                    "used_teaor_fallback":
                        sector != row["teaor_code"].strip().upper(),
                    "workplace_id": wp_id,
                    "workplace_county": work,
                    "workplace_teaor_code": sector,
                    "workplace_settlement": settlement,
                    "workplace_settlement_type": settlement_type,
                    "workplace_size": size
                })

            writer.writerow(row)

            if (idx + 1) % 500_000 == 0:
                print(
                    f"Kimentve: {idx + 1:,} agens"
                )

    # ========================================================
    # 5. ELLENORZESEK
    # ========================================================

    if any(
        count > workplaces[idx][5]
        for idx, count in use.items()
    ):
        raise AssertionError(
            "Tul van toltve egy munkahely!"
        )

    if (
        assigned != int(capacity.sum())
        or agent_count - assigned != shortage
    ):
        raise AssertionError(
            "Hibas orszagos munkahelykapacitas"
        )

    if not np.array_equal(
        actual, plan[:, :n]
    ):
        raise AssertionError(
            "A tenyleges OD elter a tervtol"
        )

    old = get_old_od(counties)

    # ========================================================
    # 6. OD KIMENET
    # ========================================================

    with OUT_OD.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:

        w = csv.writer(f)

        w.writerow([
            "residence_county",
            "workplace_county",
            "count"
        ])

        for i in range(n):
            for j in range(n):
                w.writerow([
                    counties[i],
                    counties[j],
                    int(actual[i, j])
                ])

    # ========================================================
    # 7. KSH / V3 / V3.1 OSSZEHASONLITAS
    # ========================================================

    with OUT_COMPARE.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:

        w = csv.writer(f)

        w.writerow([
            "residence_county",
            "workplace_county",
            "KSH_count",
            "old_V3_count",
            "V31_count",
            "V31_minus_KSH"
        ])

        for i in range(n):
            for j in range(n):

                w.writerow([
                    counties[i],
                    counties[j],
                    int(ksh[i, j]),
                    (
                        ""
                        if old is None
                        else int(old[i, j])
                    ),
                    int(actual[i, j]),
                    int(actual[i, j] - ksh[i, j])
                ])

    # ========================================================
    # 8. VÁRMEGYEI OSSZESITES
    # ========================================================

    with OUT_COUNTIES.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:

        w = csv.writer(f)

        w.writerow([
            "county",
            "residents",
            "worker_slots",
            "KSH_local_pct",
            "V31_local_pct",
            "local_difference_pp",
            "KSH_incoming",
            "V31_incoming",
            "KSH_outgoing",
            "V31_outgoing",
            "unassigned"
        ])

        for i, county in enumerate(counties):

            local = int(actual[i, i])

            own_pct = (
                100 * local / residents[i]
            )

            ksh_pct = (
                100 * ksh[i, i] / ksh[i].sum()
            )

            w.writerow([
                county,
                int(residents[i]),
                int(capacity[i]),
                round(ksh_pct, 3),
                round(own_pct, 3),
                round(own_pct - ksh_pct, 3),
                int(ksh[:, i].sum() - ksh[i, i]),
                int(actual[:, i].sum() - local),
                int(ksh[i].sum() - ksh[i, i]),
                int(actual[i].sum() - local),
                missing_by_county[county]
            ])

    # ========================================================
    # 9. REPORT
    # ========================================================

    own = int(np.trace(actual))
    nonlocal_count = assigned - own

    def tv_nonlocal(matrix):

        x = matrix.astype(float).copy()

        np.fill_diagonal(x, 0)

        return x / x.sum()

    tv_old = (
        None
        if old is None
        else 0.5 * np.abs(
            tv_nonlocal(ksh) - tv_nonlocal(old)
        ).sum()
    )

    tv_new = 0.5 * np.abs(
        tv_nonlocal(ksh) - tv_nonlocal(actual)
    ).sum()

    lines = [
        "SPRING WORKPLACE ASSIGNMENT V3.1 - BALANCED OD",
        f"Agents: {agent_count:,}",
        f"Assigned: {assigned:,}",
        f"Unassigned: {shortage:,}",
        f"Workplace slots: {int(capacity.sum()):,}",
        f"Own-county: {own:,} "
        f"({100 * own / agent_count:.3f}%)",
        f"KSH own-county benchmark: "
        f"{100 * np.trace(ksh) / ksh.sum():.3f}%",
        f"Own-county target before rounding: {target_local:,}",
        f"Cross-county commuters: {nonlocal_count:,}",
        f"KSH cross-county workers: "
        f"{int(ksh.sum() - np.trace(ksh)):,}",
        f"Nonlocal OD TV distance V3.1: {tv_new:.5f}",
        f"Nonlocal OD TV distance old V3: {tv_old}",
        "Overfilled workplaces: 0",
        "Assignment methods:"
    ]

    lines.extend(
        f"  {k}: {v:,}"
        for k, v in sorted(method_counts.items())
    )

    lines.extend([
        "",
        "NOTE: County OD is balanced, not exact KSH replication.",
        "NOTE: No exact residence settlement in spring agents.",
        "NOTE: Original agent FEOR and TEAOR unchanged."
    ])

    OUT_REPORT.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print("\n".join(lines))

    print("\nGenerated files:")
    print(OUT_AGENTS)
    print(OUT_REPORT)
    print(OUT_COUNTIES)
    print(OUT_OD)
    print(OUT_COMPARE)


if __name__ == "__main__":
    run()