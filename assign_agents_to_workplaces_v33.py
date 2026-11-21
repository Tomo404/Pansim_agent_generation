
"""V3.3 - KSH ingazasi kapcsolatok vedelme.

A V3.2 sajat megyei dolgozoi es kiosztatlan letszamait megtartjuk.
Kizarolag a megyek kozotti ingazasi celpontokat rendezzuk at.
"""

from pathlib import Path
import csv

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import (
    eye, csr_matrix, lil_matrix, hstack, vstack
)

import assign_agents_to_workplaces_v31 as v31


# ============================================================
# BEMENETEK ES PARAMETEREK
# ============================================================

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data/processed"

COMPANIES = (
    ROOT / "data/raw/generated_companies_county_calibrated_v2.csv"
)

V32_OD = OUT / "workplace_od_v32.csv"
V32_COUNTIES = OUT / "workplace_counties_v32.csv"

# A KSH szerinti, lakomegyere normalizalt kapcsolat
# vart letszamanak legalabb 10%-at vedjuk.
MIN_FLOW_FRACTION = 0.10

# Legfeljebb kb. 0.25 szazalekpontnyi romlast engedunk
# a lakomegyenkenti ingazasi celpont-eloszlasban.
# Kisebb tartalek a vegso egeszre kerekiteshez.
MAX_ROW_TV_EXTRA = 0.0021

ROW_DISTRIBUTION_WEIGHT = 0.15


# ============================================================
# V3.2 ADATOK BETOLTESE
# ============================================================

def read_previous(counties):
    index = {
        name: i for i, name in enumerate(counties)
    }

    n = len(counties)

    old = np.zeros(
        (n, n), dtype=np.int64
    )

    missing = np.zeros(
        n, dtype=np.int64
    )

    with V32_OD.open(
        newline="", encoding="utf-8-sig"
    ) as f:
        for row in csv.DictReader(f):

            home = v31.v3.base.normalize_county(
                row["residence_county"]
            )

            work = v31.v3.base.normalize_county(
                row["workplace_county"]
            )

            old[index[home], index[work]] += int(
                row["count"]
            )

    with V32_COUNTIES.open(
        newline="", encoding="utf-8-sig"
    ) as f:
        for row in csv.DictReader(f):

            home = v31.v3.base.normalize_county(
                row["county"]
            )

            missing[index[home]] = int(
                row["unassigned"]
            )

    return old, missing


# ============================================================
# ELTERESI MERTEKEK
# ============================================================

def nonlocal_tv(ksh, result):

    a = ksh.astype(float).copy()
    b = result.astype(float).copy()

    np.fill_diagonal(a, 0)
    np.fill_diagonal(b, 0)

    return 0.5 * np.abs(
        a / a.sum() - b / b.sum()
    ).sum()


def row_tv(ksh, result):

    a = ksh.astype(float).copy()
    b = result.astype(float).copy()

    np.fill_diagonal(a, 0)
    np.fill_diagonal(b, 0)

    return 0.5 * np.abs(
        a / a.sum(axis=1)[:, None]
        - b / b.sum(axis=1)[:, None]
    ).sum(axis=1)


# ============================================================
# V3.3 OD-TERV OPTIMALIZALASA
# ============================================================

