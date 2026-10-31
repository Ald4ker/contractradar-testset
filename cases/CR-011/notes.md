# CR-011 - Works change notice exceeding the 50% unforeseeable-circumstances cap

A +60% increase under Schedule 8 paragraph 3, which caps increases at 50%. The contract is over £5m, so section 77 publication of the modified contract applies. Money as 6,100,000.00 GBP; dates ISO.

## Hazards

- **percent_not_printed**: The modification percentage is not printed and must be computed from the values.
- **money_gbp_suffix**: Money printed as 1,234.00 GBP.
- **date_iso_format**: Dates printed as YYYY-MM-DD.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £6,100,000 is at or above the works threshold £5,193,000 (inc VAT) applicable on 2026-06-18.
- `PA23-sch8-para3-cap-50pc` (high): Increase of 60.0% exceeds the 50% cap in Schedule 8 para 3.
- `PA23-s77-publish-modified-contract` (info): Qualifying modification to a contract over £5m: publish a copy of the contract as modified within 90 days (s.77).
