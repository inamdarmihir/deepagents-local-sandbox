"""Auto-detect the best available local sandbox backend."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from typing import Literal

BackendName = Literal["docker", "bubblewrap"]


@lru_cache(maxsize=1)
def best_backend() -> BackendName:
    """Return the strongest available backend name, cached after first probe."""
    if _probe_docker():
        return "docker"
    if _probe_bubblewrap():
        return "bubblewrap"
    raise RuntimeError(
        "No supported sandbox backend found.\n"
        "  • Docker: install Docker Desktop or Docker Engine and ensure the daemon is running.\n"
        "  • Bubblewrap (Linux only): install via 'apt install bubblewrap' or 'dnf install bubblewrap'."
    )


def _probe_docker() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _probe_bubblewrap() -> bool:
    try:
        result = subprocess.run(
            ["bwrap", "--version"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False
        # Verify user namespaces are available (required for --unshare-user)
        ns_path = "/proc/sys/kernel/unprivileged_userns_clone"
        try:
            with open(ns_path) as f:
                if f.read().strip() == "0":
                    return False
        except OSError:
            pass  # file absent means namespaces are enabled by default
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
