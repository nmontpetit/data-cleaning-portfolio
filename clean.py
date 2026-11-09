#!/usr/bin/env python3
"""CLI wrapper for the data-cleaner library.

Usage:
    uv run clean.py input/messy_sales.csv            # clean + export to output/
    uv run clean.py input/messy_sales.csv --out /tmp/x
    uv run clean.py input/messy_sales.csv --profile  # only profile the raw data
    uv run clean.py <file> --json | jq               # emit the audit as NDJSON to stdout
"""
from __future__ import annotations

import argparse
import sys

from dataclean import DataCleaner, DEFAULT_RULES, clean_csv


def main() -> int:
    p = argparse.ArgumentParser(description="Class-based data-cleaning pipeline")
    p.add_argument("input", help="path to a messy CSV")
    p.add_argument("--out", default="output", help="output directory (default: output/)")
    p.add_argument("--profile", action="store_true", help="only profile the raw data, no cleaning")
    p.add_argument("--json", action="store_true", help="dump audit as NDJSON to stdout (no files)")
    args = p.parse_args()

    if args.json:
        c = DataCleaner(DEFAULT_RULES).from_csv(args.input)
        c.clean()
        for e in c.audit:
            if e.count or e.step == "load":
                print(__import__("json").dumps(e.to_dict()))
        return 0

    if args.profile:
        c = DataCleaner(DEFAULT_RULES).from_csv(args.input)
        import pprint
        pprint.pprint(c.profile())
        return 0

    c = clean_csv(args.input, args.out, rules=DEFAULT_RULES)
    n_in = c.audit[0].count  # load row count
    n_out = len(c.df)
    dup = next((e.count for e in c.audit if e.step == "dedupe"), 0)
    mis = next((e.count for e in c.audit if e.step == "derive"), 0)
    print(f"input rows         : {n_in}")
    print(f"output rows        : {n_out}")
    print(f"exact dups removed : {dup}")
    print(f"stored totals wrong: {mis}")
    print(f"wrote              : {args.out}/clean.csv / summary.md / data-dictionary.csv / audit.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
