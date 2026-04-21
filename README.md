# easy-fints

Python library with an optional FastAPI wrapper around `python-fints`.

PyPI package:

- `easy-fints`

Python import package:

- `easy_fints`

It currently supports:

- account listing
- balances
- transactions
- SEPA transfers
- TAN / decoupled confirmation flows
- payee verification (`VoP`) continuation

The package can be used in three ways:

- as a Python library
- as a FastAPI-based REST server
- as a Dockerized REST server

## Quick Start

Requirements:

- Python 3.11+
- a bank account with FinTS/HBCI access
- valid FinTS credentials and server URL

Install from PyPI:

```bash
pip install easy-fints
```

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
FINTS_DEBUG_LEVEL=off
FINTS_DEBUG_FAIL_ONLY=0
```

A FinTS product ID can be requested via the official registration page:

- `https://www.fints.org/de/hersteller/produktregistrierung`

## Usage Modes

- `Library`: import `FinTS` directly in your Python application
- `REST server`: run the built-in FastAPI service locally
- `Docker`: run the REST server through `Dockerfile` or `docker-compose.yml`

## Library

Use the package directly in Python:

```python
from easy_fints import (
    FinTS,
    TanRequiredError,
)

with FinTS(
    product_id="YourProductID",
    bank="12345678",
    user="your-user",
    pin="your-pin",
    server="https://bank.example/fints",
) as fints:
    try:
        accounts = fints.accounts()
        transactions = fints.transactions(days=30)
    except TanRequiredError as exc:
        print(exc.challenge.message)
```

## REST Server

Run the optional local HTTP server with the bundled CLI:

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

Installed CLI defaults:

- server host: `0.0.0.0`
- server port: `8000`
- PID file: `.fints-rest-server.pid`
- log file: `.fints-rest-server.log`

CLI examples:

```bash
fints-rest-server start --host 127.0.0.1 --port 9686
fints-rest-server start --env-file /etc/easy-fints.env
fints-rest-server stop
```

OpenAPI:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

## Docker

The repository includes both [`Dockerfile`](Dockerfile) and [`docker-compose.yml`](docker-compose.yml).

Start the REST server with Docker Compose:

```bash
docker compose up --build -d
docker compose logs -f api
docker compose down
```

Current Docker defaults:

- container port: `9686`
- published port: `9686`
- env file: `.env`
- log volume: `./logs:/app/logs`

Docker OpenAPI:

- `http://127.0.0.1:9686/docs`
- `http://127.0.0.1:9686/openapi.json`

## REST API

Optional HTTP endpoints:

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

## Examples

The repository includes small scripts for manual API testing:

Library examples:

- [`examples/accounts_lib.py`](examples/accounts_lib.py)
- [`examples/balance_lib.py`](examples/balance_lib.py)
- [`examples/transactions_lib.py`](examples/transactions_lib.py)
- [`examples/single_account_lib.py`](examples/single_account_lib.py)
- [`examples/transfer_lib.py`](examples/transfer_lib.py)

They use [`examples/lib_helper.py`](examples/lib_helper.py) and talk directly to `FinTS`.

REST API examples:

- [`examples/accounts_api_tan.py`](examples/accounts_api_tan.py)
- [`examples/balance_api_tan.py`](examples/balance_api_tan.py)
- [`examples/transactions_api_tan.py`](examples/transactions_api_tan.py)
- [`examples/single_account_api_tan.py`](examples/single_account_api_tan.py)
- [`examples/transfer_api_tan.py`](examples/transfer_api_tan.py)

They use [`examples/api_tan_helper.py`](examples/api_tan_helper.py) and read credentials from `.env`.

Optional helper-script env vars for manual transfer runs only:

- `FINTS_TRANSFER_INSTANT_PAYMENT=true`
- `FINTS_TRANSFER_EXECUTION_DATE=YYYY-MM-DD`

## Documentation

Detailed REST API reference:

- [`docs/API.md`](docs/API.md)

Transfer workflow:

- [`POST_transfer_workflow.md`](POST_transfer_workflow.md)

High-level testing/verification notes:

- [`USECASE.md`](USECASE.md)
- [`VERIFICATION.md`](VERIFICATION.md)

## Development

Important files:

- [`easy_fints/api.py`](easy_fints/api.py)
- [`easy_fints/client.py`](easy_fints/client.py)
- [`easy_fints/helpers.py`](easy_fints/helpers.py)
- [`easy_fints/models.py`](easy_fints/models.py)

Basic checks:

```bash
python -m compileall easy_fints examples
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

- `easy-fints`

Import package in Python:

- `easy_fints`

Install from PyPI after the first published release:

```bash
pip install easy-fints
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

## Debug Logging

Optional transaction debugging can be enabled with environment variables:

- `FINTS_DEBUG_LEVEL=off|summary|mapping|record_raw`
- `FINTS_DEBUG_FAIL_ONLY=1` to emit debug output only when a transaction is missing dates or amount after normalization

Debug entries are written to `logs/debug.log`.

Recommended troubleshooting setup for normalization issues:

```env
FINTS_DEBUG_LEVEL=record_raw
FINTS_DEBUG_FAIL_ONLY=1
```

Notes:

- `summary` writes one compact entry per transaction fetch
- `mapping` adds selected field sources and visible raw key names per record
- `record_raw` also includes the raw transaction payload/representation and may contain sensitive bank data
