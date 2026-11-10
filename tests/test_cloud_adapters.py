"""Cloud provider adapter tests with mock HTTP (no live paid calls)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from composite3dgen.providers.base import JobStatus, ProviderJobRequest
from composite3dgen.providers.hi3d import Hi3DAdapter
from composite3dgen.providers.rodin import RodinAdapter
from composite3dgen.providers.transport import HTTPResponse, MockHTTPTransport
from composite3dgen.providers.tripo import TripoAdapter


def _env() -> dict[str, str]:
    return {
        "TRIPO_API_KEY": "test-tripo-key",
        "HI3D_API_KEY": "test-hi3d-key",
        "RODIN_API_KEY": "test-rodin-key",
    }


def test_tripo_dry_run_no_http(tmp_path: Path) -> None:
    http = MockHTTPTransport()
    adapter = TripoAdapter(transport=http, environ=_env())
    req = ProviderJobRequest(
        provider="tripo",
        job_dir=tmp_path,
        inputs={"front": str(tmp_path / "f.jpg")},
        mode="dry-run",
    )
    result = asyncio.run(adapter.run(req))
    assert result.status == JobStatus.DRY_RUN
    assert http.calls == []


def test_tripo_live_submit_poll(tmp_path: Path) -> None:
    http = MockHTTPTransport()
    http.enqueue(
        HTTPResponse(
            status=200,
            body=json.dumps({"data": {"task_id": "task-abc"}}).encode(),
        )
    )
    http.enqueue(
        HTTPResponse(
            status=200,
            body=json.dumps(
                {
                    "data": {
                        "status": "success",
                        "consumed": 0.42,
                        "output": {"model": "https://example.test/model.glb"},
                    }
                }
            ).encode(),
        )
    )
    adapter = TripoAdapter(transport=http, environ=_env())
    req = ProviderJobRequest(
        provider="tripo",
        job_dir=tmp_path,
        inputs={"images": {"front": "front.jpg"}},
        mode="live",
        options={"file_tokens": ["tok1"]},
    )
    result = asyncio.run(adapter.run(req))
    assert result.status == JobStatus.SUCCEEDED
    assert result.remote_task_id == "task-abc"
    assert result.consumed == 0.42
    assert result.artifacts.get("model_url")
    assert http.calls[0]["method"] == "POST"
    assert "Authorization" in http.calls[0]["headers"]


def test_tripo_live_without_secret_blocked(tmp_path: Path) -> None:
    http = MockHTTPTransport()
    adapter = TripoAdapter(transport=http, environ={})
    req = ProviderJobRequest(provider="tripo", job_dir=tmp_path, mode="live")
    result = asyncio.run(adapter.run(req))
    assert result.status == JobStatus.BLOCKED
    assert http.calls == []


def test_hi3d_submit_poll(tmp_path: Path) -> None:
    http = MockHTTPTransport()
    http.enqueue(HTTPResponse(status=200, body=json.dumps({"id": "hi-1"}).encode()))
    http.enqueue(
        HTTPResponse(
            status=200,
            body=json.dumps(
                {"status": "completed", "consumed": 0.9, "outputs": {"glb": "https://x/a.glb"}}
            ).encode(),
        )
    )
    adapter = Hi3DAdapter(transport=http, environ=_env(), base_url="https://hi3d.test/v1")
    req = ProviderJobRequest(
        provider="hi3d",
        job_dir=tmp_path,
        mode="live",
        options={"quality": "2048quality"},
        inputs={"front": "f.jpg", "left": "l.jpg", "back": "b.jpg", "right": "r.jpg"},
    )
    result = asyncio.run(adapter.run(req))
    assert result.status == JobStatus.SUCCEEDED
    assert result.artifacts["glb"] == "https://x/a.glb"


def test_rodin_gen25_and_bang_dry_run(tmp_path: Path) -> None:
    http = MockHTTPTransport()
    adapter = RodinAdapter(transport=http, environ=_env())
    gen = asyncio.run(
        adapter.run(
            ProviderJobRequest(
                provider="rodin",
                job_dir=tmp_path,
                mode="dry-run",
                options={"operation": "gen25"},
            )
        )
    )
    bang = asyncio.run(
        adapter.run(
            ProviderJobRequest(
                provider="rodin",
                job_dir=tmp_path,
                mode="dry-run",
                options={"operation": "bang", "strength": 8},
                inputs={"glb": str(tmp_path / "in.glb")},
            )
        )
    )
    assert gen.status == JobStatus.DRY_RUN
    assert bang.status == JobStatus.DRY_RUN
    assert bang.artifacts["planned_payload"]["strength"] == 8
    assert bang.artifacts["planned_payload"]["operation"] == "custom_bang"
    assert http.calls == []


def test_rodin_live_bang(tmp_path: Path) -> None:
    http = MockHTTPTransport()
    http.enqueue(HTTPResponse(status=200, body=json.dumps({"uuid": "rod-9"}).encode()))
    http.enqueue(
        HTTPResponse(
            status=200,
            body=json.dumps(
                {
                    "status": "generate_done",
                    "consumed": 0.5,
                    "result": {"bang_glb": "https://x/bang.glb"},
                }
            ).encode(),
        )
    )
    adapter = RodinAdapter(transport=http, environ=_env())
    result = asyncio.run(
        adapter.run(
            ProviderJobRequest(
                provider="rodin",
                job_dir=tmp_path,
                mode="live",
                options={"operation": "bang", "strength": 4},
                inputs={"glb": "mesh.glb"},
            )
        )
    )
    assert result.status == JobStatus.SUCCEEDED
    assert result.remote_task_id == "rod-9"
    assert http.calls[0]["url"].endswith("/bang")
