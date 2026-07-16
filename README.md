# SSA SIRUP

Scraping pipeline for Indonesia's **SIRUP Inaproc** (Sistem Informasi Rencana Umum Pengadaan) — the government's central e-procurement planning database hosted at `sirup.inaproc.id`.

Pulls millions of procurement plan records per budget year via the site's internal DataTables API, converts them to efficient columnar formats, and filters by ministry/agency.

---

## 🧠 Agent AI Guide

> **TL;DR**: This is a data-extraction pipeline. Scripts talk to a public government API, paginate through results, dump JSONL, then convert to Feather/CSV. No auth tokens needed — just cookie headers that may need refreshing.

### Architecture

```
pull_sirup.py          →  sirup_2026_all.jsonl       (raw API dump, 2026 budget year)
pull_sirup_2025.py     →  sirup_2025_all.jsonl       (raw API dump, 2025 budget year)

convert_feather.py     →  sirup_2026_all.feather      (JSONL → Arrow Feather)
process_2025.py        →  sirup_2025_all.feather      (JSONL → Feather)
                       →  sirup_2025_K9.feather/.csv  (filtered: Kementerian Kesehatan)
```

### Key Details

| Aspect | Value |
|---|---|
| **API endpoint** | `GET https://sirup.inaproc.id/sirup/caripaketctr/search` |
| **Pagination** | DataTables protocol — `start` + `length` params, max `length=100_000` per request |
| **Resume safety** | Checkpoint files (`sirup_checkpoint.json`, `sirup_2025_checkpoint.json`) track offset; JSONL is append-only |
| **Record count** | ~3.2M records for 2026, varies for 2025 |
| **Output formats** | JSONL (raw) → Feather (fast columnar) → CSV pipe-delimited (filtered) |
| **Filter example** | `idKldi == "K9"` = Kementerian Kesehatan (Ministry of Health) |
| **Runtime** | uv (Python 3.14, dependencies in `pyproject.toml`) |

### Cookie / Session Notes

- The `PLAY_SESSION` cookie encodes `tahunAnggaranPilihan` and may expire.
- If pulls fail with session errors, refresh the cookie by visiting `sirup.inaproc.id` in a browser and copying the updated `PLAY_SESSION` value.
- `pages_info.md` has the full reference URL and headers.

### Data Schema (per record)

| Field | Description |
|---|---|
| `paket` | Procurement package name |
| `pagu` | Budget ceiling (IDR) |
| `jenisPengadaan` | Procurement type (goods/services/consulting) |
| `isPDN` | Domestic product requirement flag |
| `isUMK` | Small business (UMK) requirement flag |
| `metode` | Procurement method (tender/e-purchasing/etc.) |
| `pemilihan` | Selection method |
| `kldi` | Ministry/agency name |
| `idKldi` | Ministry/agency code (e.g. `K9` = Ministry of Health) |
| `satuanKerja` | Work unit |
| `lokasi` | Location |
| `id` | Internal SIRUP record ID |

### Common Agent Tasks

- **Add a new budget year**: Copy `pull_sirup.py` → `pull_sirup_YYYY.py`, change `tahunAnggaran`, output file, and checkpoint file. Update the `PLAY_SESSION` cookie's `tahunAnggaranPilihan`.
- **Filter by different KLDI**: In `process_2025.py`, change `FILTER_KLDI` (e.g. `K2` = Kementerian PUPR).
- **Change page size**: Adjust `PAGE_SIZE` — values above 100k may be rejected by the server.

---

## 👤 Human Guide

### What does this project do?

It downloads every procurement plan record from SIRUP Inaproc — Indonesia's government procurement planning database (~3 million+ records per year) — and converts them into easy-to-use data files.

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- Python 3.14 (managed by uv)

### Setup

```bash
# Install dependencies
uv sync
```

### Usage

**1. Download data for a budget year**

```bash
# 2026 budget year
uv run pull_sirup.py

# 2025 budget year
uv run pull_sirup_2025.py
```

This may take a while (~3M records). It's resume-safe — if interrupted, re-run the same command and it continues from where it left off.

**2. Convert raw JSONL to Feather format**

```bash
# 2026 data
uv run convert_feather.py

# 2025 data (also filters for Ministry of Health)
uv run process_2025.py
```

**3. Output files**

| File | Description |
|---|---|
| `sirup_YYYY_all.jsonl` | Raw JSON Lines — one JSON object per line, one per procurement package |
| `sirup_YYYY_all.feather` | All records in Apache Feather format (fast to read with pandas/polars) |
| `sirup_2025_K9.feather` | Filtered: Ministry of Health (K9) procurement packages |
| `sirup_2025_K9.csv` | Same as above, pipe-delimited CSV |

### Troubleshooting

- **Session expired**: Open `sirup.inaproc.id` in your browser, log in, copy the new `PLAY_SESSION` cookie value, and update it in the script.
- **Empty results**: The API may be down or the budget year data hasn't been published yet. Check `sirup.inaproc.id` directly.

### Project Structure

```
├── .gitignore
├── .python-version          # Python version pin for uv
├── pyproject.toml           # Dependencies (httpx, pandas, pyarrow)
├── main.py                  # Stub entry point
├── pull_sirup.py            # Pull 2026 data → JSONL
├── pull_sirup_2025.py       # Pull 2025 data → JSONL
├── convert_feather.py       # 2026 JSONL → Feather
├── process_2025.py          # 2025 JSONL → Feather + filter K9
└── pages_info.md            # API reference notes
```

### License

Internal use. Data sourced from [sirup.inaproc.id](https://sirup.inaproc.id).
