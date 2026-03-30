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
FINTS_BLZ=<bank_code>
FINTS_USER=<user_id>
FINTS_PIN=<pin>
FINTS_SERVER=<bank_fints_url>
FINTS_CUSTOMER_ID=<optional>
FINTS_TAN_MECHANISM=
FINTS_TAN_MECHANISM_BEFORE_BOOTSTRAP=0
PYFIN_API_BASE_URL=http://127.0.0.1:8000
```

Start the API:

```bash
uvicorn src.fastapi_app:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs will be available at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

Important:

- use `src.fastapi_app:app`
- do not use `src/fastapi_app:app`

## Configuration

The app loads `.env` from the repository root by default.

You can point to another env file with:

```bash
FINTS_ENV_FILE=.env.commerzbank uvicorn src.fastapi_app:app --reload
```

Common config values used by the API:

- `FINTS_PRODUCT_ID`: required if not provided in request `config`
- `FINTS_PRODUCT_NAME`: optional
- `FINTS_PRODUCT_VERSION`: optional
- `FINTS_BLZ`: useful for helper scripts
- `FINTS_USER`: useful for helper scripts
- `FINTS_PIN`: useful for helper scripts
- `FINTS_SERVER`: useful for helper scripts
- `FINTS_CUSTOMER_ID`: optional
- `FINTS_TAN_MECHANISM`: optional forced TAN mechanism
- `FINTS_TAN_MECHANISM_BEFORE_BOOTSTRAP`: optional boolean-like flag (`1`, `true`, `yes`, `on`)
- `PYFIN_SESSION_TTL`: TAN session lifetime in seconds, default `300`
- `PYFIN_API_BASE_URL`: base URL used by the helper scripts

## API Overview

The API exposes four endpoints:

- `GET /health`
- `POST /accounts`
- `POST /balance`
- `POST /transactions`
- `POST /submit-tan`

All operation endpoints accept a JSON body with a `config` object. The `config` values are merged with env defaults.

Supported `config` fields:

- `bank`
- `user`
- `pin`
- `server`
- `product_id`
- `product_name`
- `product_version`
- `customer_id`
- `tan_medium`
- `system_id`
- `tan_mechanism`
- `tan_mechanism_before_bootstrap`

Optional top-level request fields:

- `account_filter`
- `days`
- `include_transaction_count_days`
- `env_path`

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
      "server": "https://bank.fints.server",
      "product_id": "<product_id>",
      "tan_mechanism": "942",
      "tan_mechanism_before_bootstrap": true
    },
    "account_filter": null
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
      "server": "https://bank.fints.server",
      "product_id": "<product_id>"
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
      "server": "https://bank.fints.server",
      "product_id": "<product_id>"
    },
    "days": 30
  }'
```

## TAN Flow

If a bank operation needs TAN confirmation, the endpoint returns HTTP `409`:

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

Submit the TAN with:

```bash
curl -sS -X POST http://127.0.0.1:8000/submit-tan \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<uuid>","tan":"123456"}'
```

Possible `/submit-tan` responses:

- `200`: original operation resumed successfully
- `409`: another TAN challenge is required
- `404`: session was not found or expired
- `502`: FinTS/provider error while resuming

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
You can explicitly enable challenge image saving with `PYFIN_SAVE_CHALLENGE_IMAGES=1`.

## Development

Important files:

- [`src/fastapi_app.py`](src/fastapi_app.py): API routes and TAN session handling
- [`src/client.py`](src/client.py): main FinTS client wrapper
- [`src/helpers.py`](src/helpers.py): env loading, bootstrap helpers, runtime patches
- [`src/models.py`](src/models.py): serialized response/config models
- [`docs/API.md`](docs/API.md): API reference

Basic verification:

```bash
python -m compileall src api_tan_test_helper.py test_accounts_api_tan.py test_balance_api_tan.py test_transactions_api_tan.py
```

## Security Notes

- Do not expose this API publicly without authentication and TLS.
- Do not log or persist PINs and TANs outside controlled development needs.
- `/submit-tan` uses in-memory session state and is suitable for a single-process deployment only.
- For production, use a shared session store and carefully control worker ownership of FinTS dialogs.
