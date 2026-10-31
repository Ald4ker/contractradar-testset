# CR-005 - Scanned contract particulars (image-only PDF)

The contract front matter is an image-only PDF with slight skew and speckle, as if photocopied. pdftotext returns nothing. Supplier is printed as 'Halbrook Leisure Operations Ltd (trading as Halbrook Active)'. Only two KPIs are set on a £9.75m contract.

## Hazards

- **scanned_no_text_layer**: Image-only PDF (simulated photocopy): no text layer, slight skew and noise. Needs OCR or vision.
- **trading_as_name**: Supplier printed with a trading name in brackets; the legal name is the answer.
- **kpi_shortfall**: Contract over £5m with fewer than three KPIs.

## Expected flags

- `PA23-threshold-in-scope` (info): Value £9,750,000 is at or above the services threshold £207,720 (inc VAT) applicable on 2026-03-27.
- `PA23-s52-kpi-min3` (high): Value £9,750,000 exceeds £5m but only 2 KPI(s) set; s.52 requires at least three unless inappropriate.
