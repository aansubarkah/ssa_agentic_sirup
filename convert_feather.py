# -*- coding: utf-8 -*-
"""Convert sirup_2026_all.jsonl to feather format using chunked reading."""
import pandas as pd
import os
import json
import time

print("Reading JSONL in chunks...")
chunks = []
start = time.time()

chunk_size = 100_000
count = 0
with open("sirup_2026_all.jsonl", "r", encoding="utf-8") as f:
    chunk = []
    for line in f:
        chunk.append(json.loads(line))
        count += 1
        if len(chunk) >= chunk_size:
            chunks.append(pd.DataFrame(chunk))
            chunk = []
            print(f"  {count:,} records read ({count/3269263*100:.1f}%)")
    if chunk:
        chunks.append(pd.DataFrame(chunk))

print(f"Read {count:,} records in {time.time()-start:.1f}s")

print("Concatenating...")
df = pd.concat(chunks, ignore_index=True)
del chunks
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"Dtypes:\n{df.dtypes}")

print("Writing feather...")
df.to_feather("sirup_2026_all.feather")
print(f"Done! Size: {os.path.getsize('sirup_2026_all.feather') / (1024**2):.1f} MB")
print(f"Total time: {time.time()-start:.1f}s")