def create_v33_plan(
    ksh, residents, capacity, old, missing
):

    n = len(residents)

    # A V3.2 adatok egyezzenek a jelenlegi bemenetekkel.
    if old.shape != (n, n):
        raise ValueError("Eltero V3.2 OD-matrixmeret.")

    if not np.array_equal(
        old.sum(axis=1) + missing,
        residents
    ):
        raise ValueError(
            "A V3.2 lakomegyei letszamai elternek "
            "az eredeti agensallomanytol."
        )

    if not np.array_equal(
        old.sum(axis=0), capacity
    ):
        raise ValueError(
            "A V3.2 kapacitasai elternek "
            "a rekalibralt cegallomanytol."
        )

    # Csak a kulonbozo varmegye-párokat modosítjuk.
    edges = [
        (i, j)
        for i in range(n)
        for j in range(n)
        if i != j
    ]

    m = len(edges)

    old_cross = old.copy()
    np.fill_diagonal(old_cross, 0)

    row_need = old_cross.sum(axis=1)
    col_need = old_cross.sum(axis=0)

    ksh_cross = ksh.copy()
    np.fill_diagonal(ksh_cross, 0)

    ksh_row = ksh_cross.sum(axis=1)

    if np.any(ksh_row <= 0) or np.any(row_need <= 0):
        raise ValueError(
            "Van olyan megye, ahonnan nincs ingazo."
        )

    # Orszagos KSH OD-celaranyok.
    global_goal = np.array([
        row_need.sum()
        * ksh_cross[i, j]
        / ksh_cross.sum()
        for i, j in edges
    ])

    # Lakomegyenkenti KSH celpont-aranyok.
    home_goal = np.array([
        row_need[i]
        * ksh_cross[i, j]
        / ksh_row[i]
        for i, j in edges
    ])

    # Vedett minimum az egyes kapcsolatokra.
    minimum = np.array([
        max(
            1,
            int(np.floor(
                MIN_FLOW_FRACTION * home_goal[e]
            ))
        )
        if ksh_cross[i, j] > 0 else 0
        for e, (i, j) in enumerate(edges)
    ])

    # ========================================================
    # SOR- ES OSZLOPOSSZEGEK MEGORZESE
    # ========================================================

    A = lil_matrix(
        (2 * n, m), dtype=float
    )

    for e, (i, j) in enumerate(edges):
        A[i, e] = 1
        A[n + j, e] = 1

    A = A.tocsr()

    rhs = np.r_[
        row_need, col_need
    ].astype(float)

    # ========================================================
    # ABSZOLUT ELTERES OPTIMALIZALASA
    # ========================================================

    I = eye(m, format="csr")
    Z = csr_matrix((m, m))

    deviations = vstack([
        hstack([I, -I, Z]),
        hstack([-I, -I, Z]),
        hstack([I, Z, -I]),
        hstack([-I, Z, -I]),
    ], format="csr")

    # A V3.2 lakomegyenkenti TV-ertekeinel
    # legfeljebb kis romlast engedunk.
    old_row_tv = row_tv(ksh, old)

    row_limits = lil_matrix(
        (n, 3 * m), dtype=float
    )

    for e, (i, j) in enumerate(edges):
        row_limits[i, 2 * m + e] = 1

    limit_rhs = (
        2 * row_need
        * (old_row_tv + MAX_ROW_TV_EXTRA)
    )

    A_ub = vstack([
        deviations,
        row_limits.tocsr()
    ], format="csr")

    b_ub = np.r_[
        global_goal,
        -global_goal,
        home_goal,
        -home_goal,
        limit_rhs
    ]

    A_eq = hstack([
        A,
        csr_matrix((2 * n, 2 * m))
    ], format="csr")

    objective = np.r_[
        np.zeros(m),
        np.ones(m),
        np.full(
            m, ROW_DISTRIBUTION_WEIGHT
        )
    ]

    bounds = (
        [(int(value), None) for value in minimum]
        + [(0, None)] * (2 * m)
    )

    print(
        "V3.3 OD-optimalizalas: "
        f"{m} megye-kozi kapcsolat..."
    )

    fit = linprog(
        objective,
        A_eq=A_eq,
        b_eq=rhs,
        A_ub=A_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs"
    )

    if not fit.success:
        raise RuntimeError(
            "Az OD minimumok es a megyei aranyok "
            "egyutt nem teljesithetok: "
            + fit.message
        )

    # ========================================================
    # EGESZ DOLGOZOI LETSZAMOK
    # ========================================================

    fractional = fit.x[:m]

    whole = np.floor(
        fractional + 1e-7
    ).astype(np.int64)

    row_left = row_need.copy()
    col_left = col_need.copy()

    for value, (i, j) in zip(whole, edges):
        row_left[i] -= value
        col_left[j] -= value

    if (
        np.any(row_left < 0)
        or np.any(col_left < 0)
    ):
        raise AssertionError(
            "Negativ maradek a kerekitesnel."
        )

    rounded = linprog(
        1 - 2 * (fractional - whole),
        A_eq=A,
        b_eq=np.r_[row_left, col_left],
        bounds=[(0, 1)] * m,
        method="highs"
    )

    if not rounded.success:
        raise RuntimeError(
            "Az OD egeszre kerekitese nem sikerult: "
            + rounded.message
        )

    if np.max(np.abs(
        rounded.x - np.rint(rounded.x)
    )) > 1e-5:
        raise AssertionError(
            "Nem egesz eredmeny a matrixkerekitesnel."
        )

    whole += np.rint(
        rounded.x
    ).astype(np.int64)

    # A diagonalison levo sajat megyei dolgozok
    # pontosan a V3.2-bol jonnek.
    result = old.copy()

    for count, (i, j) in zip(whole, edges):
        result[i, j] = int(count)

    # 21. oszlop: a V3.2 szerinti kiosztatlanok.
    plan = np.column_stack([
        result, missing
    ])

    # ========================================================
    # ELLENORZESEK
    # ========================================================

    if not np.array_equal(
        plan.sum(axis=1), residents
    ):
        raise AssertionError(
            "Hibas lakomegyei sorosszeg."
        )

    if not np.array_equal(
        plan[:, :n].sum(axis=0), capacity
    ):
        raise AssertionError(
            "Hibas munkahelyi kapacitas."
        )

    if not np.array_equal(
        np.diag(result), np.diag(old)
    ):
        raise AssertionError(
            "Megvaltozott a sajat megyei letszam."
        )

    if not np.array_equal(
        plan[:, -1], missing
    ):
        raise AssertionError(
            "Megvaltozott a kiosztatlanok eloszlasa."
        )

    for count, low in zip(whole, minimum):
        if count < low:
            raise AssertionError(
                "Nem teljesult egy vedett KSH minimum."
            )

    before = nonlocal_tv(ksh, old)
    after = nonlocal_tv(ksh, result)

    old_local_tv = row_tv(ksh, old)
    new_local_tv = row_tv(ksh, result)

    protected_before = sum(
        ksh_cross[i, j] >= 500
        and old[i, j] <= 1
        for i, j in edges
    )

    protected_after = sum(
        ksh_cross[i, j] >= 500
        and result[i, j] <= 1
        for i, j in edges
    )

    print(f"V3.2 orszagos OD TV: {before * 100:.3f}%")
    print(f"V3.3 orszagos OD TV: {after * 100:.3f}%")

    print(
        "500+ KSH-kapcsolat 1 fore csokkenve:",
        protected_before,
        "->",
        protected_after
    )

    print(
        "Legnagyobb lakomegyei TV-romlas (pp):",
        round(
            100 * np.max(
                new_local_tv - old_local_tv
            ),
            4
        )
    )

    return plan, int(np.trace(result))


