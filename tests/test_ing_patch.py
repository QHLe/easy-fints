from __future__ import annotations

from types import SimpleNamespace

from fints.client import ING_BANK_IDENTIFIER

from fints_rest_wrapper.helpers import _apply_ing_two_step_tan_selection


class _FakeClient:
    def __init__(self, *, bank_identifier):
        self.bank_identifier = bank_identifier
        self.allowed_security_functions = []
        self.selected_security_function = None
        self._methods = {
            "999": SimpleNamespace(tan_process="1", security_function="999"),
            "940": SimpleNamespace(tan_process="2", security_function="940"),
        }

    def get_tan_mechanisms(self):
        return self._methods

    def get_current_tan_mechanism(self):
        return self.selected_security_function

    def set_tan_mechanism(self, value):
        self.selected_security_function = str(value)


def test_ing_patch_selects_two_step_tan_when_3920_is_received():
    client = _FakeClient(bank_identifier=ING_BANK_IDENTIFIER)
    response = SimpleNamespace(code="3920", parameters=["940"])

    changed = _apply_ing_two_step_tan_selection(client, response)

    assert changed is True
    assert client.allowed_security_functions == ["940"]
    assert client.selected_security_function == "940"


def test_ing_patch_ignores_non_ing_clients():
    client = _FakeClient(bank_identifier="not-ing")
    response = SimpleNamespace(code="3920", parameters=["940"])

    changed = _apply_ing_two_step_tan_selection(client, response)

    assert changed is False
    assert client.selected_security_function is None
