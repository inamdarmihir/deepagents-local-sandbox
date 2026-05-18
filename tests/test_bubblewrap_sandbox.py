"""Integration tests for BubblewrapSandbox (skipped on non-Linux or if bwrap is unavailable)."""

import sys
import pytest
from deepagents_local_sandbox.detect import _probe_bubblewrap

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not _probe_bubblewrap(),
    reason="bubblewrap not available on this host",
)


class TestExecute:
    def test_basic_command(self, bwrap_sb):
        resp = bwrap_sb.execute("echo hello")
        assert resp.exit_code == 0
        assert "hello" in resp.output

    def test_non_zero_exit_code(self, bwrap_sb):
        resp = bwrap_sb.execute("exit 7")
        assert resp.exit_code == 7

    def test_stderr_prefixed(self, bwrap_sb):
        resp = bwrap_sb.execute("echo err >&2")
        assert "[stderr]" in resp.output
        assert "err" in resp.output

    def test_timeout_returns_exit_code_124(self):
        from deepagents_local_sandbox import BubblewrapSandbox
        with BubblewrapSandbox(timeout=2) as sb:
            resp = sb.execute("sleep 60")
        assert resp.exit_code == 124
        assert "timed out" in resp.output.lower()

    def test_per_call_timeout_override(self, bwrap_sb):
        resp = bwrap_sb.execute("sleep 60", timeout=2)
        assert resp.exit_code == 124

    def test_working_directory_is_workspace(self, bwrap_sb):
        resp = bwrap_sb.execute("pwd")
        assert resp.exit_code == 0
        assert "/workspace" in resp.output

    def test_network_disabled_by_default(self, bwrap_sb):
        resp = bwrap_sb.execute(
            "python3 -c \""
            "import socket, sys\n"
            "try:\n"
            "    socket.setdefaulttimeout(2)\n"
            "    socket.create_connection(('8.8.8.8', 53))\n"
            "    sys.exit(0)\n"
            "except OSError:\n"
            "    sys.exit(1)\n"
            "\""
        )
        assert resp.exit_code != 0


class TestSandboxId:
    def test_id_format(self, bwrap_sb):
        assert bwrap_sb.id.startswith("bwrap-")
        assert len(bwrap_sb.id) > len("bwrap-")

    def test_id_unique_per_instance(self):
        from deepagents_local_sandbox import BubblewrapSandbox
        with BubblewrapSandbox() as a, BubblewrapSandbox() as b:
            assert a.id != b.id


class TestFileIO:
    def test_upload_and_execute(self, bwrap_sb):
        script = b"print('hello from bwrap')"
        uploads = bwrap_sb.upload_files([("/workspace/hello.py", script)])
        assert uploads[0].error is None

        resp = bwrap_sb.execute("python3 hello.py")
        assert resp.exit_code == 0
        assert "hello from bwrap" in resp.output

    def test_download_roundtrip(self, bwrap_sb):
        content = b"roundtrip bwrap"
        bwrap_sb.upload_files([("/workspace/rt.txt", content)])

        downloads = bwrap_sb.download_files(["/workspace/rt.txt"])
        assert downloads[0].error is None
        assert downloads[0].content == content

    def test_files_persist_between_execute_calls(self, bwrap_sb):
        bwrap_sb.upload_files([("/workspace/persist.txt", b"persistent data")])
        resp1 = bwrap_sb.execute("cat /workspace/persist.txt")
        resp2 = bwrap_sb.execute("cat /workspace/persist.txt")
        assert "persistent data" in resp1.output
        assert "persistent data" in resp2.output

    def test_download_missing_file_reports_error(self, bwrap_sb):
        downloads = bwrap_sb.download_files(["/workspace/_nonexistent_xyz.txt"])
        assert downloads[0].error == "file_not_found"

    def test_download_directory_reports_error(self, bwrap_sb, tmp_path):
        import os
        os.makedirs(str(tmp_path / "subdir"), exist_ok=True)
        downloads = bwrap_sb.download_files(["/workspace/subdir"])
        assert downloads[0].error == "is_directory"


class TestWorkspaceCleanup:
    def test_auto_cleanup_on_close(self, tmp_path):
        from deepagents_local_sandbox import BubblewrapSandbox
        ws = str(tmp_path / "ws")
        import os
        os.makedirs(ws)
        with BubblewrapSandbox(workspace=ws) as sb:
            sb.upload_files([("/workspace/f.txt", b"data")])
        # workspace provided by caller — NOT cleaned up by the sandbox
        assert os.path.exists(ws)

    def test_tmpdir_cleaned_up_on_close(self):
        from deepagents_local_sandbox import BubblewrapSandbox
        import os
        sb = BubblewrapSandbox()
        tmpdir = sb._tmpdir
        sb.close()
        assert not os.path.exists(tmpdir)
