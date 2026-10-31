# Cleaning report — messy_sales.csv

- Input rows: 18
- Output rows: 17
- Duplicates removed: 1
- Blank cells standardized: 10

## Changes applied

- load: 18 — raw rows loaded (10 cols)
- whitespace: 1 — trimmed leading/trailing spaces in all cells
- blanks: 10 — standardized empties/'' to missing (NA)
- numeric: 1 — coerced col 'qty' to numeric
- numeric: 1 — coerced col 'total_sales' to numeric
- date: 2 — parsed 'order_date' to one format; mixed input formats
- text_standard: 1 — lowercased + mapped aliases to canonical values
- duplicates: 1 — removed 1 exact duplicate rows
- derived: 1 — recomputed total_sales = qty*unit_price; flagged rows where stored total disagreed
- incomplete: 4 — rows missing one or more required fields (['order_id', 'order_date', 'product', 'qty'])

## Output files
- `clean.csv` — cleaned data
- `data-dictionary.csv` — column schema