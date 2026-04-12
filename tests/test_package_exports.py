from __future__ import annotations

from easy_fints import (
    FinTSClient,
    FinTSConfig,
    FinTSOperationError,
    TanRequiredError,
)


def test_public_package_exports_are_available():
    assert FinTSClient.__name__ == "FinTSClient"
    assert FinTSConfig.__name__ == "FinTSConfig"
    assert issubclass(TanRequiredError, FinTSOperationError)