# ============================================================
# KIMENETI OSZLOPNEVEK
# ============================================================

def change_header(path, replacements):

    with path.open(
        newline="", encoding="utf-8-sig"
    ) as f:
        data = list(csv.reader(f))

    data[0] = [
        replacements.get(col, col)
        for col in data[0]
    ]

    with path.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        csv.writer(f).writerows(data)


# ============================================================
# FUTTATAS
# ============================================================

def main():

    for path in (
        COMPANIES,
        V32_OD,
        V32_COUNTIES
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    # A V3.1 kiprobalt kiosztasi mechanizmusa.
    # A cegtablat nem valtoztatjuk meg.
    v31.COMPANIES = COMPANIES
    v31.OLD_OD = V32_OD

    # Kulon V3.3 fajlok.
    v31.OUT_AGENTS = (
        OUT / "agents_with_workplaces_v33.csv"
    )

    v31.OUT_REPORT = (
        OUT / "workplace_assignment_v33_report.txt"
    )

    v31.OUT_COUNTIES = (
        OUT / "workplace_counties_v33.csv"
    )

    v31.OUT_OD = (
        OUT / "workplace_od_v33.csv"
    )

    v31.OUT_COMPARE = (
        OUT / "workplace_od_v33_vs_ksh.csv"
    )

    v31.SEED = 20261123

    def make_plan(ksh, residents, capacity):

        counties = sorted(
            v31.v3.base.normalize_county(x)
            for x in v31.v3.read_ksh()[0]
        )

        old, missing = read_previous(counties)

        return create_v33_plan(
            ksh,
            residents,
            capacity,
            old,
            missing
        )

    # Csak az OD-tervezo fuggvenyt csereljuk.
    v31.balance_od = make_plan

    v31.run()

    # A V3.1-bol orokolt jelentescimek atnevezese.
    report = v31.OUT_REPORT.read_text(
        encoding="utf-8"
    )

    report = report.replace(
        "V3.1 - BALANCED OD",
        "V3.3 - PROTECTED CONNECTIONS"
    )

    report = report.replace(
        "Nonlocal OD TV distance V3.1:",
        "Nonlocal OD TV distance V3.3:"
    )

    report = report.replace(
        "Nonlocal OD TV distance old V3:",
        "Nonlocal OD TV distance V3.2:"
    )

    report += (
        "\nNOTE: V3.2 local counts and per-county "
        "unassigned counts were held constant.\n"
    )

    v31.OUT_REPORT.write_text(
        report,
        encoding="utf-8"
    )

    change_header(
        v31.OUT_COUNTIES,
        {
            "V31_local_pct": "V33_local_pct",
            "V31_incoming": "V33_incoming",
            "V31_outgoing": "V33_outgoing",
        }
    )

    change_header(
        v31.OUT_COMPARE,
        {
            "old_V3_count": "V32_count",
            "V31_count": "V33_count",
            "V31_minus_KSH": "V33_minus_KSH",
        }
    )

    print("\nV3.3 kesz.")
    print("Riport:", v31.OUT_REPORT)
    print("Megyei eredmenyek:", v31.OUT_COUNTIES)
    print("OD osszehasonlitas:", v31.OUT_COMPARE)


if __name__ == "__main__":
    main()
