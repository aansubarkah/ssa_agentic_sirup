# -*- coding: utf-8 -*-
"""
Step 1: Convert sirup_2025_all.jsonl to feather
Step 2: Filter idKldi == 'K9' (Kementerian Kesehatan)
Step 3: Save filtered as CSV (pipe delimiter) and feather

Usage: uv run --with pandas --with pyarrow process_2025.py
"""

import pandas as pd
import os
import json
import time

JSONL_FILE = "sirup_2025_all.jsonl"
FEATHER_FILE = "sirup_2025_all.feather"
FILTER_CSV_FILE = "sirup_2025_K9.csv"
FILTER_FEATHER_FILE = "sirup_2025_K9.feather"
FILTER_KLDI = "K9"
CHUNK_SIZE = 100_000


def main():
    start = time.time()

    # --- Step 1: Read JSONL and save Feather ---
    print("=" * 60)
    print("STEP 1: JSONL -> Feather")
    print("=" * 60)

    print(f"Reading {JSONL_FILE} in chunks...")
    chunks = []
    count = 0
    with open(JSONL_FILE, "r", encoding="utf-8") as f:
        chunk = []
        for line in f:
            chunk.append(json.loads(line))
            count += 1
            if len(chunk) >= CHUNK_SIZE:
                chunks.append(pd.DataFrame(chunk))
                chunk = []
                print(f"  {count:,} records read")
        if chunk:
            chunks.append(pd.DataFrame(chunk))

    print(f"Read {count:,} records in {time.time()-start:.1f}s")

    print("Concatenating...")
    df = pd.concat(chunks, ignore_index=True)
    del chunks
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")

    print(f"Writing {FEATHER_FILE}...")
    df.to_feather(FEATHER_FILE)
    feather_size = os.path.getsize(FEATHER_FILE) / (1024**2)
    print(f"Done! Size: {feather_size:.1f} MB")

    # --- Step 2: Filter idKldi == K9 ---
    print()
    print("=" * 60)
    print(f"STEP 2: Filter idKldi == '{FILTER_KLDI}' (Kementerian Kesehatan)")
    print("=" * 60)

    df_k9 = df[df["idKldi"] == FILTER_KLDI].copy()
    print(f"Filtered: {len(df_k9):,} records (from {len(df):,} total)")

    if len(df_k9) == 0:
        print(f"[WARN] No records with idKldi='{FILTER_KLDI}' found!")
        # Show unique idKldi values starting with 'K'
        k_values = df[df["idKldi"].str.startswith("K", na=False)]["idKldi"].unique()
        print(f"Available K* idKldi values: {sorted(k_values)[:20]}")
        return

    # --- Step 3a: Save CSV with pipe delimiter ---
    print()
    print("=" * 60)
    print(f"STEP 3a: Save CSV (pipe delimiter)")
    print("=" * 60)

    df_k9.to_csv(FILTER_CSV_FILE, sep="|", index=False)
    csv_size = os.path.getsize(FILTER_CSV_FILE) / (1024**2)
    print(f"Written: {FILTER_CSV_FILE} ({csv_size:.1f} MB)")

    # --- Step 3b: Save Feather ---
    print()
    print("=" * 60)
    print(f"STEP 3b: Save Feather")
    print("=" * 60)

    df_k9.to_feather(FILTER_FEATHER_FILE)
    k9_feather_size = os.path.getsize(FILTER_FEATHER_FILE) / (1024**2)
    print(f"Written: {FILTER_FEATHER_FILE} ({k9_feather_size:.1f} MB)")

    # --- Summary ---
    total_pagu = df_k9["pagu"].sum()
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total records (all):     {len(df):,}")
    print(f"Total records (K9):      {len(df_k9):,}")
    print(f"Total pagu (K9):         Rp {total_pagu:,.0f}")
    print(f"Top satker kerja (K9):   {df_k9['satuanKerja'].value_counts().head(5).to_dict()}")
    print(f"Files created:")
    print(f"  {FEATHER_FILE}         ({feather_size:.1f} MB)")
    print(f"  {FILTER_CSV_FILE}       ({csv_size:.1f} MB)")
    print(f"  {FILTER_FEATHER_FILE}   ({k9_feather_size:.1f} MB)")
    print(f"Total time: {time.time()-start:.1f}s")


if __name__ == "__main__":
    main()
