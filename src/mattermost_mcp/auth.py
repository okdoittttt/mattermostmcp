from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


class AuthProvider(ABC):
    @abstractmethod
    def driver_config(self) -> dict[str, Any]:
        ...


class MissingTokenError(RuntimeError):
    pass


class EnvTokenAuth(AuthProvider):
    def __init__(self, env_path: str | os.PathLike[str] | None = None) -> None:
        if env_path is not None:
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            load_dotenv(override=False)

    def driver_config(self) -> dict[str, Any]:
        url = os.environ.get("MM_URL", "").strip()
        token = os.environ.get("MM_TOKEN", "").strip()
        if not url:
            raise MissingTokenError(
                "MM_URL is not set. Configure it in .env or claude_desktop_config.json env block."
            )
        if not token:
            raise MissingTokenError(
                "MM_TOKEN is not set. Create a Personal Access Token in Mattermost and set MM_TOKEN."
            )

        url = url.replace("https://", "").replace("http://", "").rstrip("/")

        scheme = os.environ.get("MM_SCHEME", "https").strip() or "https"
        try:
            port = int(os.environ.get("MM_PORT", "443").strip() or "443")
        except ValueError:
            port = 443

        verify: bool | str = True
        ca_bundle = os.environ.get("MM_CA_BUNDLE", "").strip()
        if ca_bundle:
            ca_path = Path(ca_bundle).expanduser()
            verify = str(ca_path)
        elif os.environ.get("MM_VERIFY_SSL", "true").strip().lower() in {"false", "0", "no"}:
            verify = False

        return {
            "url": url,
            "token": token,
            "scheme": scheme,
            "port": port,
            "verify": verify,
            "timeout": 30,
        }
