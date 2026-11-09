# Cleaning report

- Input: input/messy_sales.csv
- Rows in: 18  /  Rows out: 17

## Audit log

- **load**: 18 — loaded 18 rows × 10 cols from input/messy_sales.csv
- **strip_whitespace**: 1 — trimmed leading/trailing spaces in all cells
- **normalize_nulls**: 9 — standardized blanks & sentinels to missing (NA)
- **coerce_number** [qty]: 1 — coerced to numeric
- **coerce_number** [total_sales]: 1 — unparseable cells set to NA (kept as missing)
- **coerce_number** [total_sales]: 1 — coerced to numeric; currency markers ($ ,) stripped
- **parse_date** [order_date]: 2 — normalized date to YYYY-MM-DD
- **dedupe**: 1 — removed 1 exact duplicate rows
- **derive** [total_sales]: 1 — recomputed total_sales=qty * unit_price; flagged 1 mismatches
- **check_required**: 4 — rows missing one or more required fields ['order_id', 'order_date', 'qty']

## Output files
- `clean.csv` — cleaned data
- `data-dictionary.csv` — column schema