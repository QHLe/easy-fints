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

### `POST /submit-tan`

Request body:

```json
{
  "session_id": "<uuid>",
  "tan": "123456"
}
```

Responses:

- `200`: original operation resumed successfully
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

Use `session_id` with `/submit-tan` to continue the original operation.

Sessions are:

- stored in memory
- local to one process
- expired after `300` seconds

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

## Notes

- Request `config` is merged with env-loaded defaults.
- `account_filter` is supported by `/balance` and `/transactions`, but not by `/accounts`.
- API request `config` does not accept `product_id`, `product_name`, or `product_version`; keep those in env/default config only.
- API request `config` does not accept `tan_mechanism` or `tan_mechanism_before_bootstrap`; if needed, keep those in env/default config only.
- For multi-worker or multi-container deployments, replace the in-memory TAN session store with a shared store.
- Protect the API with authentication and TLS before exposing it outside a trusted environment.
