"""Tests for the data-cleaner library."""
from __future__ import annotations

import pandas as pd
import pytest

from dataclean import ColumnRule, DataCleaner, DEFAULT_RULES, clean_csv


def _clean(tmp_path, text, rules=DEFAULT_RULES) -> tuple[pd.DataFrame, DataCleaner]:
    src = tmp_path / "in.csv"
    src.write_text(text, encoding="utf-8")
    c = DataCleaner(rules).from_csv(src)
    c.clean()
    return c.df, c


SIMPLE = """\
order_id,region,category,qty,unit_price,total_sales
1,EAST,Electronics,2,$45.50,91
2, lower,electronics,0,0,0
"""


def test_coerce_currency_and_commas(tmp_path):
    df, c = _clean(
        tmp_path,
        "id,price\n1,\"$1,299.00\"\n2,1299\n3,N/A\n",
        rules=[ColumnRule("id", "id"), ColumnRule("price", "number", currency=True)],
    )
    assert df["price"].tolist()[0] == 1299.0
    assert df["price"].tolist()[1] == 1299.0
    assert pd.isna(df.loc[2, "price"])


def test_date_normalization(tmp_path):
    df, _ = _clean(
        tmp_path,
        "id,when\n1,2024-1-15\n2,05/02/2024\n3,\n",
        rules=[ColumnRule("id", "id"),
               ColumnRule("when", "date", date_formats=("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"))],
    )
    assert df["when"].tolist()[:2] == ["2024-01-15", "2024-05-02"]
    assert pd.isna(df.loc[2, "when"])


def test_category_canonicalization(tmp_path):
    df, _ = _clean(
        tmp_path,
        "id,region\n1,\" East \"\n2,east\n3,WEST\n",
        rules=[ColumnRule("id", "id"),
               ColumnRule("region", "category", canonical={"east": "East", "west": "West"})],
    )
    assert df["region"].tolist() == ["East", "East", "West"]


def test_dupes_collapse_after_normalization(tmp_path):
    text = "region\nEAST\n east\nwest\n"
    df, c = _clean(tmp_path, text, rules=[ColumnRule("region", "category", canonical={"east": "East"})])
    assert len(df) == 2  # "EAST" and " east" normalized to same -> deduped
    assert next(e.count for e in c.audit if e.step == "dedupe") == 1


def test_derive_recomputes_and_flags_mismatch(tmp_path):
    df, c = _clean(
        tmp_path,
        "id,qty,unit_price,total_sales\n1,3,25,10\n2,2,45.5,91\n",
        rules=[
            ColumnRule("id", "id"),
            ColumnRule("qty", "number"),
            ColumnRule("unit_price", "number"),
            ColumnRule("total_sales", "number", compute="qty * unit_price",
                       validates_over="total_sales"),
        ],
    )
    assert df.loc[0, "total_sales"] == 75.0           # corrected
    assert bool(df.loc[0, "total_sales_was_wrong"])    # flagged True
    assert not bool(df.loc[1, "total_sales_was_wrong"])  # 2*45.5 == 91


def test_unknown_category_value_kept_not_dropped(tmp_path):
    df, c = _clean(tmp_path, "region\ngadget\n", rules=[ColumnRule("region", "category")])
    assert df["region"].tolist() == ["gadget"]


def test_required_field_flagged(tmp_path):
    _, c = _clean(
        tmp_path,
        "id,qty\n1,2\n2,\n",
        rules=[ColumnRule("id", "id"), ColumnRule("qty", "number", required=True)],
    )
    entry = next(e for e in c.audit if e.step == "check_required")
    assert entry.count >= 1


def test_missing_column_raises(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("id,x\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        DataCleaner(DEFAULT_RULES).from_csv(src)


def test_full_demo_pipeline_and_export(tmp_path):
    src = tmp_path / "messy.csv"
    src.write_text(readme_fixture(), encoding="utf-8")
    c = clean_csv(src, tmp_path / "out", rules=DEFAULT_RULES)
    out = tmp_path / "out"
    assert (out / "clean.csv").exists()
    assert (out / "summary.md").exists()
    assert (out / "data-dictionary.csv").exists()
    assert (out / "audit.json").exists()
    assert c.df is not None
    assert next(e.step for e in c.audit) == "load"


# same messy fixture shape as the repo's input/messy_sales.csv
def readme_fixture() -> str:
    return (
        "order_id,order_date,customer_name,region,product,category,qty,unit_price,total_sales,payment\n"
        "1001,2024-01-05,Alice Johnson,\" East \",Laptop,Electronics,1,$1299.00,1299,VISA\n"
        "1002,2024-1-15,alice johnson,east,Laptop,electronics,1,\"1,299.00\",1299,visa\n"
        "1003,05/02/2024,Bob Smith,WEST,Keyboard,Accessories,2,$45.50,91,Paypal\n"
        "1004,,Bob smith,West,keyboard, accessories,\"2\",45.5,91.00,paypal\n"
        "1005,2024-02-10,Carol Lee,North,Mouse,Accessories,,$11.99,Credit Card\n"
        "1006,2024-02-10,Carol Lee,North,Mouse,Accessories,3,$11.99,35.97,CREDIT CARD\n"
        "1003,05/02/2024,Bob Smith,WEST,Keyboard,Accessories,2,$45.50,91,Paypal\n"
        "1016,2024-07-20,Isla Qureshi,North,Keyboard,Accessories,3,25.00,10.00,\n"
    )
