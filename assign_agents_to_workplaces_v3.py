"""Spring workplace V3: reserve home-county capacity before nationwide commuting.

Requires the already corrected assign_agents_to_workplaces_v2.py in the same folder.
Does not change agents, FEOR, TEAOR, or any original output file.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
import csv
import random

import numpy as np

# Reuse the V2 company's disambiguation and county normalization.
# IMPORTANT: the local V2 must contain the Komlo/Komoro name fixes.
import assign_agents_to_workplaces_v2 as base

ROOT = Path(__file__).resolve().parent
AGENTS = ROOT / "data/processed/agents.csv"
COMMUTING = ROOT / "data/processed/commuting_v2/04_commuting_matrix_v2_all_domestic.csv"
OUTPUT = ROOT / "data/processed/agents_with_workplaces_v3.csv"
REPORT = ROOT / "data/processed/workplace_assignment_v3_report.txt"
COUNTIES_OUT = ROOT / "data/processed/workplace_counties_v3.csv"
OD_OUT = ROOT / "data/processed/workplace_od_v3.csv"
SEED = 20261120

NEW_FIELDS = [
    "target_work_county", "final_work_county", "used_fallback",
    "fallback_level", "used_teaor_fallback", "workplace_id",
    "workplace_county", "workplace_teaor_code", "workplace_settlement",
    "workplace_settlement_type", "workplace_size",
]
METHOD = {
    0: "5_missing_capacity",
    1: "1_local_same_teaor",
    2: "2_local_any_teaor",
    3: "3_commuter_same_teaor",
    4: "4_commuter_any_teaor",
}


def read_ksh():
    flow = Counter()
    with COMMUTING.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            h = base.normalize_county(r["residence_county"])
            w = base.normalize_county(r["workplace_county"])
            flow[h, w] += int(r["count"])
    counties = sorted({h for h, _ in flow} | {w for _, w in flow})
    if len(counties) != 20:
        raise ValueError(f"20 helyett {len(counties)} megye van a matrixban")
    county_id = {c: i for i, c in enumerate(counties)}
    ksh = np.zeros((20, 20), dtype=np.float64)
    for (h, w), cnt in flow.items():
        ksh[county_id[h], county_id[w]] = cnt
    if int(ksh.sum()) != 4_596_079:
        raise ValueError("A KSH belfoldi letszam nem 4,596,079")
    return counties, county_id, ksh


def load_workplaces(county_id):
    # The same company mapping as the previously successful V2.
    companies = base.load_companies_with_county()
    pools = defaultdict(list)
    workplace_info = []
    county_capacity = np.zeros(len(county_id), dtype=np.int64)

    for wp_idx, row in enumerate(companies.itertuples(index=False)):
        county = base.normalize_county(row.county)
        if county not in county_id:
            raise ValueError(f"Ismeretlen cegmegye: {county!r}")
        ci = county_id[county]
        size = int(row.company_size)
        sector = str(row.teaor_code).strip().upper()
        workplace_info.append((
            str(row.workplace_id), county, sector,
            str(row.settlement_pretty), str(row.settlement_type), size
        ))
        pools[ci, sector].extend([wp_idx] * size)
        county_capacity[ci] += size

    # Shuffle within every county × TEAOR. No worker-order dependence.
    rnd = random.Random(SEED)
    for key in pools:
        rnd.shuffle(pools[key])
    print(f"Workplaces: {len(workplace_info):,}; slots: {int(county_capacity.sum()):,}")
    return workplace_info, pools, county_capacity


def count_agents(county_id):
    counts = np.zeros(len(county_id), dtype=np.int64)
    count = 0
    with AGENTS.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        needed = {"agent_id", "county", "teaor_code", "feor_code"}
        if not needed.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Hianyzo agensoszlop: {needed - set(reader.fieldnames or [])}")
        for row in reader:
            county = base.normalize_county(row["county"])
            if county not in county_id:
                raise ValueError(f"Ismeretlen agens-megye: {county!r}")
            counts[county_id[county]] += 1
            count += 1
    print(f"Agents: {count:,}")
    return counts, count


def exact_transport(row_demand, col_capacity, ksh, missing):
    """Fit off-diagonal commuting to remaining county capacities.

    The last, artificial destination means 'no capacity'.  No real
    residence-to-work county pair is allowed on the diagonal here.
    """
    n = len(row_demand)
    column_targets = np.append(col_capacity, missing).astype(np.int64)
    if int(row_demand.sum()) != int(column_targets.sum()):
        raise ValueError("Nem egyeznek a fennmarado kereslet/kinalat osszegek")

    weights = np.zeros((n, n + 1), dtype=np.float64)
    for i in range(n):
        for j in range(n):
            if i != j and column_targets[j] > 0:
                # Pseudocounts keep the transportation graph connected.
                weights[i, j] = max(ksh[i, j], 0.1)
        if missing:
            weights[i, n] = max(1., ksh[i].sum() * missing / max(ksh.sum(), 1))

    # Iterative proportional fitting on the 20 x (20+missing) table.
    x = weights.copy()
    for step in range(5000):
        rs = x.sum(axis=1)
        if np.any((row_demand > 0) & (rs <= 0)):
            raise ValueError("Lehetetlen szallitasi feladat: ures megyei sor")
        np.divide(row_demand, rs, out=rs, where=rs > 0)
        x *= rs[:, None]

        cs = x.sum(axis=0)
        if np.any((column_targets > 0) & (cs <= 0)):
            raise ValueError("Lehetetlen szallitasi feladat: ures megyei oszlop")
        np.divide(column_targets, cs, out=cs, where=cs > 0)
        x *= cs[None, :]
        if step % 20 == 0:
            error = np.max(np.abs(x.sum(axis=1) - row_demand))
            if error < 1e-6:
                break
    else:
        raise RuntimeError("Az orszagos OD-illesztes nem konvergalt")

    whole = np.floor(x + 1e-9).astype(np.int64)
    row_left = (row_demand - whole.sum(axis=1)).astype(int)
    col_left = (column_targets - whole.sum(axis=0)).astype(int)
    if np.any(row_left < 0) or np.any(col_left < 0):
        raise AssertionError("Hibas matrixkerekites")

    # Exact integral rounding by a small max-flow on fractional edges.
    N = n + (n + 1) + 2
    src, sink = N - 2, N - 1
    graph = [[] for _ in range(N)]

    def edge(u, v, cap):
        graph[u].append([v, cap, len(graph[v])])
        graph[v].append([u, 0, len(graph[u]) - 1])
        return len(graph[u]) - 1

    fractional_edges = {}
    for i in range(n):
        edge(src, i, int(row_left[i]))
        eligible = [
            j for j in range(n + 1)
            if (j != i or j == n)
            and col_left[j] > 0
            and x[i, j] - whole[i, j] > 1e-9
        ]
        eligible.sort(key=lambda j: -(x[i, j] - whole[i, j]))
        for j in eligible:
            k = edge(i, n + j, 1)
            fractional_edges[i, j] = k
    for j in range(n + 1):
        edge(n + j, sink, int(col_left[j]))

    needed = int(row_left.sum())
    sent = 0
    while sent < needed:
        prev = [None] * N
        prev[src] = (-1, -1)
        q = deque([src])
        while q and prev[sink] is None:
            u = q.popleft()
            for k, e in enumerate(graph[u]):
                if e[1] > 0 and prev[e[0]] is None:
                    prev[e[0]] = (u, k)
                    q.append(e[0])
        if prev[sink] is None:
            raise RuntimeError("A megyei OD-matrix egeszre kerekitese nem sikerult")
        aug = needed - sent
        v = sink
        while v != src:
            u, k = prev[v]
            aug = min(aug, graph[u][k][1])
            v = u
        v = sink
        while v != src:
            u, k = prev[v]
            e = graph[u][k]
            e[1] -= aug
            graph[v][e[2]][1] += aug
            v = u
        sent += aug

    for (i, j), k in fractional_edges.items():
        # Each original row-to-column edge had capacity 1.
        if graph[i][k][1] == 0:
            whole[i, j] += 1

    if not np.array_equal(whole.sum(axis=1), row_demand):
        raise AssertionError("OD: hibas sorosszegek")
    if not np.array_equal(whole.sum(axis=0), column_targets):
        raise AssertionError("OD: hibas oszloposszegek")
    if np.any(np.diag(whole[:, :n]) != 0):
        raise AssertionError("OD: atlo a commuting reszben")
    return whole


def make_assignment_pools(pools):
    # Reuse only available slots, once each.
    positions = {key: 0 for key in pools}
    by_county = defaultdict(list)
    for c, sector in pools:
        by_county[c].append((c, sector))

    def take(ci, teaor):
        key = (ci, teaor)
        data = pools.get(key, ())
        pos = positions.get(key, 0)
        if pos < len(data):
            positions[key] = pos + 1
            return data[pos], False
        best_key = None
        best_left = 0
        for k in by_county.get(ci, ()):
            left = len(pools[k]) - positions[k]
            if left > best_left:
                best_left = left
                best_key = k
        if best_key is None:
            raise AssertionError(f"Nincs eleg kapacitas a(z) {ci}. megyeben")
        idx = positions[best_key]
        positions[best_key] += 1
        return pools[best_key][idx], True

    return take


def run():
    for path in (AGENTS, COMMUTING):
        if not path.is_file():
            raise FileNotFoundError(path)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    counties, county_id, ksh = read_ksh()
    home_counts, count = count_agents(county_id)
    workplaces, pools, capacity = load_workplaces(county_id)
    ksh_home_totals = ksh.sum(axis=1)
    if np.any(ksh_home_totals <= 0):
        raise ValueError("Ures KSH lakomegye")

    # Local workers get first claim on their home-county slots.
    desired_local = np.rint(home_counts * np.diag(ksh) / ksh_home_totals).astype(np.int64)
    local_quota = np.minimum(desired_local, capacity)
    remaining_workers = home_counts - local_quota
    remaining_capacity = capacity - local_quota
    missing = max(int(count - capacity.sum()), 0)
    if int(remaining_capacity.sum()) > int(remaining_workers.sum()):
        raise ValueError("Tul sok ferőhely: ehhez a V3-hoz külön ures-slot modell kell")
    od_plan = exact_transport(remaining_workers, remaining_capacity, ksh, missing)

    print("Local reserved:", f"{int(local_quota.sum()):,}")
    print("Planned missing:", f"{missing:,}")

    # Compact arrays allow exact original row order in the final CSV.
    assigned_wp = np.full(count, -1, dtype=np.int32)
    planned_county = np.full(count, -1, dtype=np.int8)
    method = np.zeros(count, dtype=np.uint8)
    take = make_assignment_pools(pools)
    rng = random.Random(SEED + 1)

    # PASS 1: distribute local quota across ALL 20 counties first.
    left_people = home_counts.copy()
    left_local = local_quota.copy()
    with AGENTS.open(newline="", encoding="utf-8-sig") as f:
        for row_id, row in enumerate(csv.DictReader(f)):
            ci = county_id[base.normalize_county(row["county"])]
            if rng.randrange(int(left_people[ci])) < int(left_local[ci]):
                teaor = row["teaor_code"].strip().upper()
                wp, changed = take(ci, teaor)
                assigned_wp[row_id] = wp
                planned_county[row_id] = ci
                method[row_id] = 2 if changed else 1
                left_local[ci] -= 1
            left_people[ci] -= 1
    if np.any(left_local != 0):
        raise AssertionError("Nem teljesult a helyi lefoglalas")

    # PASS 2: all non-local workers, using the nationally balanced OD plan.
    remaining_od = od_plan.copy()
    for i in range(len(counties)):
        remaining_od[i, i] = 0
    with AGENTS.open(newline="", encoding="utf-8-sig") as f:
        for row_id, row in enumerate(csv.DictReader(f)):
            if assigned_wp[row_id] >= 0:
                continue
            ci = county_id[base.normalize_county(row["county"])]
            row_plan = remaining_od[ci]
            total = int(row_plan.sum())
            if total <= 0:
                raise AssertionError("Elfogyott a tervezett ingazasi OD-sor")
            ticket = rng.randrange(total)
            cumulative = 0
            destination = None
            for j, quota in enumerate(row_plan):
                cumulative += int(quota)
                if ticket < cumulative:
                    destination = j
                    break
            assert destination is not None
            remaining_od[ci, destination] -= 1
            if destination == len(counties):
                method[row_id] = 0
                continue
            teaor = row["teaor_code"].strip().upper()
            wp, changed = take(destination, teaor)
            assigned_wp[row_id] = wp
            planned_county[row_id] = destination
            method[row_id] = 4 if changed else 3
    if np.any(remaining_od != 0):
        raise AssertionError("Maradt fel nem hasznalt OD-kvota")

    # PASS 3: write original agents and original columns unchanged.
    method_counts = Counter()
    actual_od = Counter()
    actual_local = Counter()
    missing_by_county = Counter()
    actual_work_county = Counter()
    used_slots = Counter()
    with AGENTS.open(newline="", encoding="utf-8-sig") as fin, OUTPUT.open(
        "w", newline="", encoding="utf-8-sig"
    ) as fout:
        reader = csv.DictReader(fin)
        original_fields = reader.fieldnames or []
        writer = csv.DictWriter(fout, fieldnames=original_fields + NEW_FIELDS)
        writer.writeheader()
        for row_id, row in enumerate(reader):
            code = int(method[row_id])
            method_counts[METHOD[code]] += 1
            wi = int(assigned_wp[row_id])
            home = base.normalize_county(row["county"])
            if wi < 0:
                missing_by_county[home] += 1
                row.update({name: "" for name in NEW_FIELDS})
                row.update({
                    "used_fallback": True,
                    "fallback_level": METHOD[code],
                    "used_teaor_fallback": False,
                })
            else:
                wp_id, work, sector, city, city_type, size = workplaces[wi]
                used_slots[wi] += 1
                actual_od[home, work] += 1
                actual_work_county[work] += 1
                if home == work:
                    actual_local[home] += 1
                row.update({
                    "target_work_county": counties[int(planned_county[row_id])],
                    "final_work_county": work,
                    "used_fallback": code in (2, 4),
                    "fallback_level": METHOD[code],
                    "used_teaor_fallback": sector != row["teaor_code"].strip().upper(),
                    "workplace_id": wp_id,
                    "workplace_county": work,
                    "workplace_teaor_code": sector,
                    "workplace_settlement": city,
                    "workplace_settlement_type": city_type,
                    "workplace_size": size,
                })
            writer.writerow(row)
            if (row_id + 1) % 500_000 == 0:
                print(f"Written: {row_id + 1:,}")

    if any(used_slots[i] > wp[5] for i, wp in enumerate(workplaces)):
        raise AssertionError("Munkahelykapacitas tulfutott!")
    assigned = int((assigned_wp >= 0).sum())
    if assigned + missing != count:
        raise AssertionError("Eltérő osszesitett dolgozoi letszam")
    if assigned != min(count, int(capacity.sum())):
        raise AssertionError("Nem sikerult a maximalis kapacitaskihasznalas")

    with COUNTIES_OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "county", "agents", "capacity", "ksh_same_county_pct",
            "v3_same_county", "v3_same_county_pct", "difference_pp",
            "ksh_local_target", "local_reserved", "local_capacity_shortage",
            "missing_workplaces", "actual_workplace_workers", "net_commuting_balance",
        ])
        for ci, county in enumerate(counties):
            n = int(home_counts[ci])
            p = 100 * ksh[ci, ci] / ksh_home_totals[ci]
            local = actual_local[county]
            writer.writerow([
                county, n, int(capacity[ci]), round(p, 3),
                local, round(100 * local / n, 3),
                round(100 * local / n - p, 3),
                int(desired_local[ci]), int(local_quota[ci]),
                int(desired_local[ci] - local_quota[ci]),
                missing_by_county[county], actual_work_county[county],
                actual_work_county[county] - (n - missing_by_county[county]),
            ])
    with OD_OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["residence_county", "workplace_county", "count"])
        for (home, work), amount in sorted(actual_od.items()):
            writer.writerow([home, work, amount])

    local_total = sum(actual_local.values())
    lines = [
        "SPRING WORKPLACE ASSIGNMENT V3",
        f"Agents: {count:,}",
        f"Assigned: {assigned:,}",
        f"Missing (capacity shortage): {missing:,}",
        f"Workplace capacity: {int(capacity.sum()):,}",
        f"Home-county employees: {local_total:,} ({100 * local_total / count:.3f}%)",
        f"KSH nationwide home-county share: {100 * np.trace(ksh) / ksh.sum():.3f}%",
        f"Capacity-limited local quota target: {int(local_quota.sum()):,}",
        f"Local quota shortfall due to capacity: {int((desired_local - local_quota).sum()):,}",
        f"Overfilled workplaces: 0",
        "Methods:",
    ]
    lines.extend(f"  {k}: {v:,}" for k, v in sorted(method_counts.items()))
    lines.extend([
        "", "NOTE: No exact home settlement exists in spring agents.csv.",
        "NOTE: FEOR and original agent TEAOR are copied unchanged.",
        "NOTE: Commuter destinations balanced to remaining county capacity.",
        "NOTE: County capacities may prevent census-level own-county shares.",
    ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print("Saved:", OUTPUT, REPORT, COUNTIES_OUT, OD_OUT)


if __name__ == "__main__":
    run()
