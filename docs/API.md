# API Reference

This API is served by the ASGI app `src.fastapi_app:app`.

Run locally with:

```bash
uvicorn src.fastapi_app:app --reload
```

Base URL:

```text
http://<host>:<port>
```

All operation endpoints accept a `config` object. Request `config` values are merged with env defaults.

## Endpoints

### `GET /health`

Response:

```json
{"status":"ok"}
```

### `POST /accounts`

Request body:

```json
{
  "config": {
    "bank": "<BLZ>",
    "user": "<user>",
    "pin": "<pin>",
    "server": "https://..."
  }
}
```

Responses:

- `200`: list of `AccountSummary`
- `400`: invalid or incomplete config
- `409`: TAN required
- `502`: FinTS/provider error

### `POST /balance`

Request body:

```json
{
  "config": {
    "bank": "<BLZ>",
    "user": "<user>",
    "pin": "<pin>",
    "server": "https://..."
  },
  "account_filter": null,
  "include_transaction_count_days": 14
}
```

Responses:

- `200`: list of `AccountSummary` with `balance`
- `400`: invalid or incomplete config
- `409`: TAN required
- `502`: FinTS/provider error

### `POST /transactions`

Request body:

```json
{
  "config": {
    "bank": "<BLZ>",
    "user": "<user>",
    "pin": "<pin>",
    "server": "https://..."
  },
  "account_filter": null,
  "date_from": "2026-03-01",
  "date_to": "2026-03-31"
}
```

`/transactions` accepts either:

- `days` for a rolling window ending today
- `date_from` and optional `date_to` in `YYYY-MM-DD` format for an explicit window

Responses:

- `200`: list of `AccountTransactions`
- `400`: invalid or incomplete config
- `409`: TAN required
- `502`: FinTS/provider error

### `POST /transfer`

Request body:

```json
{
  "config": {
    "bank": "<BLZ>",
    "user": "<user>",
    "pin": "<pin>",
    "server": "https://..."
  },
  "source_account": "DE...",
  "account_name": "Max Mustermann",
  "recipient_name": "Acme GmbH",
  "recipient_iban": "DE...",
  "recipient_bic": "ABCDEFGHXXX",
  "amount": "12.34",
  "purpose": "Invoice 123",
  "endtoend_id": "INV-123"
}
```

Notes:

- `source_account` is matched against the local SEPA account list, typically by IBAN
- `account_name` is the sender account holder name required by `python-fints.simple_sepa_transfer(...)`
- `recipient_bic` is optional for domestic/SEPA cases where the bank accepts IBAN-only routing
- `amount` must be a EUR amount between `0.01` and `999999999.99` with at most 2 decimal places
- `purpose` must be at most 140 characters and use a conservative SEPA-safe character set: letters, digits, spaces, and `/ - ? : ( ) . , ' +`
- name-to-IBAN matching is not validated locally; that remains bank-/channel-dependent

Responses:

- `200`: `TransferResponse`
- `400`: invalid or incomplete config
- `409`: TAN required
- `502`: FinTS/provider error

### `POST /transfer/retry-with-name`

Retry a transfer after a payee-verification mismatch by starting a new transfer flow with a corrected recipient name.

Request body:

```json
{
  "session_id": "<uuid>",
  "recipient_name": "Corrected Recipient Name"
}
```

Notes:

- the referenced session must belong to a transfer and currently be in `awaiting_vop`
- the old session is closed and replaced by a new transfer flow
- the response may therefore return a new `session_id`
- this reduces request reconstruction effort, but does not guarantee fewer TAN/App confirmations because the bank may treat it as a new payment order

Responses:

- `200`: `TransferResponse`
- `400`: invalid request or session state
- `404`: session not found
- `409`: TAN or VoP confirmation required for the new transfer flow
- `502`: FinTS/provider error

Example validation error:

```json
{
  "error": "validation_error",
  "operation": "transfer",
  "field": "purpose",
  "message": "purpose contains unsupported character '€'; allowed are letters, digits, spaces, and / - ? : ( ) . , ' +"
}
```

### `POST /confirm`

Request body:

```json
{
  "session_id": "<uuid>",
  "tan": "123456"
}
```

