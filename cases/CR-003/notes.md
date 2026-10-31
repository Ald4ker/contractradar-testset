# CR-003 - Contract details notice with borderless, grouped particulars

Contract particulars are a borderless three-column table whose first column is a section label spanning several rows. Labels are non-standard ('Initial expiry', 'Estimated total (ex VAT)'), an annual figure sits next to the total, and dates are 01-Mar-2026 style.

## Hazards

- **borderless_table**: Key/value table has no rules; column boundaries must be inferred from alignment.
- **grouped_rows**: A section label is printed once and spans several rows (blank cells below it).
- **label_synonyms**: Fields use non-standard labels (e.g. 'Initial expiry' for the end date).
- **annual_vs_total_value**: An annual price and a total contract value both appear; only the total is the contract value.
- **date_abbr**: Dates printed as 03-Mar-2026.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £6,400,000 is at or above the works threshold £5,193,000 (inc VAT) applicable on 2026-02-05.
