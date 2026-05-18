"""DockerSandbox: isolated container-based sandbox backend for deepagents."""

from __future__ import annotations

import io
import os
import queue
import tarfile
import threading
import uuid
from typing import TYPE_CHECKING

from typing import cast

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileOperationError,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

if TYPE_CHECKING:
    import docker as docker_module
    from docker.models.containers import Container

_DEFAULT_IMAGE = "python:3.11-slim"
_DEFAULT_TIMEOUT = 120
_DEFAULT_MEM_LIMIT = "512m"
_DEFAULT_CPU_QUOTA = 50_000  # 50% of one core (100_000 = 1 full core)
_DEFAULT_PIDS_LIMIT = 64


class DockerSandbox(BaseSandbox):
    """Isolated Docker container sandbox.

    The container is started lazily on the first ``execute()`` call and torn
    down on ``close()`` / context-manager exit.  No host paths are mounted —
    file I/O goes through tar streams (``put_archive`` / ``get_archive``).
    """

    def __init__(
        self,
        *,
        image: str = _DEFAULT_IMAGE,
        network_access: bool = False,
        mem_limit: str = _DEFAULT_MEM_LIMIT,
        cpu_quota: int = _DEFAULT_CPU_QUOTA,
        pids_limit: int = _DEFAULT_PIDS_LIMIT,
        timeout: int = _DEFAULT_TIMEOUT,
        extra_run_kwargs: dict | None = None,
    ) -> None:
        self._image = image
        self._network_mode = "bridge" if network_access else "none"
        self._mem_limit = mem_limit
        self._cpu_quota = cpu_quota
        self._pids_limit = pids_limit
        self._timeout = timeout
        self._extra_run_kwargs = extra_run_kwargs or {}
        self._sandbox_id = f"deepagents-{uuid.uuid4().hex[:8]}"
        self._container: Container | None = None
        self._client: docker_module.DockerClient | None = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def _get_container(self) -> Container:
        if self._container is not None:
            return self._container

        import docker  # deferred so import errors surface at runtime, not import time

        self._client = docker.from_env()
        self._container = self._client.containers.run(
            self._image,
            command="sleep infinity",
            detach=True,
            name=self._sandbox_id,
            network_mode=self._network_mode,
            mem_limit=self._mem_limit,
            cpu_quota=self._cpu_quota,
            pids_limit=self._pids_limit,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            **self._extra_run_kwargs,
        )
        return self._container

    def close(self) -> None:
        """Stop and remove the container."""
        if self._container is not None:
            try:
                self._container.remove(force=True)
            except Exception:  # noqa: BLE001
                pass
            self._container = None
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    def __enter__(self) -> DockerSandbox:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # BaseSandbox abstract interface
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self._sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        container = self._get_container()
        effective_timeout = timeout if timeout is not None else self._timeout

        result_holder: queue.Queue[tuple[int | None, str]] = queue.Queue()

        def _run() -> None:
            try:
                exit_code, raw = container.exec_run(
                    ["/bin/sh", "-c", command],
                    demux=False,
                    stdin=False,
                )
                output = raw.decode("utf-8", errors="replace") if raw else "<no output>"
                result_holder.put((exit_code, output))
            except Exception as exc:  # noqa: BLE001
                result_holder.put((1, f"Error: {exc}"))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=effective_timeout)

        if t.is_alive():
            return ExecuteResponse(
                output=f"Error: command timed out after {effective_timeout}s",
                exit_code=124,
            )

        exit_code, output = result_holder.get()
        return ExecuteResponse(output=output, exit_code=exit_code)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        container = self._get_container()
        responses: list[FileUploadResponse] = []

        for path, content in files:
            try:
                dir_path = os.path.dirname(path) or "/"
                container.exec_run(["mkdir", "-p", dir_path])

                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w") as tar:
                    info = tarfile.TarInfo(name=os.path.basename(path))
                    info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))
                buf.seek(0)

                container.put_archive(dir_path, buf)
                responses.append(FileUploadResponse(path=path))
            except Exception as exc:  # noqa: BLE001
                responses.append(FileUploadResponse(path=path, error=cast(FileOperationError, str(exc))))

        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        container = self._get_container()
        responses: list[FileDownloadResponse] = []

        for path in paths:
            try:
                stream, _ = container.get_archive(path)
                raw = b"".join(stream)
                with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                    members = tar.getmembers()
                    if not members:
                        responses.append(FileDownloadResponse(path=path, error="file_not_found"))
                        continue
                    f = tar.extractfile(members[0])
                    if f is None:
                        responses.append(FileDownloadResponse(path=path, error="is_directory"))
                        continue
                    responses.append(FileDownloadResponse(path=path, content=f.read()))
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if "no such" in msg or "not found" in msg:
                    responses.append(FileDownloadResponse(path=path, error="file_not_found"))
                else:
                    responses.append(FileDownloadResponse(path=path, error=cast(FileOperationError, str(exc))))

        return responses
