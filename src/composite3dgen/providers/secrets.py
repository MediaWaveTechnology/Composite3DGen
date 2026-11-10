"""Load provider API keys from environment only (never git / files in-repo).

Bitwarden CLI remains the human/controller workflow for populating env vars —
see root ``AGENTS.md``. Adapters never read Bitwarden directly so tests stay
offline and secrets never land in job manifests.
"""

from __future__ import annotations

import os
from typing import Mapping

# Canonical env var names per paid provider.
ENV_KEYS: Mapping[str, tuple[str, ...]] = {
    "tripo": ("TRIPO_API_KEY", "TRIPO_TOKEN"),
    "hi3d": ("HI3D_API_KEY", "HI3D_TOKEN"),
    "rodin": ("RODIN_API_KEY", "RODIN_TOKEN", "HYPER3D_API_KEY"),
    "seedance": ("SEEDANCE_API_KEY", "SEEDANCE_TOKEN"),
}


class MissingSecretError(RuntimeError):
    """Raised when a live paid call needs a key that is not in the environment."""


def get_api_key(provider: str, *, environ: Mapping[str, str] | None = None) -> str | None:
    """Return the first non-empty env value for ``provider``, or ``None``."""
    env = environ if environ is not None else os.environ
    for name in ENV_KEYS.get(provider, ()):
        value = env.get(name, "").strip()
        if value:
            return value
    return None


def require_api_key(provider: str, *, environ: Mapping[str, str] | None = None) -> str:
    """Return an API key or raise :class:`MissingSecretError`."""
    key = get_api_key(provider, environ=environ)
    if not key:
        names = ", ".join(ENV_KEYS.get(provider, ()))
        raise MissingSecretError(
            f"Missing API key for paid provider '{provider}'. "
            f"Set one of: {names} (via Bitwarden/env on the controller). "
            "Never commit secrets to git."
        )
    return key
