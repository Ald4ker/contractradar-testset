# CR-002 - Contract details notice with a priced schedule crossing a page

The priced schedule of service elements runs over the page break with a repeated header and the footer lands between rows. The value row prints the ANNUAL price first (£3,950,000 per annum) and the contract value second (£27,650,000 over 84 months); the schedule total is also the annual figure. Only £27,650,000 is correct.

## Hazards

- **table_crosses_page**: A table runs over a page boundary; the header row repeats on the next page.
- **repeated_header**: Repeated table header rows must not be read as data rows.
- **footer_interleaves**: Page footer text (authority, page x of y) falls between table rows in a text dump.
- **annual_vs_total_value**: An annual price and a total contract value both appear; only the total is the contract value.
- **totals_row**: A totals row must not be read as a lot or a line item.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £27,650,000 is at or above the services threshold £207,720 (inc VAT) applicable on 2026-03-20.
