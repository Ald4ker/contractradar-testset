# CR-010 - Works contract details notice with wrapped supplier name and value in words

The supplier's legal name wraps across two lines inside a narrow cell, and the contract sum is printed in words then figures. Four KPIs, 30-day terms: compliant.

## Hazards

- **supplier_name_wrapped**: Supplier legal name wraps across two lines mid-name.
- **money_words_and_figures**: Money printed in words followed by figures.
- **date_ordinal**: Dates printed as 3rd March 2026.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £7,980,000 is at or above the works threshold £5,193,000 (inc VAT) applicable on 2026-05-22.
