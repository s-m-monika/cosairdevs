import pandas as pd
import os

DATA_FOLDER = "data/seed/FRAB_DEMO_READY_DATASET"

files = [
    "accounts.csv",
    "alerts.csv",
    "behaviour_baseline.csv",
    "beneficiaries.csv",
    "cases.csv",
    "customers.csv",
    "demo_runs.csv",
    "kyc_profiles.csv",
    "merchants.csv",
    "README.txt",
    "simulator_feed.csv",
    "transactions.csv",
]

for filename in files:
    path = os.path.join(DATA_FOLDER, filename)

    print("\n" + "=" * 60)
    print(filename)
    print("=" * 60)

    if not os.path.exists(path):
        print("  FILE NOT FOUND")
        continue

    if filename in ("README.txt", "simulator_feed.csv"):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        total_rows = len(lines)
        print("Lines:", total_rows)
        print("\nFirst 5 lines:")
        for line in lines[:5]:
            print(" ", line.rstrip())
        continue

    df = pd.read_csv(path)
    total_rows = len(df)

    print("Rows:", total_rows)
    print("Columns:")
    for column in df.columns:
        print(" -", column)
    print("\nFirst 2 rows:")
    print(df.head(2).to_string(index=False))
