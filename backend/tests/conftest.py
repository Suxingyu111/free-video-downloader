from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_local_stripe_config(monkeypatch, tmp_path):
    if "STRIPE_CONFIG_FILE" not in os.environ:
        monkeypatch.setenv("STRIPE_CONFIG_FILE", str(tmp_path / "missing-stripe.env"))
