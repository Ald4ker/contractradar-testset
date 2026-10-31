# CR-006 - Contract details notice in a two-column stacked layout

Labels and values are stacked in a narrow left column beside a narrative right column, so a line-based text dump interleaves them. Value is printed as £2.31m. Published 61 days after signature; payment terms 45 days.

## Hazards

- **two_column_layout**: Page is laid out in two columns; a line-based text dump interleaves them.
- **stacked_label_value**: Each label is printed on one line and its value on the next.
- **money_short_format**: Money printed as £2.31m rather than £2,310,000.
- **trading_as_name**: Supplier printed with a trading name in brackets; the legal name is the answer.
- **late_contract_details_notice**: Contract details notice published more than 30 days after signature.
- **payment_terms_over_30**: Stated payment terms exceed 30 days.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £2,310,000 is at or above the services threshold £207,720 (inc VAT) applicable on 2026-04-29.
- `PA23-s68-payment-over-30d` (medium): Payment terms of 45 days exceed the 30-day implied term in s.68.
- `PA23-s53-cdn-late` (medium): Contract entered into 2026-02-27, notice published 2026-04-29: 61 days, over the 30-day limit in s.53.
