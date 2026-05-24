from __future__ import annotations

from pathlib import Path
import pandas as pd


# ============================================================
# INPUT / OUTPUT
# ============================================================
INPUT_COUNTY_SUMMARY = Path("data/validation/county_workplace_vs_residence_summary.csv")
OUTPUT_FILE = Path("data/validation/net_commuting_summary.csv")


def main() -> None:
    print(f"Reading: {INPUT_COUNTY_SUMMARY}")

    df = pd.read_csv(INPUT_COUNTY_SUMMARY, encoding="utf-8-sig")

    required_cols = {
        "county",
        "residence_workers",
        "workplace_workers",
        "diff_workplace_minus_residence",
    }

    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Hiányzó oszlop(ok): {missing}")

    # Biztonság kedvéért újraszámoljuk
    df["net_flow"] = df["workplace_workers"] - df["residence_workers"]

    df["net_flow_ratio_to_residence"] = df.apply(
        lambda r: r["net_flow"] / r["residence_workers"]
        if r["residence_workers"] > 0 else None,
        axis=1,
    )

    df["abs_net_flow"] = df["net_flow"].abs()

    total_residence = int(df["residence_workers"].sum())
    total_workplace = int(df["workplace_workers"].sum())
    total_net = int(df["net_flow"].sum())

    print("\n==============================")
    print("TOTAL CHECK")
    print("==============================")
    print(f"Residence total: {total_residence:,}")
    print(f"Workplace total: {total_workplace:,}")
    print(f"Net total:       {total_net:,}")
    print(f"Relative total difference: {total_net / total_residence:.4%}")

    print("\n==============================")
    print("TOP POSITIVE NET FLOWS")
    print("==============================")
    print(
        df.sort_values("net_flow", ascending=False)
        .head(10)[
            [
                "county",
                "residence_workers",
                "workplace_workers",
                "net_flow",
                "net_flow_ratio_to_residence",
            ]
        ]
        .to_string(index=False)
    )

    print("\n==============================")
    print("TOP NEGATIVE NET FLOWS")
    print("==============================")
    print(
        df.sort_values("net_flow", ascending=True)
        .head(10)[
            [
                "county",
                "residence_workers",
                "workplace_workers",
                "net_flow",
                "net_flow_ratio_to_residence",
            ]
        ]
        .to_string(index=False)
    )

    print("\n==============================")
    print("LARGEST ABSOLUTE DIFFERENCES")
    print("==============================")
    print(
        df.sort_values("abs_net_flow", ascending=False)
        .head(20)[
            [
                "county",
                "residence_workers",
                "workplace_workers",
                "net_flow",
                "net_flow_ratio_to_residence",
            ]
        ]
        .to_string(index=False)
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # rendezett mentés
    out_df = df.sort_values("net_flow", ascending=False).reset_index(drop=True)

    out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print("\n==============================")
    print("SAVED")
    print("==============================")
    print(f"Saved to: {OUTPUT_FILE}")

    print("\nDone.")


if __name__ == "__main__":
    main()