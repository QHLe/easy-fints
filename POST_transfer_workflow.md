# `POST /transfer` Workflow

This document describes the end-to-end transfer flow implemented by the REST wrapper for SEPA credit transfers.

Key points:

- local request validation happens before any bank request is sent
- the same API flow is used for standard SEPA transfers, instant payments, and dated transfers; `instant_payment=true` or `execution_date=...` only changes the FinTS payment payload requested from the bank
- the same structured `transfer_overview` payload is included in the initial transfer challenge response, later `/confirm` responses, and the final `TransferResponse`
- `/confirm` is the single continuation endpoint for TAN input, decoupled app polling, and VoP approval
- if the bank requires payee verification, the API returns `vop_required` with `state=awaiting_vop`
- active confirmation sessions can be cancelled with `DELETE /sessions/{session_id}`
- `POST /transfer/retry-with-name` keeps the same `session_id` and tries to reuse the current FinTS client/dialog when possible
- reusing the dialog can save a dialog bootstrap/login step, but the bank may still require another VoP or decoupled confirmation for the corrected payment order

```mermaid
flowchart TD
    A[POST /transfer] --> B{Local validation passed?}
    B -- No --> B1[400 validation_error]
    B -- Yes --> C[Start transfer with bank]

    C --> D{Does the bank require immediate confirmation?}
    D -- No --> Z1[200 TransferResponse SUCCESS]
    D -- Yes --> E[409 tan_required<br/>state=awaiting_decoupled or awaiting_tan]

    E --> F[POST /confirm]
    F --> G{Current session state}

    G -- awaiting_decoupled --> H[Confirm in banking app / decoupled poll]
    G -- awaiting_tan --> I[Submit TAN]
    G -- awaiting_vop --> J[Send approve_vop=true]

    H --> K[python-fints send_tan]
    I --> K
    J --> L[python-fints approve_vop_response]

    K --> M{Result}
    L --> N{Result}

    M -- More decoupled or TAN steps required --> E
    M -- FinTSInstituteMessage or intermediate state --> O[Resume original transfer operation]
    M -- Final TransactionResponse --> Z1

    O --> P{Is VoP required?}
    P -- No --> Q{Is more confirmation required?}
    P -- Yes --> R[409 vop_required<br/>state=awaiting_vop]

    Q -- Yes --> E
    Q -- No --> Z1

    R --> S{User decision}
    S -- Approve VoP --> F
    S -- Correct recipient name --> T[POST /transfer/retry-with-name]

    T --> U{Session currently awaiting_vop?}
    U -- No --> U1[400 validation_error]
    U -- Yes --> V[Keep the same session_id]
    V --> W[Reuse the same client/dialog<br/>when possible]
    W --> X[Restart transfer with corrected recipient_name]

    X --> Y{New bank result}
    Y -- VoP required again --> R
    Y -- TAN or decoupled confirmation required --> E
    Y -- Final result --> Z1
```

Typical real-world transfer path with decoupled approval and payee verification:

1. `POST /transfer` returns `409 tan_required` with `state=awaiting_decoupled`
2. the user confirms in the banking app and calls `POST /confirm`
3. the bank responds with `409 vop_required`
4. the user either approves the VoP result or retries with a corrected recipient name
5. the bank may require another decoupled confirmation
6. the flow ends with a final `TransferResponse`
