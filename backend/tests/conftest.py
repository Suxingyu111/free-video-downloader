from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_local_env_file(monkeypatch, tmp_path):
    if "SAVEANY_ENV_FILE" not in os.environ:
        monkeypatch.setenv("SAVEANY_ENV_FILE", str(tmp_path / "missing.env"))
