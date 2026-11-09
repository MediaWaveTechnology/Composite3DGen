"""Capability probe surface — stub until U3b."""

from __future__ import annotations

from typing import Any


def probe_stub() -> dict[str, Any]:
    """Return an empty capability report placeholder."""
    return {
        "node": "mwt1",
        "status": "unimplemented",
        "capabilities": {},
    }
