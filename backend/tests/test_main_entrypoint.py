from __future__ import annotations

import runpy
from pathlib import Path

import uvicorn


def test_python_main_py_starts_backend_with_uvicorn(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run(app_path: str, **kwargs: object) -> None:
        calls.append((app_path, kwargs))

    monkeypatch.setattr(uvicorn, "run", fake_run)

    runpy.run_path(str(Path(__file__).resolve().parents[1] / "main.py"), run_name="__main__")

    assert calls == [
        (
            "app.main:app",
            {
                "host": "127.0.0.1",
                "port": 8000,
                "reload": True,
            },
        )
    ]


def test_python_main_py_accepts_backend_startup_env(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run(app_path: str, **kwargs: object) -> None:
        calls.append((app_path, kwargs))

    monkeypatch.setenv("SAVEANY_BACKEND_HOST", "0.0.0.0")
    monkeypatch.setenv("SAVEANY_BACKEND_PORT", "8765")
    monkeypatch.setenv("SAVEANY_BACKEND_RELOAD", "false")
    monkeypatch.setattr(uvicorn, "run", fake_run)

    runpy.run_path(str(Path(__file__).resolve().parents[1] / "main.py"), run_name="__main__")

    assert calls == [
        (
            "app.main:app",
            {
                "host": "0.0.0.0",
                "port": 8765,
                "reload": False,
            },
        )
    ]
