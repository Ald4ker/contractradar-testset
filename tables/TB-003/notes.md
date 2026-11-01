# TB-003 - Payment milestone schedule crossing a page, one row split by the page break

The schedule starts low on page 1, so milestone 5 (Envelope) is split by the page break: the first lines of its payment trigger are on page 1 and the rest continue on page 2, under the repeated header, in a row whose other cells are empty. The running header and the page footer fall between the two halves in a text dump.

## What counts as a row

One row per milestone. Milestone 5's payment trigger starts at the foot of page 1 and finishes at the top of page 2: it is one cell. The repeated header and the Total line are not rows.

## Hazards

- **table_crosses_page**: The table runs over a page break.
- **split_row**: One row is split by the page break: its text continues on the next page, under the repeated header, with the other cells empty.
- **repeated_header**: The header row is printed again on the next page; it is not a data row.
- **footer_interleaves**: Page footer and running-header text fall between table rows in a text dump.
- **wrapped_cells**: Long cell text wraps onto two or more lines; the continuation lines are not new rows.
- **totals_row**: A totals line closes the table; it is not a row.

## Columns

| CSV column | Printed header | Type |
|---|---|---|
| `milestone_no` | No. | id |
| `milestone` | Milestone | text |
| `payment_trigger` | Payment trigger | text |
| `due_date` | Due date | date |
| `amount_gbp` | Amount (£, ex VAT) | money |

## What the wrong extraction gets wrong
`wrong.csv` is the naive text-dump extraction (pdftotext -layout, one line = one row, cells split on 2+ spaces). Scored against `expected.csv`: **26% cell accuracy** (an extra row counts as a row of wrong cells; 68% of the expected cells are right), **1/12 rows exactly right**, 20 extra rows, 0 missing rows.

Extra rows it invents (first text of each):

- `Council's structural engineer`
- `No. Milestone Payment trigger Due date Amount (£, ex`
- `Northam Vale County Council · NVCC/CAP/0412 · Schedule 2`
- `Northam Vale County Council · Schedule 2 - Payment milestone`
- `SYNTHETIC TEST DOCUMENT - fictional authority and supplier -`
- `VAT)`
- `a water test of every roof outlet and gutter and a visual`
- `after practical completion`

Column accuracy: `milestone` 67%, `payment_trigger` 8%, `due_date` 83%, `amount_gbp` 83%.
