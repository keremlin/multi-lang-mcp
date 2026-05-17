# AiTools — Multi-Language MCP Server

## What This Project Is

A Python-based MCP (Model Context Protocol) gateway that exposes tools written in multiple languages (Python, PowerShell, Node.js, Java) to Claude and other AI models.

```
Claude
   ↓
Python MCP Server  (server.py — FastMCP)
   ↓
Tool Dispatcher (shared/ adapters)
   ├── PowerShell tools  (tools/powershell/)
   ├── Python tools      (tools/python/)
   ├── Node.js tools     (tools/node/)
   └── Java tools        (tools/java/)
```

## Folder Structure

```
multi-mcp/
├── server.py                        # MCP entry point (FastMCP)
├── requirements.txt
├── config/
│   └── tools.json                   # Tool registry / metadata
├── shared/
│   ├── runner.py                    # Core subprocess executor
│   ├── powershell_runner.py
│   ├── python_runner.py
│   ├── node_runner.py
│   └── java_runner.py
└── tools/
    ├── python/
    │   └── read_file.py
    ├── powershell/
    │   └── services.ps1
    ├── node/
    │   └── npm_info.js
    └── java/
        ├── pom.xml
        ├── src/main/java/Main.java
        └── build/ToolRunner.jar     # produced by: cd tools/java && mvn package
```

## Setup

```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install MCP SDK
pip install -r requirements.txt

# 3. (Optional) Build Java tool
cd tools/java
mvn package          # outputs tools/java/build/ToolRunner.jar
cd ../..

# 4. Run the server
python server.py
```

## Adding a New Tool

1. Write the tool script in the appropriate `tools/<runtime>/` folder.
2. The script **must** output only valid JSON to stdout:
   ```json
   { "success": true, "data": { ... } }
   { "success": false, "error": "message" }
   ```
3. Register the tool in `server.py` using the correct runner from `shared/`.
4. Add metadata to `config/tools.json`.

## Tool Communication Contract

Every tool, regardless of language, must:

| Aspect | Rule |
|---|---|
| Input | CLI args **or** JSON on stdin |
| Output | JSON to **stdout only** |
| Errors | `{ "success": false, "error": "..." }` on stdout, non-zero exit |
| Stderr | Used for diagnostic logs only — never parsed |

## Runtime Recommendations

| Use Case | Runtime |
|---|---|
| Core MCP server / glue logic | Python |
| Heavy business logic / JVM ecosystem | Java |
| Windows automation / system info | PowerShell |
| Web / npm ecosystem queries | Node.js |

## Shared Runner (`shared/runner.py`)

All language adapters call `execute()` from `shared/runner.py`, which:
- Runs the subprocess with a configurable timeout (default 30 s, Java 60 s)
- Captures stdout and stderr separately
- Validates that stdout is valid JSON
- Returns a normalized `{"success": bool, ...}` dict on all code paths

Do **not** bypass `execute()` with raw `subprocess.run` calls in tool code.

## Service Management Scripts

| Script | Purpose | Needs Admin? |
|---|---|---|
| `run_server.ps1` | Start server in SSE mode (foreground, dev use) | No |
| `stop_server.ps1` | Stop server — works for both service and standalone | No |
| `server_status.ps1` | Show service state, process, SSE health, tools, log tail | No |
| `install_service.ps1` | Install as Windows service + switch Claude Code to SSE | **Yes** |
| `uninstall_service.ps1` | Remove service + revert Claude Code to stdio | **Yes** |

### Transport modes

| Mode | When | Claude Code config |
|---|---|---|
| **stdio** (default) | Claude Code spawns on-demand; no persistent process | `claude mcp add -s user multi-lang-mcp -- python server.py` |
| **SSE** (service) | Persistent; Windows starts on boot | `claude mcp add -s user --transport sse multi-lang-mcp http://127.0.0.1:8080/sse` |

`install_service.ps1` switches Claude Code to SSE automatically.
`uninstall_service.ps1` reverts it back to stdio automatically.

### Windows service internals

`service.py` uses `pywin32` (already in requirements) to wrap the server as a proper Windows service (`MultiLangMCP`). The service spawns `server.py --transport sse --host 127.0.0.1 --port 8080` with `cwd` pinned to the project root.

To check service status in Windows:
```powershell
Get-Service MultiLangMCP
sc.exe query MultiLangMCP   # raw Win32 status
```

To tail live logs while the service is running:
```powershell
Get-Content logs\server.log -Wait -Tail 50
```

---

## Logging

```
logs/
└── server.log    ← rotating, max 5 MB × 3 backups
```

