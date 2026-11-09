"""data-cleaner — a class-based, robust data-cleaning pipeline.

Turns a messy CSV into a tidy dataset while keeping a full audit trail of
every change. Cleaning behavior is declared up front with ``ColumnRule``s;
each phase runs as a method that logs to the audit; the same engine works as
a library or through the CLI.

Design goals
------------
* Trust nothing on load — read raw text (``dtype=object``, ``keep_default_na=False``)
  so the mess you are paid to find is preserved, not silently mangled by pandas.
* Declarative rules, imperative engine — per-column rules declare intent;
  the engine applies them and records what it did.
* Fail soft, report everything — malformed rows and coercion failures are
  logged, not silently dropped or quietly fatal.
"""
from __future__ import annotations

import ast
import operator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

# Sentinels treated as missing during normalization (after whitespace strip).
_NAN_TOKENS = {"", "n/a", "na", "null", "nan", "none", "-", "unknown"}

_VALID_DTYPES = {"id", "text", "number", "date", "category"}

# --- safe arithmetic for `compute` expressions -----------------------------
_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}


def _expr_columns(expr: str) -> list[str]:
    return [n.id for n in ast.walk(ast.parse(expr, mode="eval")) if isinstance(n, ast.Name)]


def _eval_expr(expr: str, df: pd.DataFrame) -> pd.Series:
    """Evaluate a safe arithmetic expression (column refs + + - * / %) vectorized."""
    env = {
        n: pd.to_numeric(pd.to_numeric(df[n], errors="coerce"))
        for n in _expr_columns(expr)
    }

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return env[node.id]
        if isinstance(node, ast.BinOp):
            return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise ValueError(f"unsupported expression node: {node}")

    return _eval(ast.parse(expr, mode="eval").body)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ColumnRule:
    """Declarative cleaning rule for a single column.

    ``dtype``: ``id`` | ``text`` | ``number`` | ``date`` | ``category``.
    ``canonical`` maps aliases to a canonical value (category dtype).
    ``compute`` is an optional arithmetic expression (column refs, ``+ - * / %``)
    that derives this column's final value.
    ``validates_over`` names the *stored* column to compare against ``compute``;
    mismatches set a ``<name>_was_wrong`` boolean flag instead of being silent.
    """

    name: str
    dtype: str = "text"
    required: bool = False
    date_formats: tuple[str, ...] = ()
    canonical: dict[str, str] = field(default_factory=dict)
    currency: bool = False
    compute: Optional[str] = None
    validates_over: Optional[str] = None
    tolerance: float = 0.01

    def __post_init__(self):
        if self.dtype not in _VALID_DTYPES:
            raise ValueError(f"invalid dtype '{self.dtype}' for column '{self.name}'")


