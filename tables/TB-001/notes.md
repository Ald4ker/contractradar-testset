# TB-001 - Supplier statement of account with no ruled lines

The statement has no lines between columns or rows. Details wrap onto a second or third line, every row has either the Debit or the Credit cell empty, and the balance goes negative once, printed in brackets. A text dump split on whitespace turns each wrapped line into a new row and slides credits into the Debit column.

## What counts as a row

Every statement line is a row, including the opening balance brought forward. The Totals line is not a row. Bracketed amounts are negative. A blank debit or credit cell stays blank.

## Hazards

- **no_ruling_lines**: No ruled lines or cell borders: column boundaries have to be inferred from alignment alone.
- **wrapped_cells**: Long cell text wraps onto two or more lines; the continuation lines are not new rows.
- **empty_cells**: Some cells are blank (a debit or a credit); splitting a line on whitespace shifts the next value into the wrong column.
- **negative_in_brackets**: A negative amount is printed in brackets, (146.10), not with a minus sign.
- **brought_forward_row**: The statement opens with a 'balance brought forward' line, which is a row of the statement.
- **totals_row**: A totals line closes the table; it is not a row.

## Columns

| CSV column | Printed header | Type |
|---|---|---|
| `date` | Date | date |
| `reference` | Ref | id |
| `details` | Details | text |
| `debit_gbp` | Debit | money |
| `credit_gbp` | Credit | money |
| `balance_gbp` | Balance | money |

## What the wrong extraction gets wrong
`wrong.csv` is the naive text-dump extraction (pdftotext -layout, one line = one row, cells split on 2+ spaces). Scored against `expected.csv`: **24% cell accuracy** (an extra row counts as a row of wrong cells; 47% of the expected cells are right), **0/11 rows exactly right**, 11 extra rows, 0 missing rows.

Extra rows it invents (first text of each):

- `Centre passenger lifts: quarterly service visit`
- `and LOLER thorough examination certificate`
- `jetting and CCTV survey`
- `lanterns, columns 4 to 9`
- `offices: fire alarm and emergency lighting`
- `on boiler 2, Market Walk depot`
- `out-of-hours call-out charge)`
- `park: out of hours, 2 operatives for 6 hours,`

Column accuracy: `reference` 91%, `details` 18%, `debit_gbp` 64%, `credit_gbp` 9%, `balance_gbp` 0%.
