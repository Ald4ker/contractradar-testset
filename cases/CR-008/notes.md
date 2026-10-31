# CR-008 - Contract change notice correctly below threshold (negative control)

A +6.0% uplift with no term change, correctly made under section 74(1)(c). Money is printed as £4 200 000. No high-severity flag should be raised; this catches over-eager rule engines.

## Hazards

- **negative_control**: Nothing is wrong with this document; a rule engine should raise no high-severity flag.
- **money_spaced_format**: Money printed with spaces as thousands separators (£4 200 000).
- **date_uk_format**: Dates printed as DD/MM/YYYY.
- **percent_not_printed**: The modification percentage is not printed and must be computed from the values.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £4,200,000 is at or above the services threshold £207,720 (inc VAT) applicable on 2026-06-02.
