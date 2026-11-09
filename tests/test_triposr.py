"""TripoSR adapter tests with mock SSH/FS (no live MWT1)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from composite3dgen.providers.base import JobStatus, ProviderJobRequest
from composite3dgen.providers.transport import MockRemoteFSTransport
from composite3dgen.providers.triposr import TripoSRAdapter, make_mock_adapter


def test_triposr_dry_run_records_virtual_job(tmp_path: Path) -> None:
    adapter = make_mock_adapter(tmp_path / "remote")
    (tmp_path / "front.jpg").write_bytes(b"fake-jpeg")
    req = ProviderJobRequest(
        provider="triposr",
        job_dir=tmp_path / "job",
        inputs={"image": str(tmp_path / "front.jpg")},
        mode="dry-run",
        subject_id="unit",
    )
    result = asyncio.run(adapter.run(req))
    assert result.status == JobStatus.DRY_RUN
    assert result.consumed == 0.0
    record = tmp_path / "job" / "out" / "triposr" / f"{result.job_id}.json"
    assert record.is_file()


def test_triposr_mock_ssh_stage_run_pull(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    fs = MockRemoteFSTransport(root=remote_root)

    def _handler_side_effect() -> None:
        # After "run.py" the adapter looks for mesh under remote output.
        # Create a matching mesh for any job output dir created during upload.
        pass

    # Intercept run: write mesh.glb into the remote_out implied by command.
    original_run = fs.run

    def run_and_write(command: str, *, timeout: float = 600.0):
        code, out, err = original_run(command, timeout=timeout)
        # command contains `--output-dir <path>`
        if "--output-dir" in command:
            out_dir = command.split("--output-dir", 1)[1].strip().split()[0]
            mesh = fs._map(f"{out_dir}/mesh.glb")
            mesh.parent.mkdir(parents=True, exist_ok=True)
            mesh.write_bytes(b"glTF-binary-mock")
        return code, out, err

    fs.run = run_and_write  # type: ignore[method-assign]

    adapter = TripoSRAdapter(transport=fs)
    image = tmp_path / "front.jpg"
    image.write_bytes(b"\xff\xd8\xfffake")
    job_dir = tmp_path / "job"
    req = ProviderJobRequest(
        provider="triposr",
        job_dir=job_dir,
        inputs={"image": str(image)},
        mode="local",
        subject_id="qm1",
    )
    result = asyncio.run(adapter.run(req))
    assert result.status == JobStatus.SUCCEEDED
    assert "glb" in result.artifacts
    assert Path(result.artifacts["glb"]).is_file()
    assert any("run.py" in c for c in fs.commands)
    _handler_side_effect()


def test_triposr_requires_transport_for_local(tmp_path: Path) -> None:
    adapter = TripoSRAdapter(transport=None)
    image = tmp_path / "front.jpg"
    image.write_bytes(b"x")
    req = ProviderJobRequest(
        provider="triposr",
        job_dir=tmp_path / "job",
        inputs={"image": str(image)},
        mode="local",
    )
    result = asyncio.run(adapter.run(req))
    assert result.status == JobStatus.FAILED
    assert "RemoteFSTransport" in (result.error or "")
