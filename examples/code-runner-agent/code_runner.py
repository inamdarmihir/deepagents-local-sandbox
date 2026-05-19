#!/usr/bin/env python3
"""
Code Runner Agent
=================

Tutorial example for deepagents-local-sandbox.
Mirrors the content-builder-agent pattern from
https://github.com/langchain-ai/deepagents/tree/main/examples/content-builder-agent
but uses an isolated Docker/Bubblewrap sandbox as the backend instead of
the plain FilesystemBackend.

Key differences from content-builder-agent
-------------------------------------------
| aspect            | content-builder-agent         | this example                     |
|-------------------|-------------------------------|----------------------------------|
| backend           | FilesystemBackend(root_dir)   | deepagents_local_sandbox.auto()  |
| code execution    | none (file-write only)        | full shell / Python execution    |
| isolation         | host filesystem               | Docker container / bwrap ns      |
| network           | open                          | isolated (network_access=False)  |

Structure (mirrors content-builder-agent)
------------------------------------------
  code-runner-agent/
  ├── AGENTS.md                   ← agent memory (system prompt)
  ├── subagents.yaml              ← subagent definitions (loaded below)
  ├── skills/
  │   └── execute-code/
  │       └── SKILL.md           ← code execution workflow
  └── code_runner.py              ← this file

Usage
-----
    # With uv (recommended)
    cd examples/code-runner-agent
    uv run python code_runner.py "Write a Python script that prints the Fibonacci sequence"

    # With pip
    pip install deepagents-local-sandbox[anthropic] pyyaml rich
    ANTHROPIC_API_KEY=... python code_runner.py "Compute primes up to 100 and print them"

Environment variables
---------------------
    ANTHROPIC_API_KEY   — required (Claude model)
    SANDBOX_BACKEND     — optional: "docker" | "bubblewrap" | "auto" (default: "auto")
    NETWORK_ACCESS      — optional: "true" to allow outbound internet inside sandbox
"""

import asyncio
import os
import sys
from pathlib import Path

import yaml
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner

from deepagents import create_deep_agent

# ── sandbox backend ──────────────────────────────────────────────────────────

def _build_sandbox():
    """
    Select and configure the sandbox backend.

    Override with the SANDBOX_BACKEND env var:
      - "docker"      → DockerSandbox (requires Docker daemon)
      - "bubblewrap"  → BubblewrapSandbox (Linux only, no Docker)
      - "auto"        → auto-detect (default)
    """
    network_access = os.environ.get("NETWORK_ACCESS", "false").lower() == "true"
    backend_choice = os.environ.get("SANDBOX_BACKEND", "auto").lower()

    if backend_choice == "docker":
        from deepagents_local_sandbox import DockerSandbox
        return DockerSandbox(
            image="python:3.11-slim",
            network_access=network_access,
            mem_limit="512m",
            cpu_quota=50_000,      # 50 % of one CPU core
            pids_limit=64,
            timeout=120,
        )
    elif backend_choice == "bubblewrap":
        from deepagents_local_sandbox import BubblewrapSandbox
        return BubblewrapSandbox(
            network_access=network_access,
            timeout=120,
        )
    else:
        from deepagents_local_sandbox import auto
        return auto(network_access=network_access, timeout=120)


# ── subagent loader (same pattern as content-builder-agent) ──────────────────

EXAMPLE_DIR = Path(__file__).parent


