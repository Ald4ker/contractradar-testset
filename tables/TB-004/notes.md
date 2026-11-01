# TB-004 - Borderless weekly payments statement: date headings, subtotals and a week split across the page

The date is not in any row: it is a heading above each week's orders, and the week of 17 July is cut by the page break, so the two orders at the top of page 2 sit under no heading of their own: their week is named only on page 1 (the week totals carry no date). Subtotal, carried-forward and brought-forward lines look like data rows, there are no ruled lines, and long descriptions wrap.

## What counts as a row

One row per order. The week-ending date comes from the heading above the order's group; the orders at the top of page 2 still belong to the week that started on page 1. Week headings, week totals, Carried forward, Brought forward and the Total for July 2026 are not rows.

## Hazards

- **no_ruling_lines**: No ruled lines or cell borders: column boundaries have to be inferred from alignment alone.
- **group_header_rows**: A date is printed as a full-width heading above its group; it is a value for every row below it, not a row of its own.
- **subtotal_rows**: Group subtotal lines are not rows.
- **table_crosses_page**: The table runs over a page break.
- **group_crosses_page**: A date group starts on one page and continues on the next without the date being printed again.
- **carried_forward_rows**: 'Carried forward' and 'brought forward' subtotal lines at the page break are not rows.
- **repeated_header**: The header row is printed again on the next page; it is not a data row.
- **footer_interleaves**: Page footer and running-header text fall between table rows in a text dump.
- **wrapped_cells**: Long cell text wraps onto two or more lines; the continuation lines are not new rows.
- **totals_row**: A totals line closes the table; it is not a row.

## Columns

| CSV column | Printed header | Type |
|---|---|---|
| `week_ending` | Week ending (group heading) | date |
| `order_no` | Order no. | id |
| `description` | Description | text |
| `cost_centre` | Cost centre | id |
| `net_gbp` | Net (£) | money |
| `vat_gbp` | VAT (£) | money |
| `gross_gbp` | Gross (£) | money |

## What the wrong extraction gets wrong
`wrong.csv` is the naive text-dump extraction (pdftotext -layout, one line = one row, cells split on 2+ spaces). Scored against `expected.csv`: **24% cell accuracy** (an extra row counts as a row of wrong cells; 64% of the expected cells are right), **0/15 rows exactly right**, 24 extra rows, 0 missing rows.

Extra rows it invents (first text of each):

- `(14 no.)`
- `1,180 m2), including traffic management`
- `Brought forward 110,260.50 21,924.10 132,184.60`
- `Carried forward 110,260.50 21,924.10 132,184.60`
- `Fenwick Lane`
- `Order no. Description Cost centre Net (£) VAT (£) Gross (£)`
- `Road bridge approach`
- `SYNTHETIC TEST DOCUMENT - fictional authority and supplier -`

Column accuracy: `week_ending` 0%, `description` 27%, `cost_centre` 80%, `net_gbp` 80%, `vat_gbp` 80%, `gross_gbp` 80%.
