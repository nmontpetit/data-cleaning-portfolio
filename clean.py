"""
clean.py — reusable data cleaning pipeline (portfolio template).

Takes a messy CSV, profiles it, cleans it, and writes:
    output/clean.csv          the cleaned, tidy dataset
    output/data-dictionary.csv column type / role documentation
    output/summary.md         a change log of every issue found & fixed

Readable as a template: drop any messy dataset in, adjust the COLUMN/MAPPINGS
section, run `python3 clean.py input/yourfile.csv` and get a documented output.

Works on Python 3.10+ with pandas. Stdlib CSV fallback not required.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG — adjust to the dataset you're cleaning (this is the JOB-WINNING part:
# showing you know the domain specifics of the client's data).
# ---------------------------------------------------------------------------
# Columns that are categorical text: normalize case/spaces/whitespace.
TEXT_COLS = ["region", "product", "category", "payment"]
# Columns that should truly be numeric (strip $ , and coerce text numbers).
NUMERIC_COLS = ["qty", "unit_price", "total_sales"]
# Column to parse as a date (list of accepted formats).
DATE_COL = "order_date"
DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%Y-%-m-%-d"]
# Alias spellings that should collapse to a single canonical value.
CANONICAL = {
    "category": {"electronics": "Electronics", "accessories": "Accessories"},
    "region": {"east": "East", "west": "West", "north": "North", "south": "South", "central": "Central"},
    "payment": {"visa": "Visa", "paypal": "PayPal", "amex": "Amex",
                "credit card": "Credit Card", "cash": "Cash"},
}
# Columns that require a non-empty value (a row missing these is flagged).
REQUIRED = ["order_id", "order_date", "product", "qty"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _flags(series: pd.Series) -> pd.Series:
    """A "clean" column per original row, for the audit report."""
    return series

def _log(report: list[dict], file: str, kind: str, count: int, detail: str):
    if count:
        report.append({"file": file, "issue": kind, "count": count, "detail": detail})


def main(input_path: str, out_dir: str = "output") -> None:
    src = Path(input_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    changes: list[dict] = []

    # ---- 1) LOAD raw, keep everything as text so nothing is silently lost ----
    df = pd.read_csv(src, dtype=object, keep_default_na=False)
    changes.append({"file": src.name, "issue": "load",
                    "count": len(df), "detail": f"raw rows loaded ({len(df.columns)} cols)"})

    # ---- 2) WHITESPACE: trim every cell ----
    df = df.map(lambda v: v.strip() if isinstance(v, str) else v)
    _log(changes, src.name, "whitespace", 1, "trimmed leading/trailing spaces in all cells")

    # ---- 3) NULL / blank handling ----
    null_before = int((df == "").sum().sum())
    df = df.replace("", pd.NA)
    _log(changes, src.name, "blanks", null_before, "standardized empties/'' to missing (NA)")

    # ---- 4) NUMERIC coercion ($ , and text numbers) ----
    for c in NUMERIC_COLS:
        raw = df[c].astype(str)
        coerced = raw.str.replace(r"[$,\s]", "", regex=True)
        num = pd.to_numeric(coerced, errors="coerce")
        _log(changes, src.name, "numeric", int(num.isna().sum()), f"coerced col '{c}' to numeric")
        df[c] = num
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")

    # ---- 5) DATE parsing to a single standard ----
    dcol = DATE_COL
    parsed = pd.to_datetime(df[dcol].astype(str), format="mixed", errors="coerce")
    _log(changes, src.name, "date", int(parsed.isna().sum()),
         f"parsed '{dcol}' to one format; mixed input formats")
    df[dcol] = parsed.dt.strftime("%Y-%m-%d")

    # ---- 6) TEXT standardization (case + aliases) ----
    for c in TEXT_COLS:
        std = df[c].fillna("").str.strip().str.lower()
        std = std.replace("n/a", pd.NA).replace("null", pd.NA)
        if c in CANONICAL:
            std = std.map(lambda v: CANONICAL[c].get(v, v) if isinstance(v, str) else v)
        df[c] = std.fillna(pd.NA) if std.isna().any() else std
    _log(changes, src.name, "text_standard", 1, "lowercased + mapped aliases to canonical values")

    # ---- 7) DEDUPE full rows ----
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    _log(changes, src.name, "duplicates", before - len(df), f"removed {before - len(df)} exact duplicate rows")

    # ---- 8) DERIVED: recompute totals, flag mismatches ----
    computed = df["qty"] * df["unit_price"]
    mismatch = ((df["total_sales"] - computed).abs() > 0.01) & df["total_sales"].notna()
    _log(changes, src.name, "derived", int(mismatch.sum()),
         "recomputed total_sales = qty*unit_price; flagged rows where stored total disagreed")
    df["stored_total_was_wrong"] = mismatch.fillna(False)
    df["total_sales"] = computed

    # ---- 9) REQUIRED-field completeness ----
    incomplete = df[REQUIRED].isna().any(axis=1).sum()
    _log(changes, src.name, "incomplete", int(incomplete),
         f"rows missing one or more required fields ({REQUIRED})")

    # ---- 10) ORDER + WRITE clean output ----
    df = df.sort_values(by="order_id", na_position="last").reset_index(drop=True)
    df.to_csv(out / "clean.csv", index=False)

    # data dictionary
    dd = pd.DataFrame({
        "column": df.columns,
        "dtype_after": [str(df[c].dtype) for c in df.columns],
        "role": ["key" if c == "order_id" else "derived" if c in ("total_sales", "stored_total_was_wrong") else "attribute" for c in df.columns],
    })
    dd.to_csv(out / "data-dictionary.csv", index=False)

    # summary / change log
    lines = [f"# Cleaning report — {src.name}", "",
             f"- Input rows: {len(pd.read_csv(src, dtype=object, keep_default_na=False))}",
             f"- Output rows: {len(df)}",
             f"- Duplicates removed: {sum(c['count'] for c in changes if c['issue']=='duplicates')}",
             f"- Blank cells standardized: {sum(c['count'] for c in changes if c['issue']=='blanks')}", "",
             "## Changes applied", ""]
    for c in changes:
        lines.append(f"- {c['issue']}: {c['count']} — {c['detail']}")
    lines.append("")
    lines.append("## Output files")
    lines.append("- `clean.csv` — cleaned data")
    lines.append("- `data-dictionary.csv` — column schema")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    # ---- 11) console summary ----
    dup = sum(c["count"] for c in changes if c["issue"] == "duplicates")
    mis = sum(c["count"] for c in changes if c["issue"] == "derived")
    print(f"input rows         : {len(pd.read_csv(src, dtype=object, keep_default_na=False))}")
    print(f"output rows        : {len(df)}")
    print(f"exact dups removed : {dup}")
    print(f"stored totals wrong: {mis}")
    print(f"wrote              : {out/'clean.csv'} / {out/'summary.md'} / {out/'data-dictionary.csv'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "input/messy_sales.csv")
