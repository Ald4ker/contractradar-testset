# CR-012 - Direct award notice with values embedded in prose

Section 41 direct award (urgency). There is no key/value table: authority, supplier, value, dates and CPV codes are all inside paragraphs. No standstill applies.

## Hazards

- **direct_award**: Direct award under section 41 with a stated justification.
- **values_in_prose**: Key values are embedded in running text rather than in a table.
- **date_iso_format**: Dates printed as YYYY-MM-DD.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £420,000 is at or above the services threshold £207,720 (inc VAT) applicable on 2026-01-22.
- `AUDIT-direct-award-above-threshold` (medium): Direct award of an above-threshold contract: a s.41 justification must be recorded in the notice.