def load_subagents(config_path: Path) -> list:
    """Load subagent definitions from YAML.

    NOTE: deepagents does not natively load subagents from files.
    We use this small helper (borrowed from content-builder-agent) to
    keep configuration separate from code.  You can also define subagents
    inline inside create_deep_agent().
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    subagents = []
    for name, spec in config.items():
        subagent: dict = {
            "name": name,
            "description": spec["description"],
            "system_prompt": spec["system_prompt"],
        }
        if "model" in spec:
            subagent["model"] = spec["model"]
        if "tools" in spec and spec["tools"]:
            # Wire tool names to actual callables here if you add any tools
            # to subagents.  The debugger subagent uses no tools.
            subagent["tools"] = []
        subagents.append(subagent)

    return subagents


# ── agent factory ────────────────────────────────────────────────────────────

def create_code_runner(sandbox):
    """
    Create the code-runner agent.

    Compare with content-builder-agent:

        # content-builder-agent (host filesystem)
        from deepagents.backends import FilesystemBackend
        agent = create_deep_agent(
            memory=["./AGENTS.md"],
            skills=["./skills/"],
            tools=[...],
            subagents=load_subagents("./subagents.yaml"),
            backend=FilesystemBackend(root_dir="./"),
        )

        # THIS EXAMPLE (isolated sandbox)
        from deepagents_local_sandbox import auto
        with auto() as sandbox:
            agent = create_deep_agent(
                memory=["./AGENTS.md"],
                skills=["./skills/"],
                tools=[],                       # sandbox exposes execute + file tools natively
                subagents=load_subagents(...),
                backend=sandbox,                # ← the only change that matters
            )

    The sandbox backend automatically exposes `execute`, `write_file`,
    `read_file`, and related tools to the agent — no extra tool definitions
    required.
    """
    model = ChatAnthropic(model="claude-sonnet-4-5")

    return create_deep_agent(
        model=model,
        memory=["./AGENTS.md"],          # Loaded by MemoryMiddleware into system prompt
        skills=["./skills/"],            # Loaded by SkillsMiddleware on demand
        tools=[],                        # Add custom @tool functions here if needed
        subagents=load_subagents(EXAMPLE_DIR / "subagents.yaml"),
        backend=sandbox,                 # ← deepagents-local-sandbox backend
    )


# ── display helpers (same pattern as content-builder-agent) ──────────────────

console = Console()


class AgentDisplay:
    """Pretty-prints streaming agent messages."""

    def __init__(self):
        self.printed_count = 0
        self.spinner = Spinner("dots", text="Thinking…")

    def update_status(self, status: str):
        self.spinner = Spinner("dots", text=status)

    def print_message(self, msg):
        if isinstance(msg, HumanMessage):
            console.print(Panel(str(msg.content), title="You", border_style="blue"))

        elif isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, list):
                text_parts = [
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                content = "\n".join(text_parts)

            if content and content.strip():
                console.print(Panel(Markdown(content), title="Agent", border_style="green"))

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("name", "unknown")
                    args = tc.get("args", {})
                    if name == "execute":
                        cmd = args.get("command", "")
                        console.print(f"  [bold yellow]>> execute:[/] {cmd[:80]}")
                        self.update_status(f"Running: {cmd[:40]}…")
                    elif name == "write_file":
                        path = args.get("file_path", "file")
                        console.print(f"  [bold cyan]>> write:[/] {path}")
                    elif name == "read_file":
                        path = args.get("file_path", "file")
                        console.print(f"  [bold dim]>> read:[/] {path}")
                    elif name == "task":
                        desc = args.get("description", "delegating…")
                        console.print(f"  [bold magenta]>> subagent:[/] {desc[:60]}…")
                        self.update_status(f"Delegating: {desc[:40]}…")

        elif isinstance(msg, ToolMessage):
            name = getattr(msg, "name", "")
            if name == "execute":
                exit_indicator = "[green]✓[/]" if "exit_code=0" in msg.content else "[red]✗[/]"
                console.print(f"  {exit_indicator} execution complete")
            elif name == "write_file":
                console.print("  [green]✓[/] file written")
            elif name == "task":
                console.print("  [green]✓[/] subagent done")


# ── main ─────────────────────────────────────────────────────────────────────

async def main():
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = "Write a Python script that prints the first 20 Fibonacci numbers, then run it"

    console.print()
    console.print("[bold blue]Code Runner Agent[/] [dim](deepagents + deepagents-local-sandbox)[/]")
    console.print(f"[dim]Task:[/] {task}")
    console.print()

    # The sandbox is a context manager — it starts a container (or bwrap process)
    # on entry and tears it down on exit.
    with _build_sandbox() as sandbox:
        backend_name = type(sandbox).__name__
        console.print(f"[dim]Backend:[/] {backend_name}")
        console.print()

        agent = create_code_runner(sandbox)
        display = AgentDisplay()

        with Live(display.spinner, console=console, refresh_per_second=10, transient=True) as live:
            async for chunk in agent.astream(
                {"messages": [("user", task)]},
                config={"configurable": {"thread_id": "code-runner-demo"}},
                stream_mode="values",
            ):
                if "messages" in chunk:
                    messages = chunk["messages"]
                    if len(messages) > display.printed_count:
                        live.stop()
                        for msg in messages[display.printed_count:]:
                            display.print_message(msg)
                        display.printed_count = len(messages)
                        live.start()
                        live.update(display.spinner)

    console.print()
    console.print("[bold green]✓ Done![/]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/]")
