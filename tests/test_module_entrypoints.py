from __future__ import annotations

from easy_fints.api import app
from easy_fints.library import FinTS


def test_new_module_entrypoints_are_importable():
    assert app is not None
    assert FinTS.__module__ == "easy_fints.library"
