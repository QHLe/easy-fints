# API Reference

This API is served by the ASGI app `easy_fints.fastapi_app:app`.

Run locally with:

```bash
uvicorn easy_fints.fastapi_app:app --reload
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

### `POST /bank-info`

Request body:

```json
{
  "config": {
    "bank": "<BLZ>",
    "server": "https://...",
    "product_id": "YOUR_PRODUCT_ID"
  }
}
```

Notes:

- `bank` and `server` are required
- `product_id` may come from request `config` or server environment
- the endpoint uses an anonymous FinTS dialog, so no user or PIN is required

Responses:

- `200`: `BankInfo`
- `400`: invalid or incomplete config
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
  "endtoend_id": "INV-123",
  "instant_payment": false,
  "execution_date": "2026-04-10"
}
```

Notes:

- `source_account` is matched against the local SEPA account list, typically by IBAN
- `account_name` is the sender account holder name required by `python-fints.simple_sepa_transfer(...)`
- `recipient_bic` is optional for domestic/SEPA cases where the bank accepts IBAN-only routing
- `instant_payment` defaults to `false`; set it to `true` to request an SCT Inst / SEPA instant payment
- `execution_date` is optional; if set, the wrapper builds a dated SEPA transfer request for that `YYYY-MM-DD` date
- `instant_payment` and `execution_date` cannot be combined
- `amount` must be a EUR amount between `0.01` and `999999999.99` with at most 2 decimal places
- `purpose` must be at most 140 characters and use a conservative SEPA-safe character set: letters, digits, spaces, and `/ - ? : ( ) . , ' +`
- name-to-IBAN matching is not validated locally; that remains bank-/channel-dependent
- the bank must support instant payments for the selected account; otherwise the request may fail with a FinTS/provider error
- non-final transfer responses and the final `200` transfer response include a structured `transfer_overview` payload with the payment details

Responses:

- `200`: `TransferResponse`
- `400`: invalid or incomplete config
- `409`: TAN or VoP confirmation required
- `422`: unsupported transfer product
- `502`: FinTS/provider error

### `GET /sessions/{session_id}`

Inspect an active confirmation session without changing it.

Responses:

- `200`: session metadata including state, next action, expiry, optional challenge/VoP details, and `transfer_overview` for transfer sessions
- `404`: session not found or expired

### `DELETE /sessions/{session_id}`

Cancel an active confirmation session.

Responses:

- `200`: session cancelled and the stored FinTS client closed
- `404`: session not found or expired

### `POST /transfer/retry-with-name`

Retry a transfer after a payee-verification mismatch by reusing the current transfer session with a corrected recipient name when possible.

Request body:

```json
{
  "session_id": "<uuid>",
  "recipient_name": "Corrected Recipient Name"
}
```

Notes:

- the referenced session must belong to a transfer and currently be in `awaiting_vop`
- the server keeps the same `session_id` and tries to reuse the existing FinTS client/dialog
- the bank may still treat the retried transfer as a new payment order
- this reduces request reconstruction effort, but does not guarantee fewer TAN/App confirmations because the bank may treat it as a new payment order

Responses:

