from pathlib import Path
import pandas as pd

INPUT_FILE = Path("data/raw/hier_foglalkoztatott_ingazas.xlsx")
OUTPUT_FILE = Path("data/processed/commuting_matrix.csv")


def main():
    print(f"Reading: {INPUT_FILE}")

    df = pd.read_excel(INPUT_FILE, header=None)

    # =========================================================
    # WORKPLACE COUNTY FEJLÉC
    # =========================================================

    workplace_counties = {}

    current_county = None

    for col in range(5, df.shape[1]):
        county = df.iloc[0, col]

        if pd.notna(county):
            current_county = str(county).strip()

        workplace_counties[col] = current_county

    # =========================================================
    # FLOW GYŰJTÉS
    # =========================================================

    flows = []

    current_gender = None
    current_age = None
    current_education = None
    current_residence_county = None

    for row in range(2, df.shape[0]):

        gender = df.iloc[row, 0]
        age = df.iloc[row, 1]
        education = df.iloc[row, 2]
        residence = df.iloc[row, 3]

        if pd.notna(gender):
            current_gender = str(gender).strip()

        if pd.notna(age):
            current_age = str(age).strip()

        if pd.notna(education):
            current_education = str(education).strip()

        if pd.notna(residence):
            current_residence_county = str(residence).strip()

        employment_type = df.iloc[row, 4]

        if pd.isna(employment_type):
            continue

        employment_type = str(employment_type).strip()

        # csak magyarországi workplace-ek
        if employment_type == "Külföldön foglalkoztatott":
            continue

        # =====================================================
        # OSZLOPOK
        # =====================================================

        for col in range(5, df.shape[1]):

            value = df.iloc[row, col]

            if pd.isna(value):
                continue

            try:
                count = int(value)
            except:
                continue

            if count <= 0:
                continue

            workplace_county = workplace_counties[col]

            flows.append({
                "residence_county": current_residence_county,
                "workplace_county": workplace_county,
                "count": count,
            })

    out = pd.DataFrame(flows)

    out = (
        out
        .groupby(
            ["residence_county", "workplace_county"],
            as_index=False
        )["count"]
        .sum()
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"Saving: {OUTPUT_FILE}")
    out.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print("\nDone.")
    print(out.head(30))

    print("\nTotal flow count:")
    print(out["count"].sum())


if __name__ == "__main__":
    main()