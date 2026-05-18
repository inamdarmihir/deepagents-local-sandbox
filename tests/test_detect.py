"""Tests for backend auto-detection (no sandbox runtime required)."""

import pytest
from unittest.mock import patch

from deepagents_local_sandbox.detect import _probe_docker, _probe_bubblewrap, best_backend


def test_probe_docker_returns_bool():
    assert isinstance(_probe_docker(), bool)


def test_probe_bubblewrap_returns_bool():
    assert isinstance(_probe_bubblewrap(), bool)


def test_best_backend_docker_wins():
    with patch("deepagents_local_sandbox.detect._probe_docker", return_value=True):
        best_backend.cache_clear()
        assert best_backend() == "docker"
    best_backend.cache_clear()


def test_best_backend_falls_back_to_bubblewrap():
    with (
        patch("deepagents_local_sandbox.detect._probe_docker", return_value=False),
        patch("deepagents_local_sandbox.detect._probe_bubblewrap", return_value=True),
    ):
        best_backend.cache_clear()
        assert best_backend() == "bubblewrap"
    best_backend.cache_clear()


def test_best_backend_raises_when_nothing_available():
    with (
        patch("deepagents_local_sandbox.detect._probe_docker", return_value=False),
        patch("deepagents_local_sandbox.detect._probe_bubblewrap", return_value=False),
    ):
        best_backend.cache_clear()
        with pytest.raises(RuntimeError, match="No supported sandbox backend"):
            best_backend()
    best_backend.cache_clear()
