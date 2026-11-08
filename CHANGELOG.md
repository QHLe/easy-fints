# Changelog

## 1.5.2 - 2026-11-08

- Correct CAMT counterparty selection for credits, debits, and reversals.
- Normalize CAMT credit and debit amount signs and handle zero-valued CAMT entries.
- Preserve MT940 applicant IBANs, reversal signs, lowercase marks, and plain-text remittance details.
- Require `mt-940>=5.1` to enable the parser compatibility options used by the FinTS adapter.
- Document upstream CAMT parsing limitations in [VERIFICATION.md](VERIFICATION.md).
