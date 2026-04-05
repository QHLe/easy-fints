from __future__ import annotations

from fints.client import NeedTANResponse

from fints_rest_wrapper.helpers import _retry_response_from_raw_response


class _FakeClient:
    @staticmethod
    def is_challenge_structured() -> bool:
        return False


class _FakeCommandSeg:
    class header:
        type = "HKCCS"


class _FakeTanRequest:
    challenge = "Enter TAN"
    challenge_hhduc = None


class _FakeResponse:
    def __init__(self, hitan=None):
        self._hitan = hitan

    def find_segment_first(self, value, throw: bool = False):
        if value == "HITAN":
            return self._hitan
        return None


def test_retry_response_fallback_builds_tan_response_from_hitan():
    response = _FakeResponse(hitan=_FakeTanRequest())

    result = _retry_response_from_raw_response(
        _FakeClient(),
        _FakeCommandSeg(),
        response,
        resume_func="resume_method",
    )

    assert isinstance(result, NeedTANResponse)
    assert result.challenge == "Enter TAN"


def test_retry_response_fallback_returns_none_without_hitan():
    response = _FakeResponse()

    result = _retry_response_from_raw_response(
        _FakeClient(),
        _FakeCommandSeg(),
        response,
        resume_func="resume_method",
    )

    assert result is None
