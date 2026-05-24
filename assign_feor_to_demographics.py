from __future__ import annotations

from pathlib import Path
import pandas as pd


# ============================================================
# ITT MÓDOSÍTSD, ha máshol vannak a fájlok
# ============================================================
INPUT_DEMOGRAPHICS = Path("data/processed/teaor_demographics_long.csv")
INPUT_TEAOR_TO_FEOR = Path("data/processed/teaor_to_feor_distribution.csv")
OUTPUT_FILE = Path("data/processed/demographics_with_feor.csv")


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    demographics = pd.read_csv(INPUT_DEMOGRAPHICS, sep="|", encoding="utf-8-sig")
    teaor_to_feor = pd.read_csv(INPUT_TEAOR_TO_FEOR, encoding="utf-8-sig", dtype={"feor_code": str})

    return demographics, teaor_to_feor


def assign_feor_counts(
    demographics: pd.DataFrame,
    teaor_to_feor: pd.DataFrame,
) -> pd.DataFrame:
    """
    A TEÁOR-os demográfiai táblát FEOR-ok szerint tovább bontja.

    Bemenet:
      demographics:
        county, gender, age_group, education, teaor_name, county, count, teaor_code
      teaor_to_feor:
        teaor, feor_code, prob

    Kimenet:
      county, teaor_code, gender, age_group, education, feor_code, count
    """

    # gyors lookup: teaor -> adott TEÁOR FEOR eloszlása
    feor_dist = {
        teaor: grp[["feor_code", "prob"]].reset_index(drop=True)
        for teaor, grp in teaor_to_feor.groupby("teaor")
    }

    output_rows = []

    for row in demographics.itertuples(index=False):
        teaor_code = row.teaor_code
        total_count = int(row.count)

        if total_count <= 0:
            continue

        if teaor_code not in feor_dist:
            # ha nincs ilyen TEÁOR-ra FEOR eloszlás, kihagyjuk
            continue

        dist = feor_dist[teaor_code].copy()

        # lebegőből egész darabszámok
        dist["expected"] = dist["prob"] * total_count
        dist["base"] = dist["expected"].astype(int)
        remainder = total_count - int(dist["base"].sum())

        # maradék szétosztása legnagyobb törtrészek szerint
        dist["frac"] = dist["expected"] - dist["base"]
        if remainder > 0:
            top_idx = dist.sort_values("frac", ascending=False).head(remainder).index
            dist.loc[top_idx, "base"] += 1

        dist = dist[dist["base"] > 0].copy()

        for feor_row in dist.itertuples(index=False):
            output_rows.append({
                "county": row.county,
                "teaor_code": teaor_code,
                "teaor_name": row.teaor_name,
                "gender": row.gender,
                "age_group": row.age_group,
                "education": row.education,
                "feor_code": feor_row.feor_code,
                "count": int(feor_row.base),
            })

    out_df = pd.DataFrame(output_rows)

    if out_df.empty:
        return out_df

    # összevonás biztonságból
    out_df = (
        out_df.groupby(
            ["county", "teaor_code", "teaor_name", "gender", "age_group", "education", "feor_code"],
            as_index=False
        )["count"]
        .sum()
    )

    return out_df


def main() -> None:
    print(f"Reading demographics: {INPUT_DEMOGRAPHICS}")
    print(f"Reading teaor->feor distribution: {INPUT_TEAOR_TO_FEOR}")

    demographics, teaor_to_feor = load_inputs()

    print("Assigning FEOR counts...")
    out_df = assign_feor_counts(demographics, teaor_to_feor)

    if out_df.empty:
        print("ERROR: output is empty.")
        return

    print(f"Saving: {OUTPUT_FILE}")
    out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print("\nDone.")
    print(f"Rows: {len(out_df):,}")
    print(f"Total count: {out_df['count'].sum():,}")
    print(f"Unique FEOR codes: {out_df['feor_code'].nunique()}")
    print(f"Unique TEÁOR codes: {out_df['teaor_code'].nunique()}")

    print("\nSample:")
    print(out_df.head(20).to_string(index=False))

    print("\nTop 20 FEOR by count:")
    top_feor = out_df.groupby("feor_code", as_index=False)["count"].sum().sort_values("count", ascending=False).head(20)
    print(top_feor.to_string(index=False))


if __name__ == "__main__":
    main()