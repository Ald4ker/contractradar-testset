# TB-002 - Council spend statement with grouped dates, directorates and suppliers

The payment date is printed once per date group, the directorate once per run within a date, and the supplier once per run within a directorate, so most rows show only some of their values. Two Dunmore rows are identical apart from the transaction number. Long supplier names wrap onto a second line.

## What counts as a row

One row per transaction. A blank Payment date, Directorate or Supplier cell repeats the value above it, within the same date group. Negative amounts are refunds and stay negative.

## Hazards

- **suppressed_repeats**: Repeated values (date, directorate, supplier) are printed only on the first row of each run; the rows below inherit them.
- **identical_rows**: Two rows are identical apart from the transaction number; both are real and both must be kept.
- **wrapped_cells**: Long cell text wraps onto two or more lines; the continuation lines are not new rows.
- **totals_row**: A totals line closes the table; it is not a row.

## Columns

| CSV column | Printed header | Type |
|---|---|---|
| `payment_date` | Payment date | date |
| `directorate` | Directorate | text |
| `supplier` | Supplier | text |
| `expense_type` | Expense type | text |
| `transaction_no` | Transaction no. | id |
| `amount_gbp` | Amount (£) | money |

## What the wrong extraction gets wrong
`wrong.csv` is the naive text-dump extraction (pdftotext -layout, one line = one row, cells split on 2+ spaces). Scored against `expected.csv`: **8% cell accuracy** (an extra row counts as a row of wrong cells; 19% of the expected cells are right), **2/16 rows exactly right**, 22 extra rows, 12 missing rows.

Extra rows it invents (first text of each):

- `(Midlands) Limited`
- `Alderman Facilities Group Ltd Void property repairs 5100300 `
- `Brightwater Environmental Refund: overpaid gate 5100356 -1,2`
- `CIC accommodation`
- `Elmstead ICT Solutions Ltd Telephony 5100411 845.00`
- `Fenwick Grounds Maintenance Grounds maintenance 5100232 6,24`
- `Fenwick Grounds Maintenance Sports pitch renovation 5100413 `
- `Hardware maintenance 5100235 2,310.75`

Column accuracy: `payment_date` 25%, `directorate` 25%, `supplier` 12%, `expense_type` 12%, `transaction_no` 19%, `amount_gbp` 19%.
