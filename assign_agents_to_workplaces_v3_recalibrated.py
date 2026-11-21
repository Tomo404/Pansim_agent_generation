from pathlib import Path

import assign_agents_to_workplaces_v3 as v3

ROOT = Path(__file__).resolve().parent

# Rekalibrált vállalati kapacitások
NEW_COMPANIES = (
    ROOT / "data/raw/generated_companies_county_calibrated_v2.csv"
)

if not NEW_COMPANIES.exists():
    raise FileNotFoundError(
        f"Hiányzik a rekalibrált vállalati fájl: {NEW_COMPANIES}"
    )

# A V3 a V2-ből veszi át a vállalatok beolvasását.
# Ezt átirányítjuk a rekalibrált cégtáblára.
v3.base.COMPANIES_FILE = NEW_COMPANIES

# Új kimenetek: nem írjuk felül a korábbi V3 eredményeit.
v3.OUTPUT = (
    ROOT / "data/processed/agents_with_workplaces_v3_recalibrated.csv"
)

v3.REPORT = (
    ROOT / "data/processed/workplace_assignment_v3_recalibrated_report.txt"
)

v3.COUNTIES_OUT = (
    ROOT / "data/processed/workplace_counties_v3_recalibrated.csv"
)

v3.OD_OUT = (
    ROOT / "data/processed/workplace_od_v3_recalibrated.csv"
)

print("Rekalibrált cégtábla:", NEW_COMPANIES)

# Munkahelyek újrakiosztása
v3.run()