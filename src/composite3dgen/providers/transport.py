"""Injectable HTTP and SSH/FS transports for provider adapters.

U3 keeps transports mockable. Full real MWT1 capability probes are **U3b** —
see ``deploy/mwt1/README.md`` and the U3b handoff notes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable
from urllib import error as urlerror
from urllib import request as urlrequest


@dataclass
class HTTPResponse:
    """Minimal HTTP response surface used by cloud adapters."""

    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@runtime_checkable
class HTTPTransport(Protocol):
    """HTTP client injectable for Tripo / Hi3D / Rodin (and tests)."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Any | None = None,
        data: bytes | None = None,
        timeout: float = 60.0,
    ) -> HTTPResponse: ...


@dataclass
class UrllibHTTPTransport:
    """Default live HTTP transport via :mod:`urllib` (stdlib only)."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Any | None = None,
        data: bytes | None = None,
        timeout: float = 60.0,
    ) -> HTTPResponse:
        hdrs = {k: str(v) for k, v in (headers or {}).items()}
        body = data
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        req = urlrequest.Request(url, data=body, headers=hdrs, method=method.upper())
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — caller supplies URL
                return HTTPResponse(
                    status=getattr(resp, "status", 200),
                    body=resp.read(),
                    headers={k.lower(): v for k, v in dict(resp.headers).items()},
                )
        except urlerror.HTTPError as exc:
            return HTTPResponse(
                status=exc.code,
                body=exc.read() if exc.fp is not None else b"",
                headers={k.lower(): v for k, v in dict(exc.headers or {}).items()},
            )


@dataclass
class MockHTTPTransport:
    """Queue-based HTTP mock for unit tests (no network)."""

    responses: list[HTTPResponse] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def enqueue(self, response: HTTPResponse) -> None:
        self.responses.append(response)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Any | None = None,
        data: bytes | None = None,
        timeout: float = 60.0,
    ) -> HTTPResponse:
        self.calls.append(
            {
                "method": method.upper(),
                "url": url,
                "headers": dict(headers or {}),
                "json_body": json_body,
                "data": data,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise RuntimeError("MockHTTPTransport: no queued responses")
        return self.responses.pop(0)


@runtime_checkable
class RemoteFSTransport(Protocol):
    """SSH/FS surface for TripoSR remote staging on MWT1.

    U3b must fill: real SSH host key checks, capability probes (CUDA, pinned
    TripoSR path), writable ``~/composite3dgen/jobs/``, and fail-closed
    remediation. U3 only requires an injectable transport for tests + dry-run.
    """

    def run(self, command: str, *, timeout: float = 600.0) -> tuple[int, str, str]:
        """Run a remote command; return (exit_code, stdout, stderr)."""

    def upload(self, local: Path, remote: str) -> None:
        """Copy a local file to a remote path."""

    def download(self, remote: str, local: Path) -> None:
        """Copy a remote file to a local path."""

    def exists(self, remote: str) -> bool:
        """Return whether a remote path exists."""

    def makedirs(self, remote: str) -> None:
        """Create remote directories (``mkdir -p``)."""


@dataclass
class MockRemoteFSTransport:
    """In-memory / local-temp SSH/FS mock for TripoSR tests."""

    root: Path
    commands: list[str] = field(default_factory=list)
    run_handlers: dict[str, tuple[int, str, str]] = field(default_factory=dict)
    default_run: tuple[int, str, str] = (0, "", "")

    def _map(self, remote: str) -> Path:
        # Treat absolute remotes as relative to mock root.
        cleaned = remote.lstrip("/")
        if cleaned.startswith("~/"):
            cleaned = cleaned[2:]
        path = self.root / cleaned
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def run(self, command: str, *, timeout: float = 600.0) -> tuple[int, str, str]:
        del timeout
        self.commands.append(command)
        for needle, result in self.run_handlers.items():
            if needle in command:
                return result
        return self.default_run

    def upload(self, local: Path, remote: str) -> None:
        dest = self._map(remote)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dest)

    def download(self, remote: str, local: Path) -> None:
        src = self._map(remote)
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local)

    def exists(self, remote: str) -> bool:
        return self._map(remote).exists()

    def makedirs(self, remote: str) -> None:
        self._map(remote).mkdir(parents=True, exist_ok=True)


@dataclass
class SubprocessSSHTransport:
    """Thin ``ssh``/``scp`` wrapper — real MWT1 wiring is a **U3b** concern.

    Kept injectable so U3 adapters compile against a live-shaped transport
    without requiring capability probes here.
    """

    host: str = "mwt1"
    ssh_binary: str = "ssh"
    scp_binary: str = "scp"

    def run(self, command: str, *, timeout: float = 600.0) -> tuple[int, str, str]:
        proc = subprocess.run(  # noqa: S603 — host/command come from caller config
            [self.ssh_binary, self.host, command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def upload(self, local: Path, remote: str) -> None:
        target = f"{self.host}:{remote}"
        subprocess.run(  # noqa: S603
            [self.scp_binary, str(local), target],
            check=True,
            capture_output=True,
            text=True,
        )

    def download(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        source = f"{self.host}:{remote}"
        subprocess.run(  # noqa: S603
            [self.scp_binary, source, str(local)],
            check=True,
            capture_output=True,
            text=True,
        )

    def exists(self, remote: str) -> bool:
        code, _, _ = self.run(f"test -e {remote!s} && echo yes || echo no")
        # Prefer explicit test exit code
        code2, out, _ = self.run(f"if [ -e {remote} ]; then echo yes; else echo no; fi")
        del code
        return "yes" in out or code2 == 0 and "yes" in out

    def makedirs(self, remote: str) -> None:
        code, _, err = self.run(f"mkdir -p {remote}")
        if code != 0:
            raise RuntimeError(f"makedirs failed: {err}")
