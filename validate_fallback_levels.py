from pathlib import Path
import pandas as pd

INPUT_FILE = Path("data/processed/agents_with_workplaces.csv")
OUTPUT_FILE = Path("data/validation/fallback_level_summary.csv")


def main():
    print(f"Reading: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig", dtype=str)

    total = len(df)

    print("\n==============================")
    print("TOTAL")
    print("==============================")
    print(f"Agents: {total:,}")

    print("\n==============================")
    print("FALLBACK LEVELS")
    print("==============================")
    summary = (
        df["fallback_level"]
        .value_counts(dropna=False)
        .reset_index()
    )
    summary.columns = ["fallback_level", "count"]
    summary["ratio"] = summary["count"] / total

    print(summary.to_string(index=False))

    print("\n==============================")
    print("TEÁOR FALLBACK")
    print("==============================")
    teaor_summary = (
        df["used_teaor_fallback"]
        .value_counts(dropna=False)
        .reset_index()
    )
    teaor_summary.columns = ["used_teaor_fallback", "count"]
    teaor_summary["ratio"] = teaor_summary["count"] / total

    print(teaor_summary.to_string(index=False))

    print("\n==============================")
    print("AGENT TEÁOR VS WORKPLACE TEÁOR")
    print("==============================")
    df["teaor_match"] = df["teaor_code"] == df["workplace_teaor_code"]

    match_summary = (
        df["teaor_match"]
        .value_counts(dropna=False)
        .reset_index()
    )
    match_summary.columns = ["teaor_match", "count"]
    match_summary["ratio"] = match_summary["count"] / total

    print(match_summary.to_string(index=False))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print("\nSaved:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()