- `200`: `TransferResponse`
- `400`: invalid request or session state
- `404`: session not found
- `409`: TAN or VoP confirmation required for the retried transfer flow
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
  "tan": "123456",
  "approve_vop": false
}
```

Notes:

- `tan` is used when the current session state is `awaiting_tan`
- for decoupled/app-based approval, `tan` may be omitted or empty and the same endpoint can be called again after app confirmation
- `approve_vop` must be set to `true` when the current session state is `awaiting_vop`

Responses:

- `200`: original operation resumed successfully
- `202`: approval is still pending in the banking app
- `400`: missing `session_id`
- `404`: session not found or expired
- `409`: another TAN or VoP challenge is required
- `422`: unsupported transfer product
- `500`: unknown stored operation
- `502`: FinTS/provider error

For transfer sessions, the `409`/`202` confirmation responses and the final `200` transfer response can include the same structured `transfer_overview` payload:

```json
{
  "source_account_label": "DE...",
  "recipient_name": "Acme GmbH",
  "recipient_iban": "DE...",
  "recipient_bic": null,
  "amount": "12.34",
  "currency": "EUR",
  "purpose": "Invoice 123",
  "endtoend_id": "INV-123",
  "instant_payment": false,
  "execution_date": "2026-04-10"
}
```

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

If the bank requires explicit payee-verification approval, the API responds with HTTP `409`:

```json
{
  "error": "vop_required",
  "session_id": "<uuid>",
  "state": "awaiting_vop",
  "next_action": "approve_vop",
  "operation": "transfer",
  "message": "Bank requires explicit approval of the payee verification result before execution.",
  "challenge": null,
  "vop": {
    "result": "RCVC",
    "message": "Bank requires explicit approval of the payee verification result before execution.",
    "close_match_name": null,
    "other_identification": null,
    "na_reason": null,
    "raw_repr": "..."
  }
}
```

Continue that flow with:

```json
{
  "session_id": "<uuid>",
  "approve_vop": true
}
```

Sessions are:

- stored as live FinTS dialog state in process-local memory
- expired after `300` seconds by default

The session TTL can be configured via `FINTS_SESSION_TTL_SECONDS`.

Relevant runtime env vars:

- `FINTS_SESSION_TTL_SECONDS`

Session state values currently used by the API:

- `awaiting_tan`: call `/confirm` with a TAN
- `awaiting_decoupled`: confirm in the banking app and call `/confirm` again
- `awaiting_vop`: inspect the `vop` payload and call `/confirm` with `approve_vop: true`, or restart with `/transfer/retry-with-name`
- `running` and `resuming`: transient internal states while the server continues the FinTS flow
- `completed` and `failed`: terminal states; the session is then removed

### `SessionInfoResponse`

```json
{
  "session_id": "<uuid>",
  "operation": "transfer",
  "state": "awaiting_decoupled",
  "next_action": "confirm",
  "message": "TAN confirmation required",
  "created_at": "2026-04-03T12:00:00.000000",
  "updated_at": "2026-04-03T12:01:30.000000",
  "expires_at": "2026-04-03T12:06:30.000000",
  "expires_in_seconds": 299,
  "challenge": {
    "message": "Please confirm in your banking app.",
    "decoupled": true,
    "has_html": false,
    "has_raw": false,
    "has_matrix": false,
    "has_hhduc": false,
    "image_mime_type": null,
    "image_base64": null
  },
  "vop": null,
  "transfer_overview": {
    "source_account_label": "DE...",
    "recipient_name": "Acme GmbH",
    "recipient_iban": "DE...",
    "recipient_bic": null,
    "amount": "12.34",
    "currency": "EUR",
    "purpose": "Invoice 123",
    "endtoend_id": "INV-123",
    "instant_payment": false,
    "execution_date": null
  }
}
```

### `UnsupportedTransferProductResponse`

```json
{
  "error": "unsupported_transfer_product",
  "operation": "transfer",
  "product": "instant_payment",
  "message": "No supported HKIPZ version found. I support (1,), bank supports ()",
  "execution_date": null,
  "instant_payment": true
}
```

## Data Shapes

### `AccountSummary`

```json
{
  "label": "Max Mustermann - Girokonto",
  "iban": "DE...",
  "bic": "...",
  "bank_code": "...",
  "account_number": "...",
  "subaccount_number": null,
  "owner_name": "Max Mustermann",
  "bank_identifier": "...",
  "product_name": "Girokonto",
  "account_type": "Girokonto / Kontokorrentkonto",
  "account_type_code": "1",
  "currency": "EUR",
  "balance": "123.45",
  "transaction_count": 12,
  "raw_repr": "..."
}
```

### `BankInfo`

```json
{
  "bank_code": "12345678",
  "server": "https://bank.example/fints",
  "bank_name": "Testbank",
  "supported_operations": {
    "GET_SEPA_ACCOUNTS": true
  },
  "supported_formats": {
    "SEPA_TRANSFER_SINGLE": [
      "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
    ]
  },
  "supported_sepa_formats": [
    "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
  ],
  "tan_methods": {
    "current": null,
    "current_name": null,
    "methods": [
      {
        "code": "942",
        "name": "pushTAN",
        "security_function": "942",
        "identifier": "push"
      }
    ],
    "media": null
  }
}
```

### `TransactionRecord`

```json
{
  "account_label": "Max Mustermann - Girokonto",
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
    "label": "Max Mustermann - Girokonto",
    "iban": "DE...",
    "bic": "...",
    "bank_code": "...",
    "account_number": "...",
    "subaccount_number": null,
    "owner_name": "Max Mustermann",
    "bank_identifier": "...",
    "product_name": "Girokonto",
    "account_type": "Girokonto / Kontokorrentkonto",
    "account_type_code": "1",
    "currency": "EUR",
    "balance": null,
    "transaction_count": 2,
    "raw_repr": "..."
  },
  "transactions": [
    {
      "account_label": "Max Mustermann - Girokonto",
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
  "transfer_overview": {
    "source_account_label": "DE...",
    "recipient_name": "Acme GmbH",
    "recipient_iban": "DE...",
    "recipient_bic": "ABCDEFGHXXX",
    "amount": "12.34",
    "currency": "EUR",
    "purpose": "Invoice 123",
    "endtoend_id": "INV-123",
    "instant_payment": false,
    "execution_date": "2026-04-10"
  },
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
