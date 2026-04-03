# python-fints REST Wrapper

Small FastAPI wrapper around `python-fints`.

PyPI package:

- `fints-rest-wrapper`

It currently supports:

- account listing
- balances
- transactions
- SEPA transfers
- TAN / decoupled confirmation over HTTP
- payee verification (`VoP`) continuation

The ASGI entrypoint is [fints_rest_wrapper/fastapi_app.py](/home/bomay/git/python-fints-REST-wrapper/fints_rest_wrapper/fastapi_app.py).

## Quick Start

Requirements:

- Python 3.11+
- a bank account with FinTS/HBCI access
- valid FinTS credentials and server URL

Install from PyPI:

```bash
pip install fints-rest-wrapper
```

Start the API server after installation:

```bash
fints-rest-server start
fints-rest-server status
fints-rest-server stop
```

Configuration priority for the CLI:

- explicit CLI flags like `--host` or `--port`
- values loaded from `--env-file`
- process environment variables
- built-in defaults

For local development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Minimal `.env`:

```env
FINTS_PRODUCT_ID=YourProductID
FINTS_PRODUCT_NAME=YourProductName
FINTS_PRODUCT_VERSION=YourProductVersion
FINTS_SESSION_TTL_SECONDS=300
```

A FinTS product ID can be requested via the official registration page:

- `https://www.fints.org/de/hersteller/produktregistrierung`

Start the API:

```bash
uvicorn fints_rest_wrapper.fastapi_app:app --reload --host 0.0.0.0 --port 8000
```

Installed CLI defaults:

- server host: `0.0.0.0`
- server port: `8000`
- PID file: `.fints-rest-server.pid`
- log file: `.fints-rest-server.log`

CLI examples:

```bash
fints-rest-server start --host 127.0.0.1 --port 9686
fints-rest-server start --env-file /etc/fints-rest-wrapper.env
fints-rest-server stop
```

OpenAPI:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

## Main Endpoints

- `GET /health`
- `POST /accounts`
- `POST /balance`
- `POST /transactions`
- `POST /transfer`
- `POST /transfer/retry-with-name`
- `POST /confirm`
- `GET /sessions/{session_id}`
- `DELETE /sessions/{session_id}`

All operation endpoints accept a JSON body with a `config` object. Request values override env defaults.

Supported `config` fields:

- `bank`
- `user`
- `pin`
- `server`

## Transfer Support

`POST /transfer` supports a single SEPA credit transfer per request.

Transfer request fields:

- `source_account`
- `account_name`
- `recipient_name`
- `recipient_iban`
- `recipient_bic`
- `amount`
- `purpose`
- `endtoend_id`
- `instant_payment`
- `execution_date`

Current behavior:

- `account_name` is required because `python-fints.simple_sepa_transfer(...)` expects the sender name explicitly
- `instant_payment=true` requests SCT Inst when the bank supports it
- `execution_date=YYYY-MM-DD` requests a dated transfer
- `instant_payment` and `execution_date` cannot be combined
- unsupported transfer products return HTTP `422` with `error="unsupported_transfer_product"`
- transfer challenge responses and final transfer responses include `transfer_overview`

## Confirmation Flow

The API uses a session-based confirmation flow.

Typical sequence:

1. `POST /transfer` or another operation endpoint
2. either immediate `200`, or a challenge response like `409 tan_required`
3. continue with `POST /confirm`
4. repeat `/confirm` for decoupled app confirmation if needed
5. for payee verification, call `/confirm` with `approve_vop=true`
6. if the recipient name should be corrected after VoP, call `POST /transfer/retry-with-name`

Session helpers:

- `GET /sessions/{session_id}` inspects the current state
- `DELETE /sessions/{session_id}` cancels the active session

Session states currently used:

- `awaiting_tan`
- `awaiting_decoupled`
- `awaiting_vop`
- `running`
- `resuming`

Sessions are:

- stored in memory only
- process-local
- expired after an inactivity TTL

The TTL defaults to `300` seconds and can be changed with `FINTS_SESSION_TTL_SECONDS`.

## Manual Test Helpers

The repository includes small scripts for manual API testing:

- [test_accounts_api_tan.py](/home/bomay/git/python-fints-REST-wrapper/test_accounts_api_tan.py)
- [test_balance_api_tan.py](/home/bomay/git/python-fints-REST-wrapper/test_balance_api_tan.py)
- [test_transactions_api_tan.py](/home/bomay/git/python-fints-REST-wrapper/test_transactions_api_tan.py)
- [test_transfer_api_tan.py](/home/bomay/git/python-fints-REST-wrapper/test_transfer_api_tan.py)

They use [api_tan_test_helper.py](/home/bomay/git/python-fints-REST-wrapper/api_tan_test_helper.py) and read credentials from `.env`.

Optional helper-script env vars for manual transfer runs only:

- `FINTS_TRANSFER_INSTANT_PAYMENT=true`
- `FINTS_TRANSFER_EXECUTION_DATE=YYYY-MM-DD`

## Documentation

Detailed API reference:

- [docs/API.md](/home/bomay/git/python-fints-REST-wrapper/docs/API.md)

Transfer workflow:

- [POST_transfer_workflow.md](/home/bomay/git/python-fints-REST-wrapper/POST_transfer_workflow.md)

High-level testing/verification notes:

- [USECASE.md](/home/bomay/git/python-fints-REST-wrapper/USECASE.md)
- [VERIFICATION.md](/home/bomay/git/python-fints-REST-wrapper/VERIFICATION.md)

## Development

Important files:

- [fints_rest_wrapper/fastapi_app.py](/home/bomay/git/python-fints-REST-wrapper/fints_rest_wrapper/fastapi_app.py)
- [fints_rest_wrapper/client.py](/home/bomay/git/python-fints-REST-wrapper/fints_rest_wrapper/client.py)
- [fints_rest_wrapper/helpers.py](/home/bomay/git/python-fints-REST-wrapper/fints_rest_wrapper/helpers.py)
- [fints_rest_wrapper/models.py](/home/bomay/git/python-fints-REST-wrapper/fints_rest_wrapper/models.py)

Basic checks:

```bash
python -m compileall fints_rest_wrapper api_tan_test_helper.py test_accounts_api_tan.py test_balance_api_tan.py test_transactions_api_tan.py test_single_account_api_tan.py test_transfer_api_tan.py
.venv/bin/python -m pytest tests -q
```

Package build:

```bash
python -m build
```

GitHub Actions:

- CI runs on pushes to `main` and on pull requests
- publishing to PyPI runs when a GitHub Release is published

## Packaging

Package name on PyPI:

- `fints-rest-wrapper`

Import package in Python:

- `fints_rest_wrapper`

Install from PyPI after the first published release:

```bash
pip install fints-rest-wrapper
```

## Deployment Notes

This project intentionally keeps the API simple:

- no server-side profile model
- no persistent credential store
- no server-managed account data
- no built-in authentication layer

Recommended deployment style:

- trusted network only
- TLS at the edge
- optional reverse proxy, VPN, mTLS, or network isolation depending on your stack
- operation logs are sanitized by default and do not store raw PINs, TANs, or raw FinTS payloads

Current limitation:

- active confirmation sessions are in-memory and process-local, so the simplest supported runtime is a single API process
