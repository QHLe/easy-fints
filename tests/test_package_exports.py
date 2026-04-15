from __future__ import annotations

from easy_fints import (
    BankInfo,
    FinTSClient,
    FinTSConfig,
    FinTSOperationError,
    TanRequiredError,
    lookup_bank_info,
)


def test_public_package_exports_are_available():
    assert BankInfo.__name__ == "BankInfo"
    assert FinTSClient.__name__ == "FinTSClient"
    assert FinTSConfig.__name__ == "FinTSConfig"
    assert callable(lookup_bank_info)
    assert issubclass(TanRequiredError, FinTSOperationError)
