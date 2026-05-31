# multi-lang-mcp

A multi-language MCP (Model Context Protocol) server that gives Claude a growing set of real-world tools — written in Python, PowerShell, Node.js, and Java.

## What it does

Most AI tool servers are locked to a single language. This project acts as a gateway: a lightweight Python MCP server receives tool calls from Claude, then dispatches each one to the right runtime depending on what the tool needs to do.

```
Claude
  ↓
Python MCP Server (FastMCP)
  ↓
  ├── Python tools    — file I/O, web fetching, downloads
  ├── PowerShell tools — Windows services, system info
  ├── Node.js tools   — npm registry queries, JS ecosystem
  └── Java tools      — JVM-based processing
```

## Current tools

| Tool | Runtime | What it does |
|---|---|---|
| `read_file` | Python | Read a local file |
| `download_file` | Python | Download a file from a URL |
| `get_clean_webpage` | Python | Fetch and clean webpage content |
| `web_search` | Python | DuckDuckGo web search |
| `youtube_download` | Python | Download YouTube video/audio |
| `npm_package_info` | Node.js | Query npm registry metadata |
| `windows_services` | PowerShell | List Windows services |
| `java_tool` | Java | JVM-based tool execution |

## How it works

Each tool script follows a simple contract: accept input as CLI args or stdin JSON, return a `{"success": true/false, ...}` JSON object on stdout. The MCP server validates every call against a security allowlist before execution — no arbitrary shell commands, no free-form code execution.

## Telegram tool architecture

Telegram tools enforce two rules that are verified by automated tests on every run:

**1 — Single point of security check.**
All Telegram tools must obtain their connection through `get_client(channel)` in `shared/telegram_config.py`. This is the only place that checks the enable/disable flag, the channel whitelist/blacklist, and the credentials. `server.py` contains no Telegram security logic — it only routes the call.

```
telegram_download.py
  └── get_client(channel)          ← one gate, all checks here
        ├── TELEGRAM_TOOLS_ENABLED?
        ├── channel ACL (config/telegram_channels.json)?
        ├── credentials present?
        └── returns TelegramClient or (None, error)
```

**2 — Tool scripts must not read `.env`.**
Credentials (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`) are private to `shared/telegram_config.py`. Tool scripts import only `get_client` — never credentials directly. An automated test fails the build if any tool script violates this.

**Adding a new Telegram tool:** see `CLAUDE.md → Telegram Tools — Connection Gate` for the required code pattern.

## Roadmap

This repo is actively updated with new tools for Claude as useful capabilities come up. The goal is to keep expanding what Claude can do in practice — file system operations, system automation, web interaction, and beyond.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

Then add to Claude Code:
```
claude mcp add -s user multi-lang-mcp -- python server.py
```
