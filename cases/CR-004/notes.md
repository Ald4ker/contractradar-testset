# CR-004 - Contract change notice relying on the wrong ground

The notice cites section 74(1)(c) (below-threshold) for a +14.4% value change and a +33% term extension. The percentage is not printed. A rule engine should raise PA23-s74-exceeds-below-threshold and PA23-s74-substantial-term.

## Hazards

- **wrong_legal_ground**: The authority cites a modification ground that does not cover the change made.
- **percent_not_printed**: The modification percentage is not printed and must be computed from the values.
- **date_uk_format**: Dates printed as DD/MM/YYYY.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £1,800,000 is at or above the services threshold £207,720 (inc VAT) applicable on 2026-05-04.
- `PA23-s74-exceeds-below-threshold` (high): Value change +14.4% exceeds the 10% below-threshold limit for services in s.74(4).
- `PA23-s74-substantial-term` (high): Term change +12 months is +33.3% of the 36-month maximum term: a substantial modification under s.74(3)(a) with no Schedule 8 ground.
