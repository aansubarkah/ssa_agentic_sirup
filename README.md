# SSA SIRUP

Scraping pipeline for Indonesia's **SIRUP Inaproc** (Sistem Informasi Rencana Umum Pengadaan) — the government's central e-procurement planning database hosted at `sirup.inaproc.id`.

Pulls millions of procurement plan records per budget year via the site's internal DataTables API, converts them to efficient columnar formats, and filters by ministry/agency.

---

## Human Guide

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

A **single script**, `sirup.py`, handles everything: pass the budget year (`--tahun`) and it pulls the data, then converts it to Feather + pipe-delimited CSV.

**1. Download + convert data for a budget year**

```bash
# 2026 budget year (pull JSONL, then convert to feather + csv)
uv run sirup.py --tahun 2026

# 2025 budget year
uv run sirup.py --tahun 2025

# Any other year that SIRUP has published
uv run sirup.py --tahun 2024
```

This may take a while (~3M records). It's resume-safe — if interrupted, re-run the same command and it continues from where it left off.

**2. Optional flags**

```bash
uv run sirup.py --tahun 2026 --no-convert      # pull JSONL only, skip conversion
uv run sirup.py --tahun 2025 --convert-only    # convert an existing JSONL only (skip the pull)
```

**3. Output files**

| File | Description |
|---|---|
| `sirup_YYYY_all.jsonl` | Raw JSON Lines — one JSON object per line, one per procurement package |
| `sirup_YYYY_all.feather` | All records in Apache Feather format (fast to read with pandas/polars) |
| `sirup_YYYY_all.csv` | Same records, pipe-delimited CSV (`|` separator) |

> `YYYY` is the budget year you passed via `--tahun`.

### Troubleshooting

- **Session expired**: Open `sirup.inaproc.id` in your browser, log in, copy the new `PLAY_SESSION` cookie value, and update the `PLAY_SESSION` template at the top of `sirup.py`.
- **Empty results**: The API may be down or the budget year data hasn't been published yet. Check `sirup.inaproc.id` directly.

### Project Structure

```
├── .gitignore
├── .python-version          # Python version pin for uv
├── pyproject.toml           # Dependencies (httpx, pandas, pyarrow)
├── main.py                  # Stub entry point
├── sirup.py                 # ★ Single entry point: pull + convert for any year (--tahun)
├── pull_sirup.py            # (legacy) Pull 2026 data → JSONL
├── pull_sirup_2025.py       # (legacy) Pull 2025 data → JSONL
├── convert_feather.py       # (legacy) 2026 JSONL → Feather
├── process_2025.py          # (legacy) 2025 JSONL → Feather + filter K9
└── pages_info.md            # API reference notes
```

### License

Internal use. Data sourced from [sirup.inaproc.id](https://sirup.inaproc.id).

---

## Agent AI Guide

> **TL;DR**: This is a data-extraction pipeline. The single script `sirup.py` talks to a public government API, paginates through results, dumps JSONL, then converts to Feather/CSV. No auth tokens needed — just cookie headers that may need refreshing.

### Architecture

```
sirup.py --tahun YYYY  →  sirup_YYYY_all.jsonl        (raw API dump)
                        →  sirup_YYYY_all.feather      (JSONL → Arrow Feather)
                        →  sirup_YYYY_all.csv          (JSONL → pipe-delimited CSV)

Flags: --no-convert (pull only) · --convert-only (skip pull)
```

The legacy per-year scripts (`pull_sirup.py`, `pull_sirup_2025.py`, `convert_feather.py`, `process_2025.py`) still exist but `sirup.py` supersedes them — prefer it for any new budget year.

### Key Details

| Aspect | Value |
|---|---|
| **API endpoint** | `GET https://sirup.inaproc.id/sirup/caripaketctr/search` |
| **Pagination** | DataTables protocol — `start` + `length` params, max `length=100_000` per request |
| **Resume safety** | Per-year checkpoint files (`sirup_YYYY_checkpoint.json`) track offset; JSONL is append-only |
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

- **Add a new budget year**: Just run `uv run sirup.py --tahun YYYY` — no new script needed. The year is injected into the `tahunAnggaran` request param, the output/checkpoint filenames (`sirup_YYYY_*`), and the `tahunAnggaranPilihan` field of the `PLAY_SESSION` cookie. If the cookie is expired, refresh the `PLAY_SESSION` template at the top of `sirup.py`.
- **Filter by different KLDI**: In `process_2025.py`, change `FILTER_KLDI` (e.g. `K2` = Kementerian PUPR).
- **Change page size**: Adjust `PAGE_SIZE` — values above 100k may be rejected by the server.
