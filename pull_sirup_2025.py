# -*- coding: utf-8 -*-
"""
Pull all data from SIRUP Inaproc DataTables API (2025 budget year).
Paginates through all records (max 100,000 per request) and appends to JSONL.
Resume-safe: checkpoint tracks offset, JSONL is append-only.

Usage: uv run --with httpx pull_sirup_2025.py
"""

import json
import time
import os
import sys

import httpx

BASE_URL = "https://sirup.inaproc.id/sirup/caripaketctr/search"
OUTPUT_FILE = "sirup_2025_all.jsonl"
CHECKPOINT_FILE = "sirup_2025_checkpoint.json"

PAGE_SIZE = 100_000
RETRY_DELAY = 15
REQUEST_DELAY = 0.5

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

COOKIES = {
    "PLAY_SESSION": "596baed944a2fbb195afe4ace1a0fbbbc3cfc38f-___TS=1784118415462&tahunAnggaranPilihan=2025&menu=cariPaket2&___ID=6ab5d171-a57e-46ef-8333-6fa4e48507b5",
    "_ga_KLDH3FQ7DR": "GS2.1.s1782194818$o3$g1$t1782194819$j59$l0$h0",
    "_ga": "GA1.1.933612520.1782181854",
    "_ga_3BPJ11C32J": "GS2.1.s1782194820$o2$g0$t1784194820$j60$l0$h0",
    "_ga_D78WKTMJC6": "GS2.1.s1784194820$o3$g1$t1784116617$j60$l0$h0",
}

TAHUN_ANGGARAN = "2025"


def build_params(start, draw):
    params = {
        "tahunAnggaran": TAHUN_ANGGARAN,
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


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return None


def save_checkpoint(start, saved_count, total):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"start": start, "saved_count": saved_count, "total": total}, f, indent=2)


def append_records(records):
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def fetch_page(client, start, draw):
    params = build_params(start, draw)
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


def main():
    checkpoint = load_checkpoint()
    total_records = 0
    saved_count = 0

    if checkpoint:
        saved_count = count_jsonl_lines(OUTPUT_FILE)
        start_offset = checkpoint["start"]
        total_records = checkpoint["total"]
        draw = start_offset // PAGE_SIZE + 1
        print(f"[RESUME] {saved_count:,} records saved, starting at offset {start_offset:,}")
    else:
        start_offset = 0
        draw = 1
        if os.path.exists(OUTPUT_FILE):
            print(f"[WARN] {OUTPUT_FILE} exists but no checkpoint. Starting fresh.")
            os.remove(OUTPUT_FILE)

    client = httpx.Client(
        headers=HEADERS,
        cookies=COOKIES,
        timeout=120.0,
        follow_redirects=True,
    )

    try:
        print(f"[INFO] Fetching initial page to get total count (tahunAnggaran={TAHUN_ANGGARAN})...")
        result = fetch_page(client, start_offset, draw)

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
            return

        append_records(page_data)
        saved_count += len(page_data)
        start_offset += PAGE_SIZE
        draw += 1
        save_checkpoint(start_offset, saved_count, total_records)

        pct = min(100.0, saved_count / total_records * 100)
        print(f"  Page {draw-1}: +{len(page_data):,} | Total: {saved_count:,}/{total_records:,} ({pct:.1f}%)")

        while start_offset < total_records:
            time.sleep(REQUEST_DELAY)
            result = fetch_page(client, start_offset, draw)
            page_data = result.get("data", [])

            if not page_data:
                print(f"  [WARN] No data at offset {start_offset:,}, stopping.")
                break

            append_records(page_data)
            saved_count += len(page_data)
            start_offset += PAGE_SIZE
            draw += 1
            save_checkpoint(start_offset, saved_count, total_records)

            pct = min(100.0, saved_count / total_records * 100)
            print(f"  Page {draw-1}: +{len(page_data):,} | Total: {saved_count:,}/{total_records:,} ({pct:.1f}%)")
            sys.stdout.flush()

    except KeyboardInterrupt:
        print(f"\n[STOP] Interrupted at offset {start_offset:,}. Progress saved.")
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()

    save_checkpoint(start_offset, saved_count, total_records)
    file_size = os.path.getsize(OUTPUT_FILE) / (1024 * 1024) if os.path.exists(OUTPUT_FILE) else 0
    print(f"\n[DONE] {saved_count:,}/{total_records:,} records ({saved_count/total_records*100:.1f}%)")
    print(f"[FILE] {OUTPUT_FILE} ({file_size:.1f} MB)")
    if saved_count >= total_records:
        print("[OK] All records fetched!")
        os.remove(CHECKPOINT_FILE)


if __name__ == "__main__":
    main()
