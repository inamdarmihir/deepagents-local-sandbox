"""Shared fixtures and skip markers for the sandbox test suite."""

import sys
import pytest

from deepagents_local_sandbox.detect import _probe_docker, _probe_bubblewrap

_docker_available = _probe_docker()
_bwrap_available = sys.platform == "linux" and _probe_bubblewrap()


@pytest.fixture(scope="session")
def docker_sb():
    """Session-scoped DockerSandbox — shared across all Docker tests for speed."""
    if not _docker_available:
        pytest.skip("Docker daemon not available")
    from deepagents_local_sandbox import DockerSandbox
    with DockerSandbox() as sb:
        yield sb


@pytest.fixture
def bwrap_sb(tmp_path):
    """Function-scoped BubblewrapSandbox with a fresh temp workspace."""
    if not _bwrap_available:
        pytest.skip("bubblewrap not available on this host")
    from deepagents_local_sandbox import BubblewrapSandbox
    with BubblewrapSandbox(workspace=str(tmp_path)) as sb:
        yield sb
