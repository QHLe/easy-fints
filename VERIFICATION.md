# Verification Plan For Simulated FinTS Backend

## Goal

Track how the simulated FinTS backend will be verified at a high level.

This document is about evidence and coverage, not detailed implementation.

## Verification Strategy

We use three layers:

1. Unit verification
2. Simulated integration verification
3. Selective live-bank smoke verification

The simulated backend should carry most of the functional coverage.
Live-bank runs should stay small and focused.

Current automated baseline:

- [`tests/test_helpers.py`](tests/test_helpers.py)
- [`tests/test_debug_logging.py`](tests/test_debug_logging.py)
- [`tests/test_api_readiness.py`](tests/test_api_readiness.py)
- [`tests/test_api_read_flows.py`](tests/test_api_read_flows.py)
- [`tests/test_api_transfer_flows.py`](tests/test_api_transfer_flows.py)
- [`tests/test_api_session_lifecycle.py`](tests/test_api_session_lifecycle.py)
- exercises transaction normalization source selection and debug logging in addition to API/session behavior
- runs against a stateful fake FinTS backend/client
- exercises endpoint logic directly with deterministic session state transitions

## Verification Layers

### Unit verification

Purpose:

- validate small pure functions
- validate request parsing and normalization
- validate state transitions and error mapping

Examples:

- bool/date parsing for transfer options
- session snapshot generation
- transfer overview construction
- unsupported transfer product normalization
- transaction normalization across flat and nested CAMT-like payloads
- debug logging fail-only behavior and selected field-source capture

### Simulated integration verification

Purpose:

- verify API behavior end to end without a real bank
- verify stateful confirm flows across multiple requests
- verify deterministic behavior for hard-to-reproduce bank scenarios

Examples:

- `/transfer -> /confirm -> success`
- `/transfer -> /confirm -> vop_required -> retry-with-name -> success`
- `/transfer -> unsupported_transfer_product`
- `/readiness -> ready` and `/readiness -> not_ready`
- `/sessions/{id}` inspection and cancellation

### Live-bank smoke verification

Purpose:

- confirm the wrapper still works against real-world FinTS servers
- catch mismatches between simulator assumptions and real bank behavior

Examples:

- one standard transfer smoke test
- one VoP flow smoke test
- one instant-payment smoke test if supported by the bank

## Verification Matrix

| Area | Verify with unit tests | Verify with simulated integration | Verify with live smoke | Status |
|---|---|---|---|---|
| Accounts flow | Partial | Yes | Optional | In progress |
| Balance flow | Partial | Yes | Optional | Planned |
| Transactions flow | Partial | Yes | Optional | In progress |
| TAN flow | Partial | Yes | Yes | In progress |
| Decoupled flow | Partial | Yes | Yes | In progress |
| VoP flow | Partial | Yes | Yes | In progress |
| Retry-with-name flow | Partial | Yes | Optional | In progress |
| Transaction normalization | Yes | Optional | Optional | Verified |
| Transaction normalization debug logging | Yes | Optional | Optional | Verified |
| Transfer overview propagation | Yes | Yes | Optional | Verified |
| Instant payment capability handling | Yes | Yes | Optional | Verified for unsupported case |
| Scheduled transfer capability handling | Yes | Yes | Optional | Verified for unsupported case |
| Readiness probe | Yes | Optional | Optional | Verified |
| Session inspection | Yes | Yes | Optional | Verified |
| Session cancellation | Yes | Yes | Optional | Verified |
| Session expiry | Yes | Yes | Optional | Verified |
| Shutdown cleanup | Partial | Yes | Optional | Verified |

## Mapping To Use Cases

| Use case IDs | Verification expectation |
|---|---|
| UC-01 to UC-04 | simulated integration must cover the baseline read and transfer flows |
| UC-05 to UC-09 | simulated integration must cover all confirm, VoP, and retry states |
| UC-10 | unit + simulated integration |
| UC-11 to UC-14 | unit + simulated integration, optional live smoke if supported |
| UC-15 to UC-20 | unit + simulated integration |

## Evidence To Collect

For each implemented scenario we should be able to point to:

- a named automated test or scenario
- the expected final HTTP status
- the expected response shape
- the expected session state transitions

Useful evidence includes:

- pytest output
- saved API response fixtures
- state transition logs
- normalization debug records in `logs/debug.log` for targeted troubleshooting
- one short live-bank validation note for selected smoke tests

## Acceptance Criteria

The simulated backend is useful when:

- common transfer flows can be tested without a bank account
- TAN, decoupled, and VoP branches are reproducible on demand
- unsupported transfer products can be verified deterministically
- session endpoints and expiry behavior can be tested automatically
- normalization regressions can be diagnosed with deterministic debug/source output
- helper scripts and API consumers can be exercised against both real and simulated backends with minimal changes

## Non-Goals

- replace all real-bank verification
- perfectly emulate every bank
- replicate raw FinTS protocol details byte-for-byte

## Next Verification Milestones

1. Extend the fake backend coverage to `UC-01`, `UC-05`, `UC-06`, `UC-09`, `UC-11`, and `UC-13`.
2. Add targeted balance-flow checks so read endpoints share the same simulated baseline.
3. Add fixture coverage for additional bank-specific transaction payload shapes in `transaction_mapping/`.
4. Add a small smoke checklist for real-bank verification after major transfer-flow changes.
5. Keep this document updated as scenarios move from Planned to Verified.
