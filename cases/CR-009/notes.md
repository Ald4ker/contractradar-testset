# CR-009 - Deed of variation extending an expired contract with no change notice

A deed of variation dated 15 May 2026 extends a contract that expired on 31 March 2026, adds 20% to the value, and the decision record states no contract change notice was published. Key values are in prose recitals. Expect three high flags.

## Hazards

- **retrospective_extension**: The variation is dated after the contract had already expired.
- **no_ccn_published**: The document states that no contract change notice was published before the modification.
- **wrong_legal_ground**: The authority cites a modification ground that does not cover the change made.
- **values_in_prose**: Key values are embedded in running text rather than in a table.
- **date_ordinal**: Dates printed as 3rd March 2026.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £1,550,000 is at or above the services threshold £214,904 (inc VAT) applicable on 2021-02-11.
- `PA23-s74-substantial-term` (high): Term change +12 months is +20.0% of the 60-month maximum term: a substantial modification under s.74(3)(a) with no Schedule 8 ground.
- `PA23-s75-ccn-required-not-published` (high): Value change +20.0% / term change +20.0% exceeds the s.75(2) exemption but no contract change notice was published.
- `AUDIT-retrospective-extension` (high): Modification dated 2026-05-15 but the contract expired on 2026-03-31: a retrospective extension of an expired contract.
