"""Public FinTS client facade assembled from focused internal modules."""

from __future__ import annotations

from typing import Any, Optional

from ._client_common import (
    _tan_methods_snapshot_from_low_level_client,
    augment_error_with_bank_response,
    coerce_optional_bool,
    coerce_optional_date,
    looks_like_tan_required,
    looks_like_transfer_result,
    looks_like_vop_required,
    lookup_bank_info,
)
from ._client_confirmation import FinTSClientConfirmationMixin
from ._client_reads import FinTSClientReadMixin
from ._client_runtime import FinTSClientRuntimeMixin
from ._client_transfer import FinTSClientTransferMixin
from .helpers import apply_runtime_patches
from .models import FinTSConfig


apply_runtime_patches()


class FinTSClient(
    FinTSClientConfirmationMixin,
    FinTSClientReadMixin,
    FinTSClientTransferMixin,
    FinTSClientRuntimeMixin,
):
    """Backend-oriented wrapper that returns structured objects instead of printing."""

    def __init__(
        self,
        config: FinTSConfig,
        *,
        profile_id: Optional[str] = None,
        display_name: Optional[str] = None,
        bank_info_path: Optional[str] = None,
        sepa_profile_path: Optional[str] = None,
        auto_persist: bool = True,
    ):
        self.config = config
        self._client = None
        self._pending_tan_response = None
        self._pending_vop_response = None
        self._pending_transfer_params: Optional[dict[str, Any]] = None
        self._pending_transfer_overview: Optional[dict[str, Any]] = None
        self.profile_id = profile_id
        self.display_name = display_name
        self.bank_info_path = bank_info_path
        self.sepa_profile_path = sepa_profile_path
        self.auto_persist = auto_persist

    def _augment_error_with_bank_response(self, message: str) -> str:
        return augment_error_with_bank_response(message)


__all__ = [
    "FinTSClient",
    "lookup_bank_info",
    "looks_like_tan_required",
    "looks_like_vop_required",
    "looks_like_transfer_result",
    "coerce_optional_bool",
    "coerce_optional_date",
    "augment_error_with_bank_response",
    "_tan_methods_snapshot_from_low_level_client",
]
