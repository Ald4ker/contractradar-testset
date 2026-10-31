# CR-007 - Multi-lot award notice with an unawarded lot and a short standstill

Three lots, two awarded to different suppliers, lot 3 not awarded. The evaluation scores table crosses the page. Standstill ends 6 working days after publication (8 required). Light touch contract.

## Hazards

- **multi_lot**: Several lots awarded to different suppliers.
- **unawarded_lot**: One lot was not awarded; it must appear with awarded=false and no supplier.
- **totals_row**: A totals row must not be read as a lot or a line item.
- **evaluation_scores_table**: Tenderer scoring table that could be mistaken for lot values.
- **table_crosses_page**: A table runs over a page boundary; the header row repeats on the next page.
- **standstill_too_short**: The stated standstill end date is fewer than 8 working days after publication.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £3,430,000 is at or above the light touch threshold £663,540 (inc VAT) applicable on 2026-03-09.
- `PA23-s51-standstill-short` (high): Standstill ends 2026-03-17 which is only 6 working days after publication on 2026-03-09; s.51 requires 8.
