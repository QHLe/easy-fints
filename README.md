# python-fints REST Wrapper

Small FastAPI wrapper around `python-fints` for:

- listing SEPA accounts
- reading balances
- reading transactions
- handling TAN challenges over HTTP

The API entrypoint is [`src/fastapi_app.py`](src/fastapi_app.py) and should be started with the module path `src.fastapi_app:app`.

## Quick Start

Prerequisites:

- Python 3.11+
- a bank account with FinTS/HBCI access
- valid FinTS credentials and bank server URL

Create the environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a minimal `.env`:

```bash
FINTS_PRODUCT_ID=HBCI4Java
FINTS_PRODUCT_NAME=HBCI4Java
FINTS_PRODUCT_VERSION=3.0
```

Start the API:

```bash
uvicorn src.fastapi_app:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs will be available at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`


## API Overview

The API exposes these main endpoints:

- `GET /health`
- `POST /accounts`
- `POST /balance`
- `POST /transactions`
- `POST /transfer`
- `POST /transfer/retry-with-name`
- `POST /confirm`

All operation endpoints accept a JSON body with a `config` object. The `config` values are merged with env defaults.

Supported `config` fields:

- `bank`
- `user`
- `pin`
- `server`

Optional top-level request fields:

- `days`
- `date_from`
- `date_to`
- `include_transaction_count_days`

Transfer-specific top-level request fields:

- `source_account`
- `account_name`
- `recipient_name`
- `recipient_iban`
- `recipient_bic`
- `amount`
- `purpose`
- `endtoend_id`

`account_filter` is supported by `/balance` and `/transactions`, but not by `/accounts`.

## Endpoint Examples

### Health

```bash
curl -sS http://127.0.0.1:8000/health
```

Response:

```json
{"status":"ok"}
```

### Accounts

```bash
curl -sS -X POST http://127.0.0.1:8000/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "bank": "<BLZ>",
      "user": "<user>",
      "pin": "<pin>",
      "server": "https://bank.fints.server"
    }
  }'
```

### Balance

```bash
curl -sS -X POST http://127.0.0.1:8000/balance \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "bank": "<BLZ>",
      "user": "<user>",
      "pin": "<pin>",
      "server": "https://bank.fints.server"
    },
    "include_transaction_count_days": 14
  }'
```

### Transactions

```bash
curl -sS -X POST http://127.0.0.1:8000/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "bank": "<BLZ>",
      "user": "<user>",
      "pin": "<pin>",
      "server": "https://bank.fints.server"
    },
    "account_filter": null,
    "date_from": "2026-03-01",
    "date_to": "2026-03-31"
  }'
```

For `/transactions`, you can use either:

- `account_filter` to restrict the response to one account
- `days` for a rolling window ending today
- `date_from` and optional `date_to` in `YYYY-MM-DD` format for an explicit window

### Transfer

```bash
curl -sS -X POST http://127.0.0.1:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "bank": "<BLZ>",
      "user": "<user>",
      "pin": "<pin>",
      "server": "https://bank.fints.server"
    },
    "source_account": "DE...",
    "account_name": "Max Mustermann",
    "recipient_name": "Acme GmbH",
    "recipient_iban": "DE...",
    "recipient_bic": "ABCDEFGHXXX",
    "amount": "12.34",
    "purpose": "Invoice 123",
    "endtoend_id": "INV-123"
  }'
```

For `/transfer` in the current V1 scope:

- only a single immediate SEPA credit transfer is supported
- `account_name` is required because `python-fints.simple_sepa_transfer(...)` expects the sender account holder name explicitly
- `source_account` should usually be the source IBAN
- `amount` must be between `0.01` and `999999999.99` with at most 2 decimal places
- `purpose` currently accepts a conservative SEPA-safe character set: letters, digits, spaces, and `/ - ? : ( ) . , ' +`
- recipient name and IBAN are not locally matched against each other; any real payee verification is bank-/channel-dependent

If a payee-verification step returns a close/no match, you can retry with a corrected recipient name via `POST /transfer/retry-with-name`. The API keeps the same `session_id` and tries to reuse the current FinTS client/dialog when possible.

A diagram of the full transfer flow is available in [`POST_transfer_workflow.md`](POST_transfer_workflow.md).

## TAN Flow

If a bank operation needs TAN confirmation, the endpoint returns HTTP `409`:

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

Continue the flow with:

```bash
curl -sS -X POST http://127.0.0.1:8000/confirm \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<uuid>","tan":"123456"}'
```

If the current state is `awaiting_vop`, continue with:

```bash
curl -sS -X POST http://127.0.0.1:8000/confirm \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<uuid>","approve_vop":true}'
```

Possible `/confirm` responses:

- `200`: original operation resumed successfully
- `202`: decoupled/app confirmation is still pending
- `409`: another TAN or VoP challenge is required
- `404`: session was not found or expired
- `502`: FinTS/provider error while resuming

If `state` is `awaiting_decoupled`, confirm the operation in the banking app and call `/confirm` again. If `state` is `awaiting_vop`, inspect the `vop` object in the response and either approve it with `approve_vop: true` or restart the transfer with `/transfer/retry-with-name`.

Sessions are stored in memory only. They are not shared across multiple workers or containers.

## Response Shapes

### AccountSummary

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

### AccountTransactions

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

## Helper Scripts

The repository includes small helper scripts for manual TAN-based testing:

- [`test_accounts_api_tan.py`](test_accounts_api_tan.py)
- [`test_balance_api_tan.py`](test_balance_api_tan.py)
- [`test_transactions_api_tan.py`](test_transactions_api_tan.py)
- [`test_transfer_api_tan.py`](test_transfer_api_tan.py)

They use [`api_tan_test_helper.py`](api_tan_test_helper.py), read credentials from `.env`, call the API, and prompt for TAN input when required.

Example:

```bash
python test_transactions_api_tan.py
```

## Runtime Notes

The integration applies a few python-fints compatibility/runtime patches during startup from the normal application code. This includes:

- safer TAN challenge handling for some banks
- bootstrap handling around TAN mechanisms
- defensive balance conversion handling for problematic responses

That behavior is now integrated into the main codebase and does not require a separate patch file.

Sensitive logging defaults:

- raw FinTS message logging is disabled by default
- challenge images are not written to disk by default
- operation logs under `logs/` are metadata-focused and avoid full account/transaction payloads

You can explicitly enable raw message logging with `FINTS_ENABLE_RAW_MESSAGE_LOG=1`.
## Development

Important files:

- [`src/fastapi_app.py`](src/fastapi_app.py): API routes and TAN session handling
- [`src/client.py`](src/client.py): main FinTS client wrapper
- [`src/helpers.py`](src/helpers.py): env loading, bootstrap helpers, runtime patches
- [`src/models.py`](src/models.py): serialized response/config models
- [`docs/API.md`](docs/API.md): API reference

Basic verification:

```bash
python -m compileall src api_tan_test_helper.py test_accounts_api_tan.py test_balance_api_tan.py test_transactions_api_tan.py test_single_account_api_tan.py test_transfer_api_tan.py
```

## Security Notes

- Do not expose this API publicly without authentication and TLS.
- Do not log or persist PINs and TANs outside controlled development needs.
- `/confirm` uses in-memory session state and is suitable for a single-process deployment only.
- For production, use a shared session store and carefully control worker ownership of FinTS dialogs.
