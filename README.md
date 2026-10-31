# data-cleaning-portfolio

A **class-based, auditable data-cleaning pipeline** — the engine side of a
data-cleaning freelance service. It turns a messy CSV into a tidy dataset while
keeping a full, machine-readable audit of every change. Clean and documented
output is the deliverable that sells the work; this repo is both the demo and
the reusable tool.

## What's in the repo
```
dataclean/               the library (DataCleaner + ColumnRule + audit)
  cleaner.py             engine: phases, audit log, export
clean.py                 thin CLI wrapper
tests/                   pytest suite covering every phase
input/messy_sales.csv    deliberately messy demo dataset
output/                  what the pipeline produces (regenerated on each run)
  clean.csv              tidy output
  data-dictionary.csv    column schema / rules
  summary.md             human-readable change log
  audit.json             machine-readable audit (one entry per line)
```

## Quickstart
Managed with [uv](https://docs.astral.sh/uv/); deps pinned in `uv.lock`.
```bash
uv sync                                  # create .venv (installs this package)
uv run clean.py input/messy_sales.csv    # clean + write output/
uv run pytest tests/                     # run the test suite
uv run clean.py input/messy_sales.csv --profile   # just profile the raw data
uv run clean.py input/messy_sales.csv --json | jq # audit as NDJSON, no files
```

## Using it as a library
```python
from dataclean import DataCleaner, ColumnRule, clean_csv

rules = [
    ColumnRule("id", "id"),
    ColumnRule("price", "number", currency=True),
    ColumnRule("region", "category", canonical={"east": "East", "west": "West"}),
    ColumnRule("total", "number", compute="qty * price", validates_over="total"),
]

cleaner = clean_csv("messy.csv", "out", rules=rules)
print(cleaner.df)       # tidy DataFrame
print(cleaner.audit)    # every change, as AuditEntry
```

## Design
- **Trust nothing on load.** Reads raw text (`dtype=object`, `keep_default_na=False`)
  and normalizes from there, so the mess you are paid to find is preserved and
  reported rather than silently mangled by pandas.
- **Declarative rules, imperative engine.** Each column is described by a
  `ColumnRule` (its dtype, whether it's required, acceptable date formats,
  category aliases, and any derived computation). The engine applies the phases
  and records what it did.
- **Every phase logs to an audit trail** — whitespace, nulls, coercion,
  dates, categories, dedupe, derived-value validation, and required-field
  checks — exported as both `summary.md` and `audit.json`.
- **Derived values are validated, not silently rewritten.** e.g.
  `total_sales = qty * unit_price` is recomputed, mismatches against the stored
  value are flagged in a `<column>_was_wrong` column.
- **Fail soft, report everything.** Malformed rows and unparseable cells are
  logged rather than dropped or fatal.
- **Safe arithmetic** on derived columns (a small AST evaluator — no `eval`).

## Phases
`strip_whitespace` → `normalize_nulls` → `coerce_numbers` → `parse_dates` →
`normalize_categories` → `dedupe` → `derive` → `check_required`. Each is a
method you can call individually or all at once via `.clean()`.

## Demo dataset issues it catches
- [x] Leading/trailing whitespace
- [x] Blank / sentinel values → missing (NA)
- [x] Text numbers, `$`, thousands separators → numerics
- [x] Mixed date formats → one standard (`YYYY-MM-DD`)
- [x] Casing + alias inconsistencies → canonical values
- [x] Duplicate rows removed
- [x] Stored totals validated against `qty × unit_price` (mismatches flagged + corrected)
- [x] Required-field completeness reported

## Tests
`uv run pytest tests/` covers coercion, date handling, canonicalization,
dedupe-after-normalize, derived-value mismatch flags, unknown-category
preservation, required-field detection, missing-column errors, and full
export. Add a test for any new `ColumnRule` dtype or phase.
