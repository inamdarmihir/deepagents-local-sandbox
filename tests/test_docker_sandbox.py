"""Integration tests for DockerSandbox (skipped if Docker is unavailable)."""

import pytest
from deepagents_local_sandbox.detect import _probe_docker

pytestmark = pytest.mark.skipif(
    not _probe_docker(),
    reason="Docker daemon not available",
)


class TestExecute:
    def test_basic_command(self, docker_sb):
        resp = docker_sb.execute("echo hello")
        assert resp.exit_code == 0
        assert "hello" in resp.output

    def test_non_zero_exit_code(self, docker_sb):
        resp = docker_sb.execute("exit 42")
        assert resp.exit_code == 42

    def test_stderr_included_in_output(self, docker_sb):
        resp = docker_sb.execute("echo err >&2")
        assert resp.exit_code == 0
        assert "err" in resp.output

    def test_multiline_output(self, docker_sb):
        resp = docker_sb.execute("printf 'a\\nb\\nc\\n'")
        assert resp.exit_code == 0
        assert resp.output.count("\n") >= 2

    def test_timeout_returns_exit_code_124(self):
        from deepagents_local_sandbox import DockerSandbox
        with DockerSandbox(timeout=2) as sb:
            resp = sb.execute("sleep 60")
        assert resp.exit_code == 124
        assert "timed out" in resp.output.lower()

    def test_per_call_timeout_override(self, docker_sb):
        resp = docker_sb.execute("sleep 60", timeout=2)
        assert resp.exit_code == 124

    def test_network_disabled_by_default(self, docker_sb):
        resp = docker_sb.execute("curl -sf --max-time 3 http://example.com || echo blocked")
        assert resp.exit_code != 0 or "blocked" in resp.output


class TestSandboxId:
    def test_id_format(self):
        from deepagents_local_sandbox import DockerSandbox
        with DockerSandbox() as sb:
            assert sb.id.startswith("deepagents-")
            assert len(sb.id) > len("deepagents-")

    def test_id_unique_per_instance(self):
        from deepagents_local_sandbox import DockerSandbox
        with DockerSandbox() as a, DockerSandbox() as b:
            assert a.id != b.id


class TestFileIO:
    def test_upload_and_execute(self, docker_sb):
        script = b"print('hello from sandbox')"
        uploads = docker_sb.upload_files([("/workspace/hello.py", script)])
        assert uploads[0].error is None

        resp = docker_sb.execute("python /workspace/hello.py")
        assert resp.exit_code == 0
        assert "hello from sandbox" in resp.output

    def test_download_roundtrip(self, docker_sb):
        content = b"roundtrip content"
        docker_sb.upload_files([("/workspace/rt.txt", content)])

        downloads = docker_sb.download_files(["/workspace/rt.txt"])
        assert downloads[0].error is None
        assert downloads[0].content == content

    def test_upload_multiple_files(self, docker_sb):
        files = [
            ("/workspace/a.txt", b"aaa"),
            ("/workspace/b.txt", b"bbb"),
        ]
        uploads = docker_sb.upload_files(files)
        assert all(u.error is None for u in uploads)

        downloads = docker_sb.download_files([f for f, _ in files])
        assert downloads[0].content == b"aaa"
        assert downloads[1].content == b"bbb"

    def test_download_missing_file_reports_error(self, docker_sb):
        downloads = docker_sb.download_files(["/workspace/_nonexistent_xyz.txt"])
        assert downloads[0].error is not None

    def test_nested_directory_upload(self, docker_sb):
        content = b"nested"
        uploads = docker_sb.upload_files([("/workspace/sub/dir/file.txt", content)])
        assert uploads[0].error is None

        resp = docker_sb.execute("cat /workspace/sub/dir/file.txt")
        assert resp.exit_code == 0
        assert b"nested" in resp.output.encode()
