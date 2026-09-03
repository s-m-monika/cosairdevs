import pandas as pd
import os

DATA_FOLDER = "data/seed"

files = {
    "alerts.csv (-> ACCOUNTS)": "alerts.csv",
    "behaviour_baseline.csv (-> ALERTS)": "behaviour_baseline.csv",
    "beneficiaries.csv (-> BEHAVIOUR BASELINE)": "beneficiaries.csv",
    "cases.csv (-> BENEFICIARIES)": "cases.csv",
    "customers.csv (-> CASES)": "customers.csv",
    "demo_runs.csv (-> CUSTOMERS)": "demo_runs.csv",
    "kyc_profiles.csv (-> SCENARIOS)": "kyc_profiles.csv",
    "merchants.csv (-> KYC PROFILES)": "merchants.csv",
    "README.txt (-> MERCHANTS)": "README.txt",
    "simulator_feed.csv (-> DOCUMENTATION)": "simulator_feed.csv",
    "transactions.csv (-> TRANSACTIONS)": "transactions.csv",
}

for label, filename in files.items():
    path = os.path.join(DATA_FOLDER, filename)

    print("\n" + "=" * 60)
    print(f"{label}")
    print("=" * 60)

    if not os.path.exists(path):
        print("  FILE NOT FOUND")
        continue

    if filename == "simulator_feed.csv":
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
