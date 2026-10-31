# Data Cleaning Portfolio — Messy Retail Sales

A complete data-cleaning project demonstrating a professional, documented
cleaning workflow on a deliberately messy retail sales dataset.

## What's in the repo
```
input/messy_sales.csv     raw, messy source data (do not edit)
clean.py                  the reusable cleaning pipeline
pyproject.toml / uv.lock  uv project definition + locked dependencies
output/clean.csv          cleaned, tidy dataset
output/summary.md         change log: every issue found and fixed
output/data-dictionary.csv  column schema after cleaning
```

## Issues found & fixed (see output/summary.md for the full log)
- [x] Leading/trailing whitespace in every cell
- [x] Blank values / empty strings standardized to missing (NA)
- [x] Text numbers, `$`, and thousands separators coerced to numerics
- [x] Mixed date formats normalized to one standard (`YYYY-MM-DD`)
- [x] Inconsistent casing and aliases mapped to canonical values
      (e.g. `"WEST"`/`" West "`/`"west"` → `West`)
- [x] Exact duplicate rows removed
- [x] Stored totals validated against `qty × unit_price`; mismatches
      flagged and corrected
- [x] Required-field completeness reported

## How to run
Managed with [uv](https://docs.astral.sh/uv/). Dependencies are pinned in `uv.lock`.
```bash
uv sync                                  # create .venv with locked deps
uv run clean.py input/messy_sales.csv    # run the pipeline
```
`uv run` will also sync automatically on first use. Python version is set in
`.python-version` (3.12; project supports 3.10+). The `CONFIG` section at the top of `clean.py`
makes the pipeline reusable: change the column names/mappings and point
it at any messy CSV. Every job ships with a written change log like
`output/summary.md` — the detail that sells the work.
