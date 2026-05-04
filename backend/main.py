from __future__ import annotations

import uvicorn

from app.services.env_file import bool_env_enabled, env_value


DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8000
DEFAULT_BACKEND_RELOAD = True


def start_backend() -> None:
    uvicorn.run(
        "app.main:app",
        host=env_value("SAVEANY_BACKEND_HOST", DEFAULT_BACKEND_HOST).strip() or DEFAULT_BACKEND_HOST,
        port=int(env_value("SAVEANY_BACKEND_PORT", str(DEFAULT_BACKEND_PORT))),
        reload=bool_env_enabled("SAVEANY_BACKEND_RELOAD", DEFAULT_BACKEND_RELOAD),
    )


if __name__ == "__main__":
    start_backend()
