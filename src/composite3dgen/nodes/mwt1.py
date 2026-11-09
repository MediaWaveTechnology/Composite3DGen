"""MWT1 node helpers.

Full SSH transport + capability probes land in **U3b**. U2 only needs the
host alias and a health-check hook used by :mod:`composite3dgen.nodes.executor`.
"""

from __future__ import annotations

from typing import Callable

# Injectable probe for tests / U3b transport. Default assumes unreachable
# until U3b implements real SSH health checks.
HealthProbe = Callable[[], bool]

_DEFAULT_PROBE: HealthProbe | None = None


def host_alias() -> str:
    """SSH Host alias for the primary local compute node."""
    return "mwt1"


def host_address() -> str:
    """LAN address recorded in the playbook (verify in U3b)."""
    return "192.168.50.212"


def set_health_probe(probe: HealthProbe | None) -> None:
    """Install or clear the injectable MWT1 health probe (tests / U3b)."""
    global _DEFAULT_PROBE
    _DEFAULT_PROBE = probe


def is_healthy(probe: HealthProbe | None = None) -> bool:
    """Return whether MWT1 looks usable for MWT1-capable stages.

    Until U3b wires SSH + capability probes, the default returns ``False``
    so the selector falls back to the controller local executor (degraded
    mode). Tests and U3b can inject a probe via ``set_health_probe`` or the
    ``probe`` argument.
    """
    active = probe if probe is not None else _DEFAULT_PROBE
    if active is None:
        return False
    try:
        return bool(active())
    except Exception:  # noqa: BLE001 — health checks must not raise to callers
        return False
