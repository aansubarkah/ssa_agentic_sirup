# -*- coding: utf-8 -*-
"""
Single-entry pipeline for SIRUP Inaproc procurement data.

1. Pulls ALL records for a given budget year (tahun anggaran) via the site's
   internal DataTables API, paginating 100,000 records at a time into a JSONL
   file (resume-safe via checkpoint).
2. Converts the resulting JSONL into Apache Feather (fast columnar) and a
   pipe-delimited CSV ('|' separator).

Resume-safe: re-running the same year continues from the last checkpoint.

Usage:
    # Pull 2026 data, then convert to feather + csv
    uv run --with httpx --with pandas --with pyarrow sirup.py --tahun 2026

    # Pull 2025 data
    uv run --with httpx --with pandas --with pyarrow sirup.py --tahun 2025

    # Pull only, skip conversion
    uv run sirup.py --tahun 2026 --no-convert

    # Convert an existing JSONL only (skip the pull)
    uv run sirup.py --tahun 2025 --convert-only
"""

import argparse
import json
import os
import sys
import time

import httpx

BASE_URL = "https://sirup.inaproc.id/sirup/caripaketctr/search"

PAGE_SIZE = 100_000
RETRY_DELAY = 15
REQUEST_DELAY = 0.5

# PLAY_SESSION cookie template — tahunAnggaranPilihan is injected from --tahun.
# If pulls fail with session errors, refresh by visiting sirup.inaproc.id in a
# browser, copying the new PLAY_SESSION value, and replacing PLAY_SESSION below.
PLAY_SESSION = (
    "596baed944a2fbb195afe4ace1a0fbbbc3cfc38f"
    "-___TS=1784118415462&tahunAnggaranPilihan={tahun}"
    "&menu=cariPaket2&___ID=6ab5d171-a57e-46ef-8333-6fa4e48507b5"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.5",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://sirup.inaproc.id/sirup/caripaketctr/index",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

GA_COOKIES = {
    "_ga_KLDH3FQ7DR": "GS2.1.s1782194818$o3$g1$t1782194819$j59$l0$h0",
    "_ga": "GA1.1.933612520.1782181854",
    "_ga_3BPJ11C32J": "GS2.1.s1782194820$o2$g0$t1784194820$j60$l0$h0",
    "_ga_D78WKTMJC6": "GS2.1.s1784194820$o3$g1$t1784116617$j60$l0$h0",
}


def build_cookies(tahun):
    cookies = dict(GA_COOKIES)
    cookies["PLAY_SESSION"] = PLAY_SESSION.format(tahun=tahun)
    return cookies


def build_params(tahun, start, draw):
    params = {
        "tahunAnggaran": str(tahun),
        "jenisPengadaan": "",
        "metodePengadaan": "",
        "minPagu": "",
        "maxPagu": "",
        "bulan": "",
        "lokasi": "",
        "kldi": "",
        "pdn": "",
        "ukm": "",
        "draw": str(draw),
        "start": str(start),
        "length": str(PAGE_SIZE),
        "order[0][column]": "5",
        "order[0][dir]": "DESC",
        "search[value]": "",
        "search[regex]": "false",
        "_": str(int(time.time() * 1000)),
    }
    col_data = ["", "paket", "pagu", "jenisPengadaan", "isPDN", "isUMK",
                "metode", "pemilihan", "kldi", "satuanKerja", "lokasi", "id"]
    for i, cd in enumerate(col_data):
        searchable = "true" if cd else "false"
        orderable = "true" if cd else "false"
        params[f"columns[{i}][data]"] = cd
        params[f"columns[{i}][name]"] = ""
        params[f"columns[{i}][searchable]"] = searchable
        params[f"columns[{i}][orderable]"] = orderable
        params[f"columns[{i}][search][value]"] = ""
        params[f"columns[{i}][search][regex]"] = "false"
    return params


def count_jsonl_lines(filepath):
    if not os.path.exists(filepath):
        return 0
    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


def load_checkpoint(checkpoint_file):
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
            return json.load(f)
    return None


def save_checkpoint(checkpoint_file, start, saved_count, total):
    with open(checkpoint_file, "w") as f:
        json.dump({"start": start, "saved_count": saved_count, "total": total}, f, indent=2)


def append_records(output_file, records):
    with open(output_file, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def fetch_page(client, tahun, start, draw):
    params = build_params(tahun, start, draw)
    for attempt in range(5):
        try:
            resp = client.get(BASE_URL, params=params)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f"  [!] Attempt {attempt+1}/5 failed at offset {start}: {e}")
            if attempt < 4:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise


def pull(tahun, output_file, checkpoint_file):
    """Pull all records for the given budget year into output_file (JSONL)."""
    checkpoint = load_checkpoint(checkpoint_file)
    total_records = 0
    saved_count = 0

    if checkpoint:
        saved_count = count_jsonl_lines(output_file)
        start_offset = checkpoint["start"]
        total_records = checkpoint["total"]
        draw = start_offset // PAGE_SIZE + 1
        print(f"[RESUME] {saved_count:,} records saved, starting at offset {start_offset:,}")
    else:
        start_offset = 0
        draw = 1
        if os.path.exists(output_file):
            print(f"[WARN] {output_file} exists but no checkpoint. Starting fresh.")
            os.remove(output_file)

    client = httpx.Client(
        headers=HEADERS,
        cookies=build_cookies(tahun),
        timeout=120.0,
        follow_redirects=True,
    )

    try:
        print(f"[INFO] Fetching initial page to get total count (tahunAnggaran={tahun})...")
        result = fetch_page(client, tahun, start_offset, draw)

        if not checkpoint:
            total_records = result.get("recordsTotal", 0)
            records_filtered = result.get("recordsFiltered", 0)
            print(f"   Total records:      {total_records:,}")
            print(f"   Filtered records:   {records_filtered:,}")
            print(f"   Pages:              {(total_records + PAGE_SIZE - 1) // PAGE_SIZE:,}")
            print(f"   Page size:          {PAGE_SIZE:,}")
            print()

        page_data = result.get("data", [])
        if not page_data and start_offset == 0:
            print("[ERROR] No data returned on first request! Check cookies/auth.")
            print(f"   Response keys: {list(result.keys())}")
            return False

        append_records(output_file, page_data)
        saved_count += len(page_data)
        start_offset += PAGE_SIZE
        draw += 1
        save_checkpoint(checkpoint_file, start_offset, saved_count, total_records)

        pct = min(100.0, saved_count / total_records * 100) if total_records else 0
        print(f"  Page {draw-1}: +{len(page_data):,} | Total: {saved_count:,}/{total_records:,} ({pct:.1f}%)")

        while start_offset < total_records:
            time.sleep(REQUEST_DELAY)
            result = fetch_page(client, tahun, start_offset, draw)
            page_data = result.get("data", [])

            if not page_data:
                print(f"  [WARN] No data at offset {start_offset:,}, stopping.")
                break

            append_records(output_file, page_data)
            saved_count += len(page_data)
            start_offset += PAGE_SIZE
            draw += 1
            save_checkpoint(checkpoint_file, start_offset, saved_count, total_records)

            pct = min(100.0, saved_count / total_records * 100)
            print(f"  Page {draw-1}: +{len(page_data):,} | Total: {saved_count:,}/{total_records:,} ({pct:.1f}%)")
            sys.stdout.flush()

    except KeyboardInterrupt:
        print(f"\n[STOP] Interrupted at offset {start_offset:,}. Progress saved.")
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.close()

    save_checkpoint(checkpoint_file, start_offset, saved_count, total_records)
    file_size = os.path.getsize(output_file) / (1024 * 1024) if os.path.exists(output_file) else 0
    print(f"\n[DONE] {saved_count:,}/{total_records:,} records "
          f"({saved_count/total_records*100:.1f}%)" if total_records else "\n[DONE]")
    print(f"[FILE] {output_file} ({file_size:.1f} MB)")
    if total_records and saved_count >= total_records:
        print("[OK] All records fetched!")
        os.remove(checkpoint_file)
    return True


def convert(output_file, feather_file, csv_file):
    """Convert JSONL → Feather + pipe-delimited CSV using chunked reading."""
    import pandas as pd

    if not os.path.exists(output_file):
        print(f"[ERROR] {output_file} not found. Run the pull first (drop --convert-only).")
        return False

    print(f"[INFO] Reading {output_file} in chunks...")
    chunks = []
    start = time.time()
    chunk_size = 100_000
    count = 0
    with open(output_file, "r", encoding="utf-8") as f:
        chunk = []
        for line in f:
            chunk.append(json.loads(line))
            count += 1
            if len(chunk) >= chunk_size:
                chunks.append(pd.DataFrame(chunk))
                chunk = []
                print(f"  {count:,} records read")
        if chunk:
            chunks.append(pd.DataFrame(chunk))

    print(f"[INFO] Read {count:,} records in {time.time()-start:.1f}s")
    print("[INFO] Concatenating...")
    df = pd.concat(chunks, ignore_index=True)
    del chunks
    print(f"   Shape: {df.shape}")

    print(f"[INFO] Writing {feather_file}...")
    df.to_feather(feather_file)
    feather_mb = os.path.getsize(feather_file) / (1024 ** 2)
    print(f"   Done! Size: {feather_mb:.1f} MB")

    print(f"[INFO] Writing {csv_file} (pipe-delimited)...")
    df.to_csv(csv_file, sep="|", index=False)
    csv_mb = os.path.getsize(csv_file) / (1024 ** 2)
    print(f"   Done! Size: {csv_mb:.1f} MB")

    print(f"[INFO] Total conversion time: {time.time()-start:.1f}s")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Pull SIRUP Inaproc data for a budget year and convert to Feather + CSV.",
    )
    parser.add_argument(
        "--tahun", "-t", required=True, type=int,
        help="Budget year (tahun anggaran), e.g. 2025, 2026",
    )
    parser.add_argument(
        "--no-convert", action="store_true",
        help="Only pull JSONL, skip Feather/CSV conversion",
    )
    parser.add_argument(
        "--convert-only", action="store_true",
        help="Only convert an existing JSONL (skip the pull)",
    )
    args = parser.parse_args()

    tahun = args.tahun
    output_file = f"sirup_{tahun}_all.jsonl"
    checkpoint_file = f"sirup_{tahun}_checkpoint.json"
    feather_file = f"sirup_{tahun}_all.feather"
    csv_file = f"sirup_{tahun}_all.csv"

    if args.convert_only and args.no_convert:
        print("[ERROR] --convert-only and --no-convert are mutually exclusive.")
        sys.exit(2)

    if not args.convert_only:
        ok = pull(tahun, output_file, checkpoint_file)
        if not ok:
            sys.exit(1)

    if not args.no_convert:
        convert(output_file, feather_file, csv_file)


if __name__ == "__main__":
    main()