@dataclass
class AuditEntry:
    step: str
    count: int
    detail: str
    column: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class DataCleaner:
    """Run a declarative cleaning pipeline and produce a documented output."""

    def __init__(self, rules: Iterable[ColumnRule]):
        self.rules: dict[str, ColumnRule] = {r.name: r for r in rules}
        if not self.rules:
            raise ValueError("at least one ColumnRule is required")
        self._audit: list[AuditEntry] = []
        self._profile_raw: dict[str, Any] = {}
        self._bad_lines: int = 0
        self._df: Optional[pd.DataFrame] = None

    # -- state -------------------------------------------------------------
    @property
    def df(self) -> Optional[pd.DataFrame]:
        return self._df

    @property
    def audit(self) -> list[AuditEntry]:
        return list(self._audit)

    def _log(self, step: str, count: int, detail: str, column: Optional[str] = None) -> None:
        self._audit.append(AuditEntry(step=step, count=count, detail=detail, column=column))

    # -- I/O ---------------------------------------------------------------
    def from_csv(self, path: str | Path) -> "DataCleaner":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"input not found: {path}")

        held = self._audit
        try:
            df = pd.read_csv(
                path, dtype=object, keep_default_na=False,
                on_bad_lines="skip", engine="python",
            )
        except Exception as exc:  # malformed enough to defeat even the python engine
            raise ValueError(f"could not parse {path}: {exc}") from exc
        self._audit = held

        missing = [c for c in self.rules if c not in df.columns]
        if missing:
            raise ValueError(f"input missing columns: {missing}")

        self._profile_raw = {
            "path": str(path),
            "raw_rows": int(len(df)),
            "raw_cols": int(df.shape[1]),
        }
        self._df = pd.DataFrame(df)  # copy
        self._log("load", len(df), f"loaded {len(df)} rows × {df.shape[1]} cols from {path}")
        return self

    # -- phases ------------------------------------------------------------
    def profile(self) -> dict[str, Any]:
        """Profile the current frame (run before cleaning to describe the raw state)."""
        df = self._df
        if df is None:
            raise RuntimeError("no data loaded")
        return {
            "shape": list(df.shape),
            "columns": [
                {"name": c, "dtype": str(df[c].dtype), "nulls": int(df[c].isna().sum())}
                for c in df.columns
            ],
            "duplicate_rows": int(df.duplicated().sum()),
            "total_blanks": int((df == "").sum().sum()),
        }

    def strip_whitespace(self) -> "DataCleaner":
        _df = self.df
        if _df is None:
            raise RuntimeError("no data loaded")
        self._df = _df.map(lambda v: v.strip() if isinstance(v, str) else v)
        self._log("strip_whitespace", 1, "trimmed leading/trailing spaces in all cells")
        return self

    def normalize_nulls(self) -> "DataCleaner":
        df = self.df
        if df is None:
            raise RuntimeError("no data loaded")
        blank = int((df == "").sum().sum())
        df = df.replace("", pd.NA)
        for col in df.columns:
            df[col] = df[col].map(
                lambda v: pd.NA if isinstance(v, str) and v.strip().lower() in _NAN_TOKENS else v
            )
        self._df = df
        self._log("normalize_nulls", blank, "standardized blanks & sentinels to missing (NA)")
        return self

    def coerce_numbers(self) -> "DataCleaner":
        df = self.df
        if df is None:
            raise RuntimeError("no data loaded")
        for col, rule in self.rules.items():
            if rule.dtype != "number":
                continue
            s = df[col].astype(str)
            if rule.currency:
                s = s.str.replace(r"[$,\s€£]", "", regex=True)
            num = pd.to_numeric(s, errors="coerce")
            failed = int((df[col].notna() & num.isna()).sum())
            self._df[col] = num
            if failed:
                self._log("coerce_number", failed, "unparseable cells set to NA (kept as missing)", col)
            self._log("coerce_number", int(num.isna().sum()),
                      "coerced to numeric; currency markers ($ ,) stripped" if rule.currency else "coerced to numeric", col)
        return self

    def parse_dates(self) -> "DataCleaner":
        df = self.df
        if df is None:
            raise RuntimeError("no data loaded")
        for col, rule in self.rules.items():
            if rule.dtype != "date":
                continue
            s = df[col].astype(str).replace("", pd.NA)
            parsed = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
            # 1) explicit formats from the rule (e.g. %m/%d/%Y catches 05/02/2024)
            for fmt in rule.date_formats:
                tmp = pd.to_datetime(s, format=fmt, errors="coerce")
                parsed = parsed.mask(tmp.notna() & parsed.isna(), tmp)
            # 2) fall back to pandas inference for anything unresolved (ISO, %Y-1-15, ...)
            if parsed.isna().any():
                unresolved = parsed.isna() & s.notna()
                inf = pd.to_datetime(s[unresolved], errors="coerce")
                parsed = parsed.mask(unresolved, inf)
            failed = int(parsed.isna().sum())
            strf = parsed.dt.strftime("%Y-%m-%d")
            self._df[col] = strf.where(parsed.notna())  # NaT -> missing, not the string "NaT"
            self._log("parse_date", failed, "normalized date to YYYY-MM-DD", col)
        return self

    def normalize_categories(self) -> "DataCleaner":
        df = self.df
        if df is None:
            raise RuntimeError("no data loaded")
        for col, rule in self.rules.items():
            if rule.dtype != "category":
                continue
            s = df[col].map(lambda v: v.lower().strip() if isinstance(v, str) else v)
            unknown = set()
            def _map(v):
                if v is pd.NA or not isinstance(v, str):
                    return v
                if v in rule.canonical:
                    return rule.canonical[v]
                unknown.add(v)
                return v
            s = s.map(_map)
            self._df[col] = s
            self._log("normalize_category", len(unknown), f"canonicalized; unmapped values kept: {sorted(unknown)[:10]}", col)
        return self

    def dedupe(self) -> "DataCleaner":
        df = self.df
        if df is None:
            raise RuntimeError("no data loaded")
        before = len(df)
        self._df = df.drop_duplicates().reset_index(drop=True)
        removed = before - len(self._df)
        self._log("dedupe", removed, f"removed {removed} exact duplicate rows")
        return self

    def derive(self) -> "DataCleaner":
        df = self.df
        if df is None:
            raise RuntimeError("no data loaded")
        for col, rule in self.rules.items():
            if not rule.compute:
                continue
            computed = _eval_expr(rule.compute, df)
            if rule.validates_over and rule.validates_over in df.columns:
                stored = pd.to_numeric(df[rule.validates_over], errors="coerce")
                mismatch = stored.notna() & ((stored - computed).abs() > rule.tolerance)
                flag = f"{rule.name}_was_wrong"
                self._df[flag] = mismatch.fillna(False)
                self._log("derive", int(mismatch.sum()),
                          f"recomputed {rule.name}={rule.compute}; flagged {mismatch.sum()} mismatches", col)
            self._df[rule.name] = computed
        return self

    def check_required(self) -> "DataCleaner":
        df = self.df
        if df is None:
            raise RuntimeError("no data loaded")
        req = [c for c, r in self.rules.items() if r.required]
        if req:
            missing = df[req].isna().any(axis=1).sum()
            self._log("check_required", int(missing), f"rows missing one or more required fields {req}")
        return self

    def clean(self) -> "DataCleaner":
        """Run every phase in a sensible order; each logs to the audit."""
        self.strip_whitespace()
        self.normalize_nulls()
        self.coerce_numbers()
        self.parse_dates()
        self.normalize_categories()
        self.dedupe()
        self.derive()
        self.check_required()
        return self

    # -- export ------------------------------------------------------------
    def export(self, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        df = self.df
        if df is None:
            raise RuntimeError("no data to export")

        df.to_csv(out / "clean.csv", index=False)

        # data dictionary
        facts = []
        for c in df.columns:
            rule = self.rules.get(c.replace("_was_wrong", ""))
            base = c.removesuffix("_was_wrong")
            rule = self.rules.get(base)
            facts.append({
                "column": c,
                "dtype_after": str(df[c].dtype),
                "base_column": base,
                "derived": rule.compute if rule else "",
                "required": bool(rule.required) if rule else False,
                "dtype_rule": rule.dtype if rule else "output",
            })
        pd.DataFrame(facts).to_csv(out / "data-dictionary.csv", index=False)

        # audit / change log
        src = self._profile_raw
        lines = [
            "# Cleaning report",
            "",
            f"- Input: {src.get('path')}",
            f"- Rows in: {src.get('raw_rows')}  /  Rows out: {len(df)}",
            "",
            "## Audit log",
            "",
        ]
        if self._bad_lines:
            lines.append(f"- *{self._bad_lines} malformed line(s) were skipped during load.*")
        for entry in self.audit:
            if entry.count or entry.step == "load":
                lines.append(
                    f"- **{entry.step}**{(' [' + entry.column + ']') if entry.column else ''}: "
                    f"{entry.count} — {entry.detail}"
                )
        lines.append("")
        lines.append("## Output files")
        lines.append("- `clean.csv` — cleaned data")
        lines.append("- `data-dictionary.csv` — column schema")
        (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")

        # machine-readable audit
        (out / "audit.json").write_text(
            "\n".join(__import__("json").dumps(e.to_dict()) for e in self.audit),
            encoding="utf-8",
        )
        return out


def clean_csv(input_path: str | Path, out_dir: str | Path = "output",
              rules: Optional[Iterable[ColumnRule]] = None) -> DataCleaner:
    """Convenience wrapper: load → clean → export. Returns the cleaner (also .audit)."""
    if rules is None:
        rules = DEFAULT_RULES
    cleaner = DataCleaner(rules).from_csv(input_path)
    cleaner.clean()
    cleaner.export(out_dir)
    return cleaner


# --------------------------------------------------------------------------- #
# Default rules for the portfolio demo dataset
# --------------------------------------------------------------------------- #
DEFAULT_RULES = [
    ColumnRule("order_id", dtype="id", required=True),
    ColumnRule("order_date", dtype="date", required=True, date_formats=(
        "%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d",
    )),
    ColumnRule("customer_name", dtype="text"),
    ColumnRule("region", dtype="category", canonical={
        "east": "East", "west": "West", "north": "North",
        "south": "South", "central": "Central",
    }),
    ColumnRule("product", dtype="text"),
    ColumnRule("category", dtype="category", canonical={
        "electronics": "Electronics", "accessories": "Accessories",
    }),
    ColumnRule("qty", dtype="number", required=True),
    ColumnRule("unit_price", dtype="number", currency=True),
    ColumnRule("total_sales", dtype="number", currency=True,
               compute="qty * unit_price", validates_over="total_sales"),
    ColumnRule("payment", dtype="category", canonical={
        "visa": "Visa", "paypal": "PayPal", "amex": "Amex",
        "credit card": "Credit Card", "cash": "Cash",
    }),
]