| Channel | Purpose |
|---|---|
| `logs/server.log` | All tool calls, durations, errors — structured, timestamped |
| `stderr` | Interpreter-level diagnostics only — never parsed by anything |
| `stdout` | **Reserved for JSON tool responses** — never write log lines here |

Logging is initialized in `server.py` via `shared/logging_config.py`. Every call through `shared/runner.py` is automatically logged with:
- tool label and runtime
- wall-clock duration (ms precision)
- exit code and stderr on failure

**Never add `print()` statements** anywhere in `shared/` or `server.py`. Use `logging.getLogger(__name__)` instead. Tools under `tools/` write to stdout only (their JSON response) and may write diagnostics to stderr.

To tail live logs on Windows:

```powershell
Get-Content logs\server.log -Wait -Tail 50
```

---

## Tool Design Rules

Each tool must:

| Rule | Rationale |
|---|---|
| Perform **one responsibility** | Composability — Claude combines tools, not monoliths |
| Be **deterministic** when possible | Reproducible agent runs; easier to test |
| **Avoid hidden side effects** | Side effects that aren't in the tool name violate the principle of least surprise |
| **Support timeout handling** | Set via the runner; tools must not block indefinitely |
| **Return structured JSON** | `{"success": bool, ...}` — the universal contract |
| **Not depend on interactive prompts** | Tools run headlessly — stdin is for data, not user interaction |
| **Write diagnostics to stderr only** | stdout is reserved for the JSON response |
| **Be registered in `config/tools.json`** | Required for security allowlist enforcement |

These rules apply to tools in **all runtimes** (Python, PowerShell, Node.js, Java). When reviewing or generating a new tool, check it against every row above before adding it to `server.py`.

---

## Security Rules

**Never expose unrestricted execution tools.** Every tool must have a narrow, explicit purpose.

### Forbidden patterns

```python
# BAD — never add these
execute_shell(command: str)
run_anything(cmd: str)
run_cmd(command: str)
```

Any tool that accepts a free-form shell command, arbitrary PowerShell, or unrestricted `ProcessBuilder`/`subprocess` call is prohibited. This prevents the "AI can run everything" failure mode.

### Required pattern

All tool scripts must be **registered in `config/tools.json`** before they can execute. The `shared/security.py` module enforces this at runtime via `validate_tool_path()`, which is called in every language adapter before the subprocess is started. Adding a script to `tools/` but not to `tools.json` will raise `ValueError` and block execution.

```
GOOD tools:           BAD tools:
get_windows_services  run_cmd("...")
read_file             execute_shell(command)
git_status            powershell_eval(script_text)
npm_package_info      java_exec(class_name)
```

### Security module

`shared/security.py` enforces:
1. **Allowlist** — path must appear in `config/tools.json` under `script` or `jar`
2. **Traversal prevention** — `..` in any path part is rejected
3. **Root confinement** — resolved path must stay within the project root

The allowlist is loaded once at import time. Restart the server after editing `tools.json`.

---

## Schema Contract

Every tool **should** provide input and output schemas under `schemas/`:

```
schemas/
├── read_file.input.json
├── read_file.output.json
├── services.input.json
├── services.output.json
├── npm_info.input.json
├── npm_info.output.json
├── java_tool.input.json
└── java_tool.output.json
```

Schemas use **JSON Schema draft-07**. All output schemas enforce the `{"success": bool, ...}` envelope via `oneOf` (success branch / error branch).

LLMs produce far more reliable tool calls when given explicit schemas. When adding a new tool, create both `<name>.input.json` and `<name>.output.json` alongside the implementation.

---

## Tests

Run with:

```powershell
.venv\Scripts\pytest tests\ -v
```

Test files and what they cover:

| File | Covers |
|---|---|
| `tests/test_runner.py` | `shared/runner.py` — JSON validation, timeout, missing exe, non-zero exit, stdin pass-through |
| `tests/test_python_runner.py` | Security allowlist enforcement — unregistered path, traversal, root escape |
| `tests/test_tools_registry.py` | `config/tools.json` integrity — required fields, no duplicates, script files exist |
| `tests/test_read_file.py` | Integration: `tools/python/read_file.py` — happy path, missing file, no args |

When adding a new tool, add a corresponding `tests/test_<tool_name>.py` with at least: happy path, missing input, and invalid input.

---

## Key Conventions

- All tools live under `tools/<runtime>/`.
- Shared infrastructure lives under `shared/`.
- `server.py` only wires MCP tool names to runner calls — no business logic.
- Timeouts are set per-runner: Python/PowerShell/Node 30 s, Java 60 s.
- The Java build artifact goes in `tools/java/build/ToolRunner.jar` (set by `pom.xml`).
