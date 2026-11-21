#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recalibrate synthetic-company worker slots to workplace-county KSH totals.

Inputs (spring agent_generation project):
  data/raw/generated_companies_calibrated.csv
  data/raw/settlement_weights.csv  (original source from Pansim_workplace_generation-main.zip)
  data/processed/commuting_v2/04_commuting_matrix_v2_all_domestic.csv

Outputs:
  data/raw/generated_companies_county_calibrated_v2.csv
  data/validation/workplace_recalibration/*.csv, *.txt

Preserves company count, row order, settlement, TEAOR, size bin and all non-size
columns. Uses mathematical optimization to exactly match the KSH *workplace*
county proportions (scaled to the existing total number of company slots).
It minimizes unavoidable changes to national TEAOR-2-digit slot totals while
respecting the original company-size categories. Requirements: numpy, scipy.

This is a workplace-capacity calibration, not a new assignment of workers.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

SIZE_BINS = {
    '1-4': (1, 4), '5-9': (5, 9), '10-19': (10, 19),
    '20-49': (20, 49), '50-249': (50, 249), '250-1000': (250, 1000),
}


def simple_norm(text: str) -> str:
    raw = str(text).strip().casefold()
    raw = ''.join(ch for ch in unicodedata.normalize('NFD', raw)
                  if unicodedata.category(ch) != 'Mn')
    return re.sub('[^a-z0-9]+', '', raw)


def settlement_key(text: str) -> str:
    # The hierarchy and source contain unusual partially accented spellings.
    # Keep Kömlő distinct from Komló, and Kömörő distinct from Komoró.
    t = str(text).strip().casefold()
    if t in {'kömlő', 'kömlo'}:
        return '__komloe__'
    if t in {'kömörő', 'kömöro'}:
        return '__komoroe__'
    return simple_norm(t)


def county_key(text: str) -> str:
    t = str(text).strip().casefold()
    if t in {'fováros', 'főváros', 'budapest', 'budapest főváros'}:
        return 'budapest'
    return simple_norm(t.removesuffix(' vármegye').removesuffix(' megye'))


def read_ksh(path: Path):
    destinations = Counter()
    residence = Counter()
    with path.open(newline='', encoding='utf-8-sig') as fp:
        reader = csv.DictReader(fp)
        required = {'residence_county', 'workplace_county', 'count'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'KSH file missing columns: {required - set(reader.fieldnames or [])}')
        for row in reader:
            n = int(row['count'])
            if n < 0:
                raise ValueError('KSH flow has a negative count')
            destinations[row['workplace_county'].strip()] += n
            residence[row['residence_county'].strip()] += n
    if len(destinations) != 20 or sum(destinations.values()) != sum(residence.values()):
        raise ValueError(f'Expected 20 workplace counties; got {len(destinations)}')
    by_key = {county_key(v): v for v in destinations}
    if len(by_key) != 20:
        raise ValueError('Ambiguous canonical KSH county names')
    return destinations, by_key


def read_settlement_counties(path: Path, ksh_by_key: dict):
    mapping = {}
    with path.open(newline='', encoding='utf-8-sig') as fp:
        reader = csv.DictReader(fp)
        if not {'settlement_original', 'county'}.issubset(reader.fieldnames or []):
            raise ValueError('settlement_weights.csv needs settlement_original and county')
        for r in reader:
            key = settlement_key(r['settlement_original'])
            ckey = county_key(r['county'])
            if ckey not in ksh_by_key:
                raise ValueError(f'Unknown county in settlement weights: {r["county"]!r}')
            canonical = ksh_by_key[ckey]
            if key in mapping and mapping[key] != canonical:
                raise ValueError(f'Ambiguous place key {key}: {mapping[key]} vs {canonical}')
            mapping[key] = canonical
    # The weights source omits these two settlements, while the company CSV has them.
    explicit = {'__komloe__': 'Heves vármegye',
                '__komoroe__': 'Szabolcs-Szatmár-Bereg vármegye'}
    for key, name in explicit.items():
        if name not in ksh_by_key.values():
            raise ValueError(f'Missing canonical county for {key}')
        mapping[key] = name
    return mapping


def largest_remainder_targets(reference: dict, total: int) -> dict:
    basis = sum(reference.values())
    raw = {k: total * val / basis for k, val in reference.items()}
    result = {k: int(math.floor(v)) for k, v in raw.items()}
    remain = total - sum(result.values())
    for c in sorted(reference, key=lambda k: (-(raw[k] - result[k]), k))[:remain]:
        result[c] += 1
    assert sum(result.values()) == total
    return result


def add_sparse_row(ri, ci, vi, row, col, value):
    ri.append(row); ci.append(col); vi.append(value)


def sector_county_plan(cell_stats: dict, county_targets: dict):
    """Two LPs: minimum necessary sector imbalance, then near-proportional fit."""
    combined = defaultdict(lambda: [0, 0, 0])  # before, min, max
    for (county, teaor, size_bin), (n, old, low, high) in cell_stats.items():
        current = combined[county, teaor]
        current[0] += old
        current[1] += low
        current[2] += high

    counties = sorted(county_targets)
    teaors = sorted({t for _, t in combined}, key=lambda t: (int(t) if t.isdigit() else 999, t))
    groups = sorted(combined)
    n = len(groups)
    t = len(teaors)
    county_idx = {name: i for i, name in enumerate(counties)}
    teaor_idx = {code: i for i, code in enumerate(teaors)}

    original_by_sector = Counter()
    original_by_county = Counter()
    for (county, teaor), values in combined.items():
        original_by_sector[teaor] += values[0]
        original_by_county[county] += values[0]

    for county in counties:
        low = sum(v[1] for (c, _), v in combined.items() if c == county)
        high = sum(v[2] for (c, _), v in combined.items() if c == county)
        if not low <= county_targets[county] <= high:
            raise ValueError(f'Impossible company-bin bounds for {county}: '
                             f'min={low}, target={county_targets[county]}, max={high}')

    ri, ci, vi = [], [], []
    for j, (county, teaor) in enumerate(groups):
        add_sparse_row(ri, ci, vi, county_idx[county], j, 1)
        add_sparse_row(ri, ci, vi, len(counties) + teaor_idx[teaor], j, 1)
    for j in range(t):
        # x + sector_deficit - sector_surplus = original sector count.
        add_sparse_row(ri, ci, vi, len(counties)+j, n+j, 1)
        add_sparse_row(ri, ci, vi, len(counties)+j, n+t+j, -1)
    A = coo_matrix((vi, (ri, ci)), shape=(len(counties)+t, n+2*t)).tocsr()
    b = [county_targets[c] for c in counties] + [original_by_sector[s] for s in teaors]
    xbounds = [(combined[g][1], combined[g][2]) for g in groups]
    bounds = xbounds + [(0, None)] * (2*t)
    obj = [0.0]*n + [1.0]*(2*t)
    print(f'Optimizing {n:,} county×TEAOR groups; {len(cell_stats):,} company-bin cells ...', flush=True)
    first = linprog(obj, A_eq=A, b_eq=b, bounds=bounds, method='highs')
    if not first.success:
        raise RuntimeError('Unable to match county targets: ' + first.message)
    min_sector_change = int(round(float(sum(first.x[n:]))))

    # The proportional soft target is a county×sector version of IPF, giving
    # priority to preserving each county's original industry profile.
    prior = np.array([combined[g][0] for g in groups], dtype=float)
    county_ids = np.array([county_idx[g[0]] for g in groups], dtype=int)
    sector_ids = np.array([teaor_idx[g[1]] for g in groups], dtype=int)
    cc = np.array([county_targets[c] for c in counties], dtype=float)
    ss = np.array([original_by_sector[s] for s in teaors], dtype=float)
    for _ in range(400):
        current_c = np.bincount(county_ids, weights=prior, minlength=len(counties))
        prior *= (cc / current_c)[county_ids]
        current_s = np.bincount(sector_ids, weights=prior, minlength=t)
        prior *= (ss / current_s)[sector_ids]
    prior_round = np.rint(prior).astype(int)

    # Fix national sector mismatch to its mathematical minimum, then minimize
    # per-cell deviation from proportional IPF priors.
    ri, ci, vi = [], [], []
    for j, (county, teaor) in enumerate(groups):
        add_sparse_row(ri, ci, vi, county_idx[county], j, 1)
        add_sparse_row(ri, ci, vi, len(counties)+teaor_idx[teaor], j, 1)
        row = len(counties)+t+j
        add_sparse_row(ri, ci, vi, row, j, 1)
        add_sparse_row(ri, ci, vi, row, n+j, -1)
        add_sparse_row(ri, ci, vi, row, 2*n+j, 1)
    for j in range(t):
        add_sparse_row(ri, ci, vi, len(counties)+j, 3*n+j, 1)
        add_sparse_row(ri, ci, vi, len(counties)+j, 3*n+t+j, -1)
    A2 = coo_matrix((vi, (ri, ci)),
                    shape=(len(counties)+t+n, 3*n+2*t)).tocsr()
    b2 = b + list(map(int, prior_round))
    U = coo_matrix(([1.0]*(2*t),
                    ([0]*(2*t), list(range(3*n, 3*n+2*t)))),
                   shape=(1, 3*n+2*t)).tocsr()
    w = (1 / np.sqrt(prior + 50.0)).tolist()
    obj2 = [0.0]*n + w + w + [0.0]*(2*t)
    bounds2 = xbounds + [(0, None)]*(2*n+2*t)
    refined = linprog(obj2, A_eq=A2, b_eq=b2, A_ub=U,
                      b_ub=[min_sector_change], bounds=bounds2, method='highs')
    if not refined.success:
        raise RuntimeError('Refinement LP failed: ' + refined.message)
    numeric = refined.x[:n]
    if np.max(np.abs(numeric-np.rint(numeric))) > 1e-5:
        raise RuntimeError('Non-integer LP solution: do not round it silently')
    result = {g: int(round(v)) for g, v in zip(groups, numeric)}
    after_c = Counter(); after_t = Counter()
    for (county, teaor), val in result.items():
        after_c[county] += val
        after_t[teaor] += val
    if any(after_c[c] != county_targets[c] for c in counties):
        raise AssertionError('County totals were not met exactly')
    measured_l1 = sum(abs(after_t[s]-original_by_sector[s]) for s in teaors)
    if measured_l1 != min_sector_change:
        raise AssertionError('Industry loss exceeds theoretical minimum')
    print(f'Exact county targets: YES; minimum TEAOR L1 change: '
          f'{measured_l1:,} (equivalent to {measured_l1//2:,} transferred slots)')
    return result, original_by_sector, measured_l1


def capped_weighted_int(amount: int, available, weights):
    """Integer water filling with exact sum; caps and deterministic rounding."""
    avail = np.asarray(available, dtype=np.int64)
    if amount < 0 or amount > int(avail.sum()):
        raise ValueError('Target violates slot size bounds')
    if amount == 0:
        return np.zeros(len(avail), dtype=np.int64)
    if amount == int(avail.sum()):
        return avail.copy()
    w = np.asarray(weights, dtype=float)
    w = np.maximum(w, 1.0)
    w[avail == 0] = 0
    # Find a multiplier such that sum(min(available, multiplier*weight)) == amount.
    lower, upper = 0.0, float(np.max(avail[w>0] / w[w>0]))
    for _ in range(55):
        middle = (lower + upper) / 2.0
        if float(np.minimum(avail, middle*w).sum()) <= amount:
            lower = middle
        else:
            upper = middle
    flo = np.minimum(avail.astype(float), lower*w)
    taken = np.floor(flo + 1e-9).astype(np.int64)
    left = amount - int(taken.sum())
    if left < 0:
        raise AssertionError('Numerical overflow in water filling')
    if left:
        possible = np.flatnonzero(taken < avail)
        if left > len(possible):
            raise AssertionError('More remainder slots than active companies')
        # Higher fractional remainder first; mergesort keeps stable source order.
        ranked = possible[np.argsort(-(flo[possible]-taken[possible]), kind='stable')]
        taken[ranked[:left]] += 1
    assert int(taken.sum()) == amount
    return taken


def distribute_over_bins(cell_stats: dict, group_plan: dict):
    by_group = defaultdict(list)
    for key in cell_stats:
        by_group[key[:2]].append(key)
    bin_plan = {}
    for g, cellkeys in by_group.items():
        cellkeys.sort(key=lambda key: list(SIZE_BINS).index(key[2]))
        old = np.array([cell_stats[key][1] for key in cellkeys], dtype=np.int64)
        mn = np.array([cell_stats[key][2] for key in cellkeys], dtype=np.int64)
        mx = np.array([cell_stats[key][3] for key in cellkeys], dtype=np.int64)
        target = group_plan[g]
        delta = target-int(old.sum())
        if delta >= 0:
            distributed = capped_weighted_int(delta, mx-old, old)
            final = old+distributed
        else:
            distributed = capped_weighted_int(-delta, old-mn, old)
            final = old-distributed
        if final.sum() != target or np.any(final < mn) or np.any(final > mx):
            raise AssertionError(f'Invalid bin distribution at {g}')
        bin_plan.update({key: int(value) for key, value in zip(cellkeys, final)})
    return bin_plan


def csv_write(path: Path, rows: list, columns: list[str]):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def calibrate(companies_file: Path, weights_file: Path, ksh_file: Path,
              output_file: Path, reports: Path):
    if not companies_file.is_file() or not weights_file.is_file() or not ksh_file.is_file():
        raise FileNotFoundError('One or more input files are missing: ' + '\n'.join(str(x) for x in (companies_file, weights_file, ksh_file)))
    if companies_file.resolve() == output_file.resolve():
        raise ValueError('Refusing to overwrite the original company CSV')

    ksh, canonical = read_ksh(ksh_file)
    settle_to_county = read_settlement_counties(weights_file, canonical)
    stats = defaultdict(lambda: [0, 0, 0, 0])
    sectors_before = Counter()
    before_county = Counter()
    company_counts = Counter()
    print('Reading company capacities and mapping settlements ...', flush=True)
    nrows = 0
    with companies_file.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        required = {'settlement', 'teaor', 'bin', 'company_size'}
        if not required.issubset(fields):
            raise ValueError(f'Missing company columns: {required-set(fields)}')
        for row in reader:
            nrows += 1
            k = settlement_key(row['settlement'])
            if k not in settle_to_county:
                raise ValueError(f'Unmapped settlement at company row {nrows}: {row["settlement"]!r}')
            county = settle_to_county[k]
            teaor = row['teaor'].strip()
            sizebin = row['bin'].strip()
            if sizebin not in SIZE_BINS:
                raise ValueError(f'Unknown size bin at row {nrows}: {sizebin!r}')
            size = int(row['company_size'])
            lo, hi = SIZE_BINS[sizebin]
            if not lo <= size <= hi:
                raise ValueError(f'Company row {nrows} size {size} violates {sizebin}')
            cell = stats[county, teaor, sizebin]
            cell[0] += 1; cell[1] += size; cell[2] += lo; cell[3] += hi
            before_county[county] += size
            sectors_before[teaor] += size
            company_counts[county] += 1
    if set(before_county) != set(ksh):
        raise ValueError('Not exactly the same 20 counties in companies and KSH: '
                         + str(set(before_county) ^ set(ksh)))
    old_total = sum(before_county.values())
    targets = largest_remainder_targets(ksh, old_total)
    print(f'Companies: {nrows:,}; worker slots: {old_total:,}; '
          f'county targets: {len(targets)}; two-digit TEAORs: {len(sectors_before)}')

    group_plan, old_sector, l1 = sector_county_plan(stats, targets)
    cell_plan = distribute_over_bins(stats, group_plan)

    # Re-read the company CSV to keep original physical row positions and all
    # metadata; modifications consist of company_size only.
    print('Reassigning sizes within existing company-bin limits ...', flush=True)
    bins_rows = defaultdict(list)
    sizes_old = np.empty(nrows, dtype=np.int16)
    i = 0
    with companies_file.open(newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            county = settle_to_county[settlement_key(row['settlement'])]
            key = (county, row['teaor'].strip(), row['bin'].strip())
            bins_rows[key].append(i)
            sizes_old[i] = int(row['company_size'])
            i += 1
    if i != nrows:
        raise AssertionError('Source company file changed while calibrating')
    sizes_new = sizes_old.copy()
    for key, ids in bins_rows.items():
        a = np.array(ids, dtype=np.int64)
        old = sizes_old[a].astype(np.int64)
        new_target = cell_plan[key]
        diff = new_target - int(old.sum())
        lo, hi = SIZE_BINS[key[2]]
        if diff > 0:
            sizes_new[a] = (old + capped_weighted_int(diff, hi-old, old)).astype(np.int16)
        elif diff < 0:
            sizes_new[a] = (old - capped_weighted_int(-diff, old-lo, old)).astype(np.int16)
        if int(sizes_new[a].sum(dtype=np.int64)) != new_target:
            raise AssertionError(f'Incorrect employee slots after bin adjustment: {key}')
    del bins_rows

    after_county = Counter()
    after_sector = Counter()
    changed = 0

    output_file.parent.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    print(f'Writing recalibrated companies: {output_file}', flush=True)
    with companies_file.open(newline='', encoding='utf-8-sig') as inp, \
            output_file.open('w', newline='', encoding='utf-8-sig') as out:
        reader = csv.DictReader(inp)
        writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
        writer.writeheader()
        for j, row in enumerate(reader):
            newsize = int(sizes_new[j]); oldsize = int(sizes_old[j])
            county = settle_to_county[settlement_key(row['settlement'])]
            row['company_size'] = str(newsize)
            writer.writerow(row)
            after_county[county] += newsize
            after_sector[row['teaor'].strip()] += newsize
            changed += int(newsize != oldsize)
    assert all(after_county[c] == targets[c] for c in ksh)
    assert all(after_sector[t] >= 0 for t in old_sector)
    assert sum(after_county.values()) == old_total
    assert sum(abs(after_sector[t]-old_sector[t]) for t in old_sector) == l1

    county_rows = []
    for c in sorted(ksh):
        lb = sum(v[2] for key, v in stats.items() if key[0] == c)
        ub = sum(v[3] for key, v in stats.items() if key[0] == c)
        county_rows.append(dict(county=c, companies=company_counts[c],
                                ksh_workplace_workers=ksh[c],
                                original_slots=before_county[c],
                                target_slots=targets[c],
                                final_slots=after_county[c],
                                changed_slots=after_county[c]-before_county[c],
                                minimum_possible=lb, maximum_possible=ub,
                                target_error=after_county[c]-targets[c]))
    csv_write(reports/'01_county_targets.csv', county_rows, list(county_rows[0]))
    teaor_rows = []
    for t in sorted(old_sector, key=lambda x: int(x) if x.isdigit() else 9999):
        teaor_rows.append(dict(teaor=t, original_slots=old_sector[t],
                               final_slots=after_sector[t],
                               difference=after_sector[t]-old_sector[t]))
    csv_write(reports/'02_teaor_comparison.csv', teaor_rows, list(teaor_rows[0]))
    bin_rows = []
    for key, v in sorted(stats.items()):
        c, t, b = key
        bin_rows.append(dict(county=c, teaor=t, company_size_bin=b,
                             company_count=v[0], old_slots=v[1], new_slots=cell_plan[key],
                             changed_slots=cell_plan[key]-v[1], min_slots=v[2], max_slots=v[3]))
    csv_write(reports/'03_county_teaor_bin_comparison.csv', bin_rows, list(bin_rows[0]))
    changed_teaors = sum(row['difference'] != 0 for row in teaor_rows)
    summary = [
        'WORKPLACE COMPANY-SIZE COUNTY RECALIBRATION',
        f'Input file: {companies_file}',
        f'Output file: {output_file}',
        f'Companies: {nrows:,}',
        f'Worker slots before: {old_total:,}',
        f'Worker slots after: {sum(after_county.values()):,}',
        f'Companies with changed size: {changed:,}',
        f'Counties with exact KSH-scaled target: {sum(after_county[c] == targets[c] for c in ksh)}/20',
        f'National TEAOR sector total L1 deviation (minimum achievable): {l1:,}',
        f'Equivalent net sector slot transfers (L1/2): {l1//2:,}',
        f'TEAOR subsectors with changed national slot count: {changed_teaors}',
        'Company rows, order, settlement, TEAOR, size-bin, and other fields: unchanged',
        'Individual company sizes: all within original size bins',
        '',
        'County targets use KSH *workplace* county counts normalized to the',
        'original total physical company slots, including HOME category in KSH.',
        'This is a modelling decision consistent with the current spring V3',
        'workflow; it does not separately model workers working from home.',
    ]
    (reports/'04_recalibration_report.txt').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    print('\n'.join(summary))
    print(f'Reports: {reports}')


def main():
    root = Path(__file__).resolve().parent
    default_companies = root/'data/raw/generated_companies_calibrated.csv'
    if not default_companies.exists():
        default_companies = root/'generated_companies_calibrated.csv'
    default_weights = default_companies.parent/'settlement_weights.csv'
    if not default_weights.exists():
        default_weights = root/'settlement_weights.csv'
    default_ksh = root/'data/processed/commuting_v2/04_commuting_matrix_v2_all_domestic.csv'
    if not default_ksh.exists():
        default_ksh = root/'04_commuting_matrix_v2_all_domestic.csv'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--companies', type=Path, default=default_companies)
    parser.add_argument('--weights', type=Path, default=default_weights)
    parser.add_argument('--commuting', type=Path, default=default_ksh)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--reports', type=Path)
    args = parser.parse_args()
    output = args.output or args.companies.with_name('generated_companies_county_calibrated_v2.csv')
    reports = args.reports or (root/'data/validation/workplace_recalibration')
    calibrate(args.companies, args.weights, args.commuting, output, reports)


if __name__ == '__main__':
    main()