For decoupled/app-based approval, `tan` may be omitted or empty and the same endpoint can be called again after app confirmation.

Responses:

- `200`: original operation resumed successfully
- `202`: approval is still pending in the banking app
- `400`: missing `session_id`
- `404`: session not found or expired
- `409`: another TAN challenge is required
- `500`: unknown stored operation
- `502`: FinTS/provider error

## TAN Flow

When an operation requires a TAN, the API responds with HTTP `409`:

```json
{
  "error": "tan_required",
  "session_id": "<uuid>",
  "state": "awaiting_tan",
  "next_action": "provide_tan",
  "operation": "transactions",
  "message": "TAN confirmation required",
  "challenge": {
    "message": "...",
    "decoupled": false,
    "has_html": false,
    "has_raw": false,
    "has_matrix": false,
    "has_hhduc": false,
    "image_mime_type": null,
    "image_base64": null
  }
}
```

Use `session_id` with `/confirm` to continue the original operation.

Sessions are:

- stored in memory
- local to one process
- expired after `300` seconds

Session state values currently used by the API:

- `awaiting_tan`: call `/confirm` with a TAN
- `awaiting_decoupled`: confirm in the banking app and call `/confirm` again
- `running` and `resuming`: transient internal states while the server continues the FinTS flow
- `completed` and `failed`: terminal states; the session is then removed

## Data Shapes

### `AccountSummary`

```json
{
  "label": "DE...",
  "iban": "DE...",
  "bic": "...",
  "bank_code": "...",
  "account_number": "...",
  "subaccount_number": null,
  "bank_identifier": "...",
  "balance": "123.45",
  "transaction_count": 12,
  "raw_repr": "..."
}
```

### `TransactionRecord`

```json
{
  "account_label": "DE...",
  "tx_index": 1,
  "booking_date": "2026-03-01",
  "value_date": "2026-03-01",
  "amount": "-50.00",
  "currency": "EUR",
  "counterparty_name": "Acme GmbH",
  "counterparty_iban": "DE...",
  "purpose": "Invoice 123",
  "raw": "..."
}
```

### `AccountTransactions`

```json
{
  "account": {
    "label": "DE...",
    "iban": "DE...",
    "bic": "...",
    "bank_code": "...",
    "account_number": "...",
    "subaccount_number": null,
    "bank_identifier": "...",
    "balance": null,
    "transaction_count": 2,
    "raw_repr": "..."
  },
  "transactions": [
    {
      "account_label": "DE...",
      "tx_index": 1,
      "booking_date": "2026-03-01",
      "value_date": "2026-03-01",
      "amount": "-50.00",
      "currency": "EUR",
      "counterparty_name": "Acme GmbH",
      "counterparty_iban": "DE...",
      "purpose": "Invoice 123",
      "raw": "..."
    }
  ]
}
```

### `TransferResponse`

```json
{
  "status": "SUCCESS",
  "success": true,
  "reference": null,
  "amount": "12.34",
  "currency": "EUR",
  "source_account_label": "DE...",
  "recipient_name": "Acme GmbH",
  "recipient_iban": "DE...",
  "recipient_bic": "ABCDEFGHXXX",
  "purpose": "Invoice 123",
  "endtoend_id": "INV-123",
  "bank_responses": [
    {
      "code": "0010",
      "message": "Message accepted",
      "reference": null
    }
  ]
}
```

### `ValidationErrorResponse`

```json
{
  "error": "validation_error",
  "operation": "transfer",
  "field": "amount",
  "message": "amount must have at most 2 decimal places"
}
```

## Notes

- Request `config` is merged with env-loaded defaults.
- `account_filter` is supported by `/balance` and `/transactions`, but not by `/accounts`.
- API request `config` does not accept `product_id`, `product_name`, or `product_version`; keep those in env/default config only.
- API request `config` does not accept `tan_mechanism` or `tan_mechanism_before_bootstrap`; if needed, keep those in env/default config only.
- For multi-worker or multi-container deployments, replace the in-memory TAN session store with a shared store.
- Protect the API with authentication and TLS before exposing it outside a trusted environment.
