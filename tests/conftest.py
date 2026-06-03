"""Shared pytest fixtures.

A single trained ``ModelHub`` is built once per session and reused across the
unit/integration suites, so the tests stay fast (training is the expensive bit).
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.trainer import ModelHub  # noqa: E402


@pytest.fixture(scope="session")
def hub() -> ModelHub:
    h = ModelHub()
    h.quick_pretrain(n_per_class=150)  # small + fast, still separable
    return h
