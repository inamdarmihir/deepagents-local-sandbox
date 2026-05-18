# deepagents-local-sandbox

> Free, isolated local sandbox backends for the [deepagents](https://pypi.org/project/deepagents/) SDK.
> Run agent-generated code in a hardened container or Linux namespace — nothing leaves your machine.

![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue?logo=python&logoColor=white)
![PyPI](https://img.shields.io/pypi/v/deepagents-local-sandbox?logo=pypi&logoColor=white&color=blue)
![License](https://img.shields.io/badge/license-MIT-green)
![deepagents](https://img.shields.io/badge/deepagents-%3E%3D0.5-purple)
![Docker](https://img.shields.io/badge/docker-%3E%3D7.0-2496ED?logo=docker&logoColor=white)
![Linux](https://img.shields.io/badge/bubblewrap-linux%20only-orange?logo=linux&logoColor=white)

---

## Overview

| Backend | Platform | Requires |
|---|---|---|
| `DockerSandbox` | Cross-platform | Docker Engine / Docker Desktop |
| `BubblewrapSandbox` | Linux only | `bubblewrap` package, no Docker needed |

`auto()` probes the host and picks the strongest available backend (Docker → Bubblewrap). An exception is raised if neither is available.

---

## Installation

```bash
pip install deepagents-local-sandbox
```

Pick your model provider:

```bash
# Anthropic (Claude)
pip install "deepagents-local-sandbox[anthropic]"

# OpenAI (GPT-4o)
pip install "deepagents-local-sandbox[openai]"

# Ollama — Llama, Mistral, and other local models
pip install "deepagents-local-sandbox[ollama]"

# All providers at once
pip install "deepagents-local-sandbox[all-providers]"
```

---

## Quick Start

```python
from langchain_anthropic import ChatAnthropic
from deepagents import create_deep_agent
from deepagents_local_sandbox import auto

model = ChatAnthropic(model="claude-sonnet-4-6")

with auto(network_access=False) as sandbox:
    agent = create_deep_agent(model=model, backend=sandbox)
    result = agent.invoke({
        "messages": [{"role": "user", "content": "Write hello.py and run it"}]
    })
    print(result["messages"][-1].content)
```

---

## Backends

### 🐳 `DockerSandbox`

Starts a Docker container on first use. All file I/O is streamed through tar archives — no host paths are mounted.

```python
from deepagents_local_sandbox import DockerSandbox

with DockerSandbox(
    image="python:3.11-slim",   # any image with /bin/sh
    network_access=False,       # True to allow outbound network
    mem_limit="512m",           # memory cap
    cpu_quota=50_000,           # 50% of one CPU core (100_000 = 1 full core)
    pids_limit=64,              # max processes
    timeout=120,                # per-command timeout in seconds
) as sandbox:
    resp = sandbox.execute("python -c \"print('hi')\"")
    print(resp.output)          # hi
    print(resp.exit_code)       # 0
```

**Security controls applied automatically:**

- All Linux capabilities dropped (`--cap-drop ALL`)
- `no-new-privileges` security option
- Network isolated to `none` mode by default

---

### 🫧 `BubblewrapSandbox`

Spawns a fresh `bwrap` process per command. No Docker required. Files are exchanged via a host temp directory that is bind-mounted as `/workspace` inside the sandbox. Commands execute with `/workspace` as their working directory.

```python
from deepagents_local_sandbox import BubblewrapSandbox

with BubblewrapSandbox(
    network_access=False,              # True to allow outbound network
    timeout=120,                       # per-command timeout in seconds
    workspace="/tmp/my-workspace",     # optional; auto-created + cleaned if omitted
) as sandbox:
    sandbox.upload_files([("/workspace/hello.py", b"print('hi')")])
    resp = sandbox.execute("python hello.py")   # relative to /workspace
    print(resp.output)   # hi
```

**Security controls applied automatically:**

- Separate user, PID, IPC, and (optionally) network namespaces
- Read-only bind mounts for system directories
- Private `/tmp` tmpfs
- Network namespace isolated by default

> **Note:** The bubblewrap backend maps file paths under `/workspace` to the host temp directory. Paths outside `/workspace` (e.g. `/tmp/foo.py`) are stored relative to the workspace root on the host but are not accessible at those paths inside the sandbox.

---

### ⚡ `auto()`

Selects the strongest available backend transparently. All keyword arguments are forwarded to the chosen backend constructor.

```python
from deepagents_local_sandbox import auto

with auto(network_access=False, timeout=60) as sandbox:
    ...
```

Docker-specific options are silently ignored by bubblewrap and vice versa when passed via `auto()`. Use the concrete classes if you need exact control.

---

## Model Provider Examples

```python
# Anthropic (Claude)
from langchain_anthropic import ChatAnthropic
model = ChatAnthropic(model="claude-sonnet-4-6")

# OpenAI (GPT-4o)
from langchain_openai import ChatOpenAI
model = ChatOpenAI(model="gpt-4o")

# Azure OpenAI
from langchain_openai import AzureChatOpenAI
model = AzureChatOpenAI(azure_deployment="gpt-4o")

# Ollama (local, no API key required)
from langchain_ollama import ChatOllama
model = ChatOllama(model="llama3.2")
```

---

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | Core runtime |
| `deepagents` | ≥ 0.5 | Agent orchestration SDK |
| `docker` | ≥ 7.0 | Required for `DockerSandbox` only |
| `bubblewrap` | system package | Required for `BubblewrapSandbox`, Linux only |
| Unprivileged user namespaces | — | Required for `BubblewrapSandbox` |

---

## Development

```bash
git clone <repo>
cd deepagents-local-sandbox
pip install -e ".[dev,anthropic]"
pytest tests/
```

Tests that require Docker or bubblewrap are skipped automatically when the backend is unavailable.

---

## License

MIT © deepagents-local-sandbox contributors
