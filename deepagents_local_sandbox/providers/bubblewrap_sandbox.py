"""BubblewrapSandbox: Linux bwrap-based sandbox backend for deepagents."""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

_DEFAULT_TIMEOUT = 120

# Directories bind-mounted read-only into the sandbox
_RO_BIND_DIRS = ["/usr", "/bin", "/lib", "/etc/ssl"]
# Optional RO dirs (skipped if absent on the host)
_RO_BIND_DIRS_OPTIONAL = ["/lib64", "/lib32", "/usr/lib32"]
# Individual /etc files needed for basic Python and system tool operation
_RO_BIND_ETC_FILES = [
    "/etc/passwd",
    "/etc/group",
    "/etc/nsswitch.conf",
    "/etc/localtime",
    "/etc/hosts",
]
# Additional /etc files needed only when network access is enabled
_RO_BIND_ETC_NETWORK = ["/etc/resolv.conf"]


class BubblewrapSandbox(BaseSandbox):
    """Linux bwrap-based sandbox — no Docker required.

    Each ``execute()`` call spawns a fresh ``bwrap`` process.  Files are
    exchanged via a host tmpdir that is bind-mounted read-write as
    ``/workspace`` inside the sandbox.
    """

    def __init__(
        self,
        *,
        network_access: bool = False,
        timeout: int = _DEFAULT_TIMEOUT,
        workspace: str | None = None,
    ) -> None:
        self._network_access = network_access
        self._timeout = timeout
        self._sandbox_id = f"bwrap-{uuid.uuid4().hex[:8]}"
        self._tmpdir = tempfile.mkdtemp(prefix="deepagents-bwrap-") if workspace is None else workspace
        self._owns_tmpdir = workspace is None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._owns_tmpdir:
            import shutil
            try:
                shutil.rmtree(self._tmpdir, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self) -> BubblewrapSandbox:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # bwrap command builder
    # ------------------------------------------------------------------

    def _build_bwrap_cmd(self, shell_command: str) -> list[str]:
        cmd = ["bwrap"]

        # Namespace isolation
        cmd += ["--unshare-user", "--unshare-pid", "--unshare-ipc"]
        if not self._network_access:
            cmd += ["--unshare-net"]

        # Minimal /proc and /dev
        cmd += ["--proc", "/proc", "--dev", "/dev"]

        # Read-only system dirs
        for d in _RO_BIND_DIRS:
            if os.path.exists(d):
                cmd += ["--ro-bind", d, d]

        for d in _RO_BIND_DIRS_OPTIONAL:
            if os.path.exists(d):
                cmd += ["--ro-bind", d, d]

        # /tmp inside the sandbox
        cmd += ["--tmpfs", "/tmp"]  # noqa: S108

        # Workspace: host tmpdir → /workspace (read-write)
        cmd += ["--bind", self._tmpdir, "/workspace"]

        # Essential /etc files for Python and common tools
        for f in _RO_BIND_ETC_FILES:
            if os.path.exists(f):
                cmd += ["--ro-bind", f, f]

        if self._network_access:
            for f in _RO_BIND_ETC_NETWORK:
                if os.path.exists(f):
                    cmd += ["--ro-bind", f, f]

        # Run commands from /workspace so relative paths resolve correctly
        cmd += ["--chdir", "/workspace"]

        cmd += ["/bin/sh", "-c", shell_command]
        return cmd

    # ------------------------------------------------------------------
    # BaseSandbox abstract interface
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self._sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = timeout if timeout is not None else self._timeout

        try:
            proc = subprocess.run(  # noqa: S603
                self._build_bwrap_cmd(command),
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            parts = []
            if proc.stdout:
                parts.append(proc.stdout)
            if proc.stderr:
                for line in proc.stderr.strip().splitlines():
                    parts.append(f"[stderr] {line}")
            output = "\n".join(parts) if parts else "<no output>"
            return ExecuteResponse(output=output, exit_code=proc.returncode)

        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Error: command timed out after {effective_timeout}s",
                exit_code=124,
            )
        except FileNotFoundError:
            return ExecuteResponse(
                output="Error: bwrap not found. Install bubblewrap (e.g. apt install bubblewrap).",
                exit_code=1,
            )
        except Exception as exc:  # noqa: BLE001
            return ExecuteResponse(output=f"Error: {exc}", exit_code=1)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            # Paths inside the sandbox start with /workspace; strip that prefix
            # to find the real host path, or fall back to storing under tmpdir.
            host_path = self._sandbox_to_host(path)
            try:
                host_path.parent.mkdir(parents=True, exist_ok=True)
                host_path.write_bytes(content)
                responses.append(FileUploadResponse(path=path))
            except PermissionError:
                responses.append(FileUploadResponse(path=path, error="permission_denied"))
            except Exception:  # noqa: BLE001
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            host_path = self._sandbox_to_host(path)
            try:
                if not host_path.exists():
                    responses.append(FileDownloadResponse(path=path, error="file_not_found"))
                    continue
                if host_path.is_dir():
                    responses.append(FileDownloadResponse(path=path, error="is_directory"))
                    continue
                responses.append(FileDownloadResponse(path=path, content=host_path.read_bytes()))
            except Exception:  # noqa: BLE001
                responses.append(FileDownloadResponse(path=path, error="invalid_path"))
        return responses

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _sandbox_to_host(self, sandbox_path: str) -> Path:
        """Map a sandbox-side path to its host-side equivalent."""
        p = sandbox_path.lstrip("/")
        if p.startswith("workspace/"):
            p = p[len("workspace/"):]
        elif sandbox_path == "/workspace":
            return Path(self._tmpdir)
        return Path(self._tmpdir) / p
