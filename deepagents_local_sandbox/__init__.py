"""deepagents-local-sandbox: free, isolated local sandbox backends for deepagents.

Quickstart::

    from deepagents_local_sandbox import auto

    with auto() as sandbox:
        # pass sandbox as backend= to create_deep_agent(...)
        ...

Supported backends (selected automatically):
  - DockerSandbox   — cross-platform, requires Docker
  - BubblewrapSandbox — Linux only, requires bubblewrap, no Docker needed
"""

from __future__ import annotations

from deepagents_local_sandbox.detect import best_backend
from deepagents_local_sandbox.providers.bubblewrap_sandbox import BubblewrapSandbox
from deepagents_local_sandbox.providers.docker_sandbox import DockerSandbox

__all__ = [
    "BubblewrapSandbox",
    "DockerSandbox",
    "auto",
    "best_backend",
]


def auto(**kwargs: object) -> DockerSandbox | BubblewrapSandbox:
    """Return the strongest available sandbox backend on this host.

    Probe order: Docker → Bubblewrap → RuntimeError.

    All keyword arguments are forwarded to the chosen backend constructor.
    Common options accepted by both backends:

    - ``network_access`` (bool, default ``False``) — allow outbound network
    - ``timeout`` (int, default 120) — per-command timeout in seconds

    Docker-only options:
    - ``image`` (str, default ``"python:3.11-slim"``)
    - ``mem_limit`` (str, default ``"512m"``)
    - ``cpu_quota`` (int, default ``50_000``)
    - ``pids_limit`` (int, default ``64``)

    Bubblewrap-only options:
    - ``workspace`` (str | None) — host path to use as /workspace; a
      temporary directory is created and cleaned up if omitted

    Examples::

        # Anthropic
        from langchain_anthropic import ChatAnthropic
        model = ChatAnthropic(model="claude-sonnet-4-6")

        # OpenAI
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(model="gpt-4o")

        # Azure OpenAI
        from langchain_openai import AzureChatOpenAI
        model = AzureChatOpenAI(azure_deployment="gpt-4o", ...)

        # Ollama (local, no API key)
        from langchain_ollama import ChatOllama
        model = ChatOllama(model="llama3.2")

        from deepagents import create_deep_agent
        from deepagents_local_sandbox import auto

        with auto(network_access=False) as sandbox:
            agent = create_deep_agent(model=model, backend=sandbox)
            result = agent.invoke({"messages": [{"role": "user", "content": "Write hello.py and run it"}]})
    """
    backend = best_backend()
    if backend == "docker":
        return DockerSandbox(**kwargs)  # type: ignore[arg-type]
    return BubblewrapSandbox(**kwargs)  # type: ignore[arg-type]
