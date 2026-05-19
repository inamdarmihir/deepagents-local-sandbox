---
name: execute-code
description: Use this skill when asked to write, run, or debug Python code or shell commands
---

# Execute-Code Skill

Follow this workflow whenever you run code inside the sandbox:

## Step 1 — Write the code
Use `write_file` to save the script to `/workspace/<filename>.py` (or `.sh` for shell scripts).

## Step 2 — Execute
Run the script with `execute`:
```
python /workspace/<filename>.py
```
For shell scripts:
```
bash /workspace/<filename>.sh
```

## Step 3 — Check the output
- Exit code `0` means success.
- Any other exit code means failure — read stderr and fix the issue.
- If the fix is non-trivial, delegate to the `debugger` subagent.

## Step 4 — Iterate
Repeat steps 1–3 until the output is correct.

## Step 5 — Save results (optional)
If the task produces a file the user wants to keep, note the `/workspace/` path in your reply.

## Tips
- Install missing packages with `pip install <pkg>` before running code that needs them.
- Use `python -c "import <pkg>"` to quickly check whether a package is available.
- For long-running computations, print progress so you can see the output incrementally.
