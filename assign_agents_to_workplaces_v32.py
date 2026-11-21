from pathlib import Path
import csv

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

import assign_agents_to_workplaces_v31 as v31


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data/processed"

COMPANIES = ROOT / "data/raw/generated_companies_county_calibrated_v2.csv"
OLD_OD = OUT / "workplace_od_v31.csv"
OLD_COUNTIES = OUT / "workplace_counties_v31.csv"

# Legfeljebb ennyivel romolhat egy vármegye saját
# megyei arányának KSH-eltérése a V3.1-hez képest.
MAX_LOCAL_EXTRA_PP = 0.5

# Vármegyénként az ingázási kördiagram TV-eltérése
# legfeljebb ennyivel romolhat a V3.1-hez képest.
# Kisebb biztonsági tartalékot hagyunk a kerekítésre.
MAX_ROW_TV_EXTRA_PP = 0.45

# A kiosztatlan dolgozók vármegyénkénti korlátai:
# 0,05% és 0,50% az ott lakó foglalkoztatottakból.
MIN_MISSING_RATE = 0.0005
MAX_MISSING_RATE = 0.005


def load_previous_od(counties):
    if not OLD_OD.exists():
        raise FileNotFoundError(
            f"Hiányzik a V3.1 OD-tábla: {OLD_OD}"
        )

    index = {county: i for i, county in enumerate(counties)}
    old = np.zeros(
        (len(counties), len(counties)),
        dtype=np.int64
    )

    with OLD_OD.open(
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

    return old


def tv_distance(reference, actual):
    a = reference.astype(float).copy()
    b = actual.astype(float).copy()

    np.fill_diagonal(a, 0)
    np.fill_diagonal(b, 0)

    return 0.5 * np.abs(
        a / a.sum() - b / b.sum()
    ).sum()


def optimize_od(ksh, residents, capacity, old):
    n = len(residents)

    residents = np.asarray(residents, dtype=np.int64)
    capacity = np.asarray(capacity, dtype=np.int64)

    shortage = int(residents.sum() - capacity.sum())

    if shortage < 0:
        raise ValueError(
            "Több férőhely van, mint dolgozó."
        )

    if old.shape != (n, n):
        raise ValueError("A V3.1 OD-mátrix mérete hibás.")

    if old.sum() != capacity.sum():
        raise ValueError(
            "A V3.1 kiosztott létszáma nem egyezik "
            "a jelenlegi kapacitással."
        )

    # Országos KSH szerinti saját megyei arány.
    target_local = int(round(
        residents.sum() * np.trace(ksh) / ksh.sum()
    ))

    expected_local = (
        residents * np.diag(ksh) / ksh.sum(axis=1)
    )

    expected_missing = (
        residents * shortage / residents.sum()
    )

    off_pairs = [
        (i, j)
        for i in range(n)
        for j in range(n)
        if i != j
    ]

    noff = len(off_pairs)

    ksh_cross = ksh.sum() - np.trace(ksh)
    target_cross = int(capacity.sum()) - target_local

    scaled_cross = (
        ksh * (target_cross / ksh_cross)
    )

    cross_by_home = (
        ksh.sum(axis=1) - np.diag(ksh)
    )

    if np.any(cross_by_home <= 0):
        raise ValueError(
            "Van olyan megye, amelyből nincs "
            "KSH szerinti ingázás."
        )

    # V3.1 lakómegyénkénti kördiagram-eltérései.
    old_row_tv = np.zeros(n)

    for i in range(n):
        reference = ksh[i].astype(float).copy()
        reference[i] = 0
        reference /= reference.sum()

        actual = old[i].astype(float).copy()
        actual[i] = 0

        if actual.sum() == 0:
            raise ValueError(
                f"A V3.1-ben a(z) {i}. megye "
                "nem rendelkezik ingázóval."
            )

        actual /= actual.sum()

        old_row_tv[i] = (
            0.5 * np.abs(reference - actual).sum()
        )

    # =====================================================
    # LINEÁRIS OPTIMALIZÁLÁS
    # =====================================================

    # x: 20 x 21 OD mátrix
    #    21. oszlop = munkahely nélkül maradók
    #
    # A többi változó az eltérések abszolút értéke:
    # a = országos OD
    # b = saját megyei cél
    # d = hiányzók eloszlása
    # e = lakómegyénkénti ingázási kördiagram

    nx = n * (n + 1)

    pa = nx
    pb = pa + noff
    pd = pb + n
    pe = pd + n

    nvars = pe + noff

    objective = np.zeros(nvars)

    objective[pa:pb] = 1.0
    objective[pb:pd] = 0.1
    objective[pd:pe] = 0.1

    for a, (i, j) in enumerate(off_pairs):
        objective[pe + a] = (
            0.1 * target_cross /
            (n * cross_by_home[i])
        )

    def xidx(i, j):
        return i * (n + 1) + j

    # Minden lakómegyéből pontosan annyi dolgozó
    # induljon, amennyi a szintetikus állományban van.
    #
    # Minden munkahelyi vármegye pontosan a saját
    # kapacitását használja el.
    #
    # Az országos saját megyei kvóta is kötött.

    eq = lil_matrix((2 * n + 1, nvars))

    rhs_eq = np.r_[
        residents,
        capacity,
        target_local
    ].astype(float)

    for i in range(n):
        for j in range(n + 1):
            eq[i, xidx(i, j)] = 1

        eq[2 * n, xidx(i, i)] = 1

    for j in range(n):
        for i in range(n):
            eq[n + j, xidx(i, j)] = 1

    # =====================================================
    # ELTÉRÉSEK KORLÁTOZÁSA
    # =====================================================

    ndev = noff + n + n + noff

    ub = lil_matrix(
        (2 * ndev + n, nvars)
    )

    rhs_ub = np.zeros(2 * ndev + n)

    t = 0

    def add_abs_bound(entries, target, error_idx):
        nonlocal t

        for sign in (1, -1):
            for column, value in entries:
                ub[t, column] = sign * value

            ub[t, error_idx] = -1
            rhs_ub[t] = sign * target
            t += 1

    # Országos megye-megye ingázási eltérés.
    for a, (i, j) in enumerate(off_pairs):
        add_abs_bound(
            [(xidx(i, j), 1)],
            scaled_cross[i, j],
            pa + a
        )

    # Saját megyei dolgozók.
    for i in range(n):
        add_abs_bound(
            [(xidx(i, i), 1)],
            expected_local[i],
            pb + i
        )

    # Munkahely nélkül maradók eloszlása.
    for i in range(n):
        add_abs_bound(
            [(xidx(i, n), 1)],
            expected_missing[i],
            pd + i
        )

    # Lakómegyénkénti ingázási célpontok.
    for a, (i, j) in enumerate(off_pairs):
        q = ksh[i, j] / cross_by_home[i]

        add_abs_bound(
            [
                (xidx(i, j), 1),
                (xidx(i, i), q),
                (xidx(i, n), q),
            ],
            q * residents[i],
            pe + a
        )

    # A vármegyénkénti kördiagram-eltérés ne
    # romolhasson lényegesen a V3.1-hez képest.
    for i in range(n):
        allowed = (
            old_row_tv[i]
            + MAX_ROW_TV_EXTRA_PP / 100
        )

        for a, (home, dest) in enumerate(off_pairs):
            if home == i:
                ub[t, pe + a] = 1

        ub[t, xidx(i, i)] = 2 * allowed
        ub[t, xidx(i, n)] = 2 * allowed

        rhs_ub[t] = 2 * allowed * residents[i]
        t += 1

    if t != ub.shape[0]:
        raise AssertionError(
            "Hibás optimalizálási feltételek."
        )

    # =====================================================
    # FÉRŐHELY- ÉS ARÁNYKORLÁTOK
    # =====================================================

    bounds = [(0, None)] * nvars

    # Minden, KSH-ban létező ingázási kapcsolat
    # legalább egy dolgozót kapjon.
    for i, j in off_pairs:
        bounds[xidx(i, j)] = (
            1 if ksh[i, j] > 0 else 0,
            None
        )

    for i in range(n):
        old_local_pct = old[i, i] / residents[i]
        ksh_local_pct = (
            ksh[i, i] / ksh[i].sum()
        )

        permitted_difference = (
            abs(old_local_pct - ksh_local_pct)
            + MAX_LOCAL_EXTRA_PP / 100
        )

        lower = max(
            0,
            (ksh_local_pct - permitted_difference)
            * residents[i]
        )

        upper = min(
            residents[i],
            capacity[i],
            (ksh_local_pct + permitted_difference)
            * residents[i]
        )

        if lower > upper:
            raise ValueError(
                f"Nem teljesíthető saját megyei "
                f"korlát a(z) {i}. megyénél."
            )

        bounds[xidx(i, i)] = (lower, upper)

        bounds[xidx(i, n)] = (
            int(np.floor(
                MIN_MISSING_RATE * residents[i]
            )) if shortage else 0,
            int(np.ceil(
                MAX_MISSING_RATE * residents[i]
            )) if shortage else 0
        )

    print("V3.2 OD-optimalizálás...")

    result = linprog(
        objective,
        A_eq=eq.tocsr(),
        b_eq=rhs_eq,
        A_ub=ub.tocsr(),
        b_ub=rhs_ub,
        bounds=bounds,
        method="highs"
    )

    if not result.success:
        raise RuntimeError(
            "Az OD-optimalizálás sikertelen: "
            + result.message
        )

    real = result.x[:nx].reshape(n, n + 1)

    # =====================================================
    # EGÉSZ DOLGOZÓI LÉTSZÁMOKRA KEREKÍTÉS
    # =====================================================

    local = np.diag(real[:, :n])

    own = np.floor(
        local + 1e-7
    ).astype(np.int64)

    needed = target_local - int(own.sum())

    for i in np.argsort(-(local - own)):
        if needed == 0:
            break

        if own[i] < min(residents[i], capacity[i]):
            own[i] += 1
            needed -= 1

    if needed != 0:
        raise AssertionError(
            "Nem kerekíthető a helyi kvóta."
        )

    nonlocal_real = real.copy()

    for i in range(n):
        nonlocal_real[i, i] = 0

    whole = np.floor(
        nonlocal_real + 1e-7
    ).astype(np.int64)

    row_left = (
        residents - own - whole.sum(axis=1)
    )

    col_left = np.r_[
        capacity - own - whole[:, :n].sum(axis=0),
        shortage - int(whole[:, -1].sum())
    ]

    if np.any(row_left < 0) or np.any(col_left < 0):
        raise AssertionError(
            "Negatív kerekítési maradék."
        )

    edges = [
        (i, j)
        for i in range(n)
        for j in range(n + 1)
        if i != j
    ]

    rounding_eq = lil_matrix(
        (2 * n + 1, len(edges))
    )

    rounding_cost = np.zeros(len(edges))

    for a, (i, j) in enumerate(edges):
        rounding_eq[i, a] = 1
        rounding_eq[n + j, a] = 1

        fraction = (
            nonlocal_real[i, j] - whole[i, j]
        )

        rounding_cost[a] = 1 - 2 * fraction

    rounded = linprog(
        rounding_cost,
        A_eq=rounding_eq.tocsr(),
        b_eq=np.r_[row_left, col_left],
        bounds=(0, 1),
        method="highs"
    )

    if not rounded.success:
        raise RuntimeError(
            "Az OD egészre kerekítése sikertelen: "
            + rounded.message
        )

    if np.max(
        np.abs(rounded.x - np.rint(rounded.x))
    ) > 1e-6:
        raise AssertionError(
            "Nem egész lett a kerekített OD."
        )

    for (i, j), bit in zip(
        edges,
        np.rint(rounded.x).astype(np.int64)
    ):
        whole[i, j] += bit

    for i in range(n):
        whole[i, i] = own[i]

    # =====================================================
    # VÉGSŐ ELLENŐRZÉSEK
    # =====================================================

    if not np.array_equal(
        whole.sum(axis=1), residents
    ):
        raise AssertionError(
            "Hibás lakómegyei sorösszegek."
        )

    if not np.array_equal(
        whole[:, :n].sum(axis=0), capacity
    ):
        raise AssertionError(
            "Hibás munkahelyi kapacitások."
        )

    if int(np.trace(whole[:, :n])) != target_local:
        raise AssertionError(
            "Nem teljesült a helyi országos kvóta."
        )

    if int(whole[:, -1].sum()) != shortage:
        raise AssertionError(
            "Nem megfelelő a kiosztatlan dolgozók száma."
        )

    if np.any(whole < 0):
        raise AssertionError(
            "Negatív OD-érték."
        )

    for i, j in off_pairs:
        if ksh[i, j] > 0 and whole[i, j] == 0:
            raise AssertionError(
                "Eltűnt egy KSH-ingázási kapcsolat."
            )

    old_tv = tv_distance(ksh, old)
    new_tv = tv_distance(ksh, whole[:, :n])

    print(f"V3.1 országos OD TV: {old_tv * 100:.3f}%")
    print(f"V3.2 országos OD TV: {new_tv * 100:.3f}%")
    print(f"Saját megyei dolgozók: {target_local:,}")
    print(f"Munkahely nélkül: {shortage:,}")

    if new_tv >= old_tv:
        raise AssertionError(
            "A V3.2 nem javította az OD-eloszlást."
        )

    return whole, target_local


def rename_csv_columns(path, mapping):
    with path.open(
        newline="", encoding="utf-8-sig"
    ) as f:
        reader = csv.DictReader(f)
        old_columns = reader.fieldnames or []
        records = list(reader)

    with path.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.writer(f)

        writer.writerow([
            mapping.get(col, col)
            for col in old_columns
        ])

        for row in records:
            writer.writerow([
                row[col] for col in old_columns
            ])


def main():
    if not COMPANIES.is_file():
        raise FileNotFoundError(COMPANIES)

    counties, county_id, ksh = v31.v3.read_ksh()

    old = load_previous_od(counties)

    # Meglévő V3.1 kiosztási mechanizmus,
    # új ingázási tervvel.
    v31.COMPANIES = COMPANIES
    v31.OLD_OD = OLD_OD

    v31.OUT_AGENTS = (
        OUT / "agents_with_workplaces_v32.csv"
    )

    v31.OUT_REPORT = (
        OUT / "workplace_assignment_v32_report.txt"
    )

    v31.OUT_COUNTIES = (
        OUT / "workplace_counties_v32.csv"
    )

    v31.OUT_OD = (
        OUT / "workplace_od_v32.csv"
    )

    v31.OUT_COMPARE = (
        OUT / "workplace_od_v32_vs_ksh.csv"
    )

    v31.SEED = 20261122

    v31.balance_od = lambda k, r, c: optimize_od(
        k, r, c, old
    )

    v31.run()

    # A V3.1 újrahasznosított riportjának átnevezése.
    report = v31.OUT_REPORT.read_text(
        encoding="utf-8"
    )

    report = report.replace(
        "V3.1 - BALANCED OD",
        "V3.2 - PROTECTED COMMUTING"
    )

    report = report.replace(
        "Nonlocal OD TV distance V3.1:",
        "Nonlocal OD TV distance V3.2:"
    )

    report = report.replace(
        "Nonlocal OD TV distance old V3:",
        "Nonlocal OD TV distance V3.1:"
    )

    v31.OUT_REPORT.write_text(
        report, encoding="utf-8"
    )

    rename_csv_columns(
        v31.OUT_COMPARE,
        {
            "old_V3_count": "V31_count",
            "V31_count": "V32_count",
            "V31_minus_KSH": "V32_minus_KSH",
        }
    )

    rename_csv_columns(
        v31.OUT_COUNTIES,
        {
            "V31_local_pct": "V32_local_pct",
            "V31_incoming": "V32_incoming",
            "V31_outgoing": "V32_outgoing",
        }
    )

    # Külön ellenőrzés:
    # mely vármegyékbe kerültek a kiosztatlanok?
    if OLD_COUNTIES.exists():
        with OLD_COUNTIES.open(
            newline="", encoding="utf-8-sig"
        ) as f:
            previous = {
                row["county"]: int(row["unassigned"])
                for row in csv.DictReader(f)
            }

        with v31.OUT_COUNTIES.open(
            newline="", encoding="utf-8-sig"
        ) as f:
            current = {
                row["county"]: int(row["unassigned"])
                for row in csv.DictReader(f)
            }

        missing_output = (
            OUT / "workplace_missing_v32_vs_v31.csv"
        )

        with missing_output.open(
            "w", newline="", encoding="utf-8-sig"
        ) as f:
            writer = csv.writer(f)

            writer.writerow([
                "county",
                "V31_unassigned",
                "V32_unassigned",
                "difference"
            ])

            for county in counties:
                writer.writerow([
                    county,
                    previous[county],
                    current[county],
                    current[county] - previous[county]
                ])

        print("Kiosztatlanok összehasonlítása:", missing_output)

    print("\nV3.2 sikeresen elkészült.")
    print("Report:", v31.OUT_REPORT)
    print("County comparison:", v31.OUT_COUNTIES)
    print("OD comparison:", v31.OUT_COMPARE)


if __name__ == "__main__":
    main()