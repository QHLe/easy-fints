from __future__ import annotations

from typing import Any

from . import default, vr_camt
from .base import (
    NORMALIZED_TRANSACTION_FIELDS,
    data_value,
    empty_transaction_row,
    field_present,
    json_compatible,
    module_applied,
    transaction_data,
    transaction_debug_failure_reasons,
)

MAPPING_MODULES = (default, vr_camt)


def normalize_transaction(tx: Any, *, include_debug: bool = False) -> dict[str, Any]:
    data = transaction_data(tx)
    row = empty_transaction_row(tx)
    selected_sources = {field: None for field in NORMALIZED_TRANSACTION_FIELDS}
    applied_modules: list[str] = []

    for module in MAPPING_MODULES:
        if not module.applies(data):
            continue
        result = module.map_transaction(tx, data)
        if not module_applied(result.values):
            continue
        applied_modules.append(module.NAME)
        for field in NORMALIZED_TRANSACTION_FIELDS:
            value = result.values.get(field)
            if not field_present(value) or field_present(row.get(field)):
                continue
            row[field] = value
            source = result.sources.get(field)
            if source:
                selected_sources[field] = f"{module.NAME}.{source}"

    if include_debug:
        row["__debug__"] = {
            "raw_type": type(tx).__name__,
            "raw_keys": sorted(str(key) for key in data.keys()),
            "sources": selected_sources,
            "applied_modules": applied_modules,
            "credit_debit_indicator": data_value(
                data,
                "CreditDebitIndicator",
                "EntryDetails.TransactionDetails.CreditDebitIndicator",
            ),
            "failure_reasons": transaction_debug_failure_reasons(row),
            "raw_data": json_compatible(data),
        }
    return row
