# Code Runner Agent

A tutorial example showing how to use **deepagents-local-sandbox** with deepagents —
the same way the
[content-builder-agent](https://github.com/langchain-ai/deepagents/tree/main/examples/content-builder-agent)
is structured, but with an **isolated Docker/Bubblewrap sandbox** as the backend instead of
the plain `FilesystemBackend`.

---

## What This Example Demonstrates

- **Memory** (`AGENTS.md`) — persistent context loaded into the system prompt
- **Skills** (`skills/*/SKILL.md`) — task-specific workflows loaded on demand
- **Subagents** (`subagents.yaml`) — specialized agents for delegated tasks
- **`deepagents-local-sandbox`** — the key addition: code the agent writes is
  executed inside a hardened container or Linux namespace, not directly on your machine

---

## Quick Start

```bash
# 1. Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 2. Run with uv (installs deps automatically)
cd examples/code-runner-agent
uv run python code_runner.py "Write a Python script that prints the first 20 Fibonacci numbers and run it"

# 3. More examples
uv run python code_runner.py "Write and run a script that computes prime numbers up to 1000"
uv run python code_runner.py "Create a CSV with 5 rows of fake data and print it"
```

### Backend Selection

By default `auto()` probes the host and picks Docker → Bubblewrap:

```bash
# Force Docker
SANDBOX_BACKEND=docker uv run python code_runner.py "..."

# Force Bubblewrap (Linux only)
SANDBOX_BACKEND=bubblewrap uv run python code_runner.py "..."

# Allow outbound internet inside the sandbox (off by default)
NETWORK_ACCESS=true uv run python code_runner.py "pip install requests and fetch https://example.com"
```

---

## How It Works

The agent is configured entirely through files on disk — the same three-primitive
pattern used by the content-builder-agent:

```
code-runner-agent/
├── AGENTS.md                    ← Brand voice & behavior guidelines (MemoryMiddleware)
├── subagents.yaml               ← Subagent definitions (loaded by code_runner.py)
├── skills/
│   └── execute-code/
│       └── SKILL.md            ← Code-execution workflow (SkillsMiddleware)
└── code_runner.py               ← Wires it together with deepagents-local-sandbox
```

| File | Purpose | When Loaded |
|------|---------|-------------|
| `AGENTS.md` | Sandbox constraints, agent behavior | Always (system prompt) |
| `subagents.yaml` | Debugger subagent for complex errors | Always (defines `task` tool) |
| `skills/execute-code/SKILL.md` | Write → Execute → Check → Iterate workflow | On demand |

---

## The Key Difference from content-builder-agent

The **only** meaningful code change compared to `content-builder-agent` is the
`backend=` argument to `create_deep_agent()`:

```python
# content-builder-agent  (writes files directly on the host)
from deepagents.backends import FilesystemBackend

agent = create_deep_agent(
    memory=["./AGENTS.md"],
    skills=["./skills/"],
    tools=[generate_cover, generate_social_image],
    subagents=load_subagents("./subagents.yaml"),
    backend=FilesystemBackend(root_dir="./"),   # ← host filesystem
)

# code-runner-agent  (executes code in an isolated sandbox)
from deepagents_local_sandbox import auto

with auto(network_access=False) as sandbox:        # ← isolated sandbox
    agent = create_deep_agent(
        memory=["./AGENTS.md"],
        skills=["./skills/"],
        tools=[],            # sandbox exposes execute + file tools automatically
        subagents=load_subagents("./subagents.yaml"),
        backend=sandbox,     # ← that's the only difference
    )
```

When a sandbox backend is used, deepagents automatically exposes `execute`,
`write_file`, `read_file`, and other file-system tools to the agent — no
extra `@tool` definitions are needed for basic code execution.

---

## Architecture

```python
with auto(network_access=False) as sandbox:
    agent = create_deep_agent(
        model=ChatAnthropic(model="claude-sonnet-4-5"),
        memory=["./AGENTS.md"],            # ← MemoryMiddleware
        skills=["./skills/"],              # ← SkillsMiddleware
        tools=[],                          # ← add custom tools here
        subagents=load_subagents(...),     # ← custom YAML loader (see below)
        backend=sandbox,                   # ← deepagents-local-sandbox
    )
```

**Note on subagents:** deepagents does not natively load subagents from files.
`load_subagents()` is a small helper (identical to the one in content-builder-agent)
that reads `subagents.yaml` and returns the inline dict format expected by
`create_deep_agent()`. You can also define them directly:

```python
subagents=[
    {
        "name": "debugger",
        "description": "Second opinion on failing code...",
        "model": "anthropic:claude-haiku-4-5-20251001",
        "system_prompt": "You are an expert Python debugger...",
        "tools": [],
    }
]
```

**Execution flow:**
1. User message arrives → relevant skill (`execute-code`) is loaded
2. Agent writes a script with `write_file` → runs it with `execute`
3. If the script fails, agent reads the error and fixes it (or delegates to `debugger`)
4. Agent reports results to the user

---

## Customizing

### Change the agent's behavior
Edit `AGENTS.md` to modify the agent's tone, constraints, or priorities.

### Add a new skill
Create `skills/<name>/SKILL.md` with YAML front matter:

```yaml
---
name: data-analysis
description: Use this skill when asked to analyze data files (CSV, JSON, etc.)
---

# Data Analysis Skill

## Step 1 — Read the data ...
```

### Add a subagent
Add to `subagents.yaml`:

```yaml
linter:
  description: Review code for style issues and suggest improvements
  model: anthropic:claude-haiku-4-5-20251001
  system_prompt: |
    You are a Python code reviewer. Point out style issues, potential bugs,
    and suggest cleaner alternatives. Be concise.
  tools: []
```

### Add a custom tool
Define a `@tool` function in `code_runner.py` and pass it to `tools=[]`:

```python
from langchain_core.tools import tool

@tool
def notify_slack(message: str) -> str:
    """Send a notification to the team Slack channel."""
    # ... your implementation
    return "sent"

agent = create_deep_agent(
    ...
    tools=[notify_slack],   # ← add here
    backend=sandbox,
)
```

### Switch model providers

```python
# OpenAI
from langchain_openai import ChatOpenAI
model = ChatOpenAI(model="gpt-4o")

# Azure OpenAI
from langchain_openai import AzureChatOpenAI
model = AzureChatOpenAI(azure_deployment="gpt-4o")

# Ollama (local, no API key)
from langchain_ollama import ChatOllama
model = ChatOllama(model="llama3.2")
```

Install the matching extra:

```bash
pip install "deepagents-local-sandbox[openai]"
pip install "deepagents-local-sandbox[ollama]"
```

### Tune the sandbox

```python
# Docker with custom limits
from deepagents_local_sandbox import DockerSandbox

with DockerSandbox(
    image="python:3.12-slim",   # any image with /bin/sh
    network_access=True,        # allow outbound traffic
    mem_limit="1g",             # 1 GB RAM cap
    cpu_quota=100_000,          # 1 full CPU core
    pids_limit=128,
    timeout=300,                # 5-minute timeout per command
) as sandbox:
    ...

# Bubblewrap (Linux only)
from deepagents_local_sandbox import BubblewrapSandbox

with BubblewrapSandbox(
    network_access=False,
    timeout=120,
    workspace="/tmp/my-agent-workspace",  # reuse a specific directory
) as sandbox:
    ...
```

---

## Comparison with content-builder-agent

| | content-builder-agent | code-runner-agent (this example) |
|---|---|---|
| Backend | `FilesystemBackend` | `deepagents-local-sandbox` |
| Code execution | ✗ (file-write only) | ✓ (full shell + Python) |
| Isolation | Host filesystem | Docker / Bubblewrap namespace |
| Network | Open | Isolated by default |
| Memory (`AGENTS.md`) | ✓ | ✓ |
| Skills (`skills/`) | ✓ | ✓ |
| Subagents (`subagents.yaml`) | ✓ | ✓ |
| Custom tools (`@tool`) | ✓ (image generation) | ✓ (add your own) |
| Structured output files | `blogs/`, `linkedin/` dirs | `/workspace/` inside sandbox |

---

## Security Note

The sandbox severely limits what agent-generated code can do:

- **DockerSandbox** drops all Linux capabilities, enforces `no-new-privileges`,
  and defaults to network isolation (`none` mode).
- **BubblewrapSandbox** creates separate user, PID, IPC, and network namespaces
  and bind-mounts system directories read-only.

Neither backend gives the agent access to your host filesystem or environment
variables. Review any files the agent asks to download before opening them.

---

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | |
| `deepagents` | ≥ 0.5 | Agent orchestration SDK |
| `deepagents-local-sandbox` | ≥ 0.1 | This package |
| `langchain-anthropic` | ≥ 0.3 | Or any other LangChain chat model |
| Docker Engine / Desktop | ≥ 7.0 | Required for `DockerSandbox` |
| `bubblewrap` (system pkg) | — | Required for `BubblewrapSandbox`, Linux only |
| `ANTHROPIC_API_KEY` | — | Set in environment |
