# backchannel-bot

A hacky Discord back channel for remote communication with Claude Code CLI

## Overview

**backchannel-bot** is a lightweight Discord bot that bridges Discord chat with Claude Code CLI on your local machine. This enables remote interaction with Claude from anywhere via Discord—from your phone, another computer, wherever—treating the bot as a transparent relay layer between Discord and Claude.

> **🚨 SECURITY WARNING 🚨**
>
> This is alpha-quality, hacky software with **no security hardening**. Anyone with access to your Discord bot token can execute Claude Code prompts on your machine (and optionally tmux commands via `!raw`). Do not use this on shared systems, with sensitive data, or in any environment where security matters. You have been warned.

### Why?

When away from the development machine, there's no easy way to continue or interact with an ongoing Claude CLI session. Existing solutions require direct terminal access or complex remote desktop setups. A simple Discord-based relay allows asynchronous, mobile-friendly interaction with Claude sessions.

### How It Works

```
┌─────────────┐         ┌──────────────────────────────────────┐
│   Discord   │         │   Dev Machine (Desktop)              │
│   Client    │◄───────►│  ┌─────────────────┐                 │
│  (Mobile/   │ Discord │  │ backchannel-bot │                 │
│   Desktop)  │   API   │  └────────┬────────┘                 │
└─────────────┘         │           │                          │
                        │           ▼                          │
                        │  ┌─────────────────┐                 │
                        │  │  claude -p      │ ◄─ main relay   │
                        │  │  (print mode)   │                 │
                        │  └─────────────────┘                 │
                        │           │                          │
                        │           ▼ (optional, for ! cmds)   │
                        │  ┌─────────────────┐                 │
                        │  │  TMUX Session   │ ◄─ !status,     │
                        │  │                 │    !interrupt,  │
                        │  └─────────────────┘    !raw         │
                        └──────────────────────────────────────┘
```

**Main relay:** Messages are sent via `claude -p <prompt>` (print mode), which runs Claude Code headlessly and returns clean text output—no TMUX session needed for normal operation.

**Control commands:** The `!status`, `!interrupt`, and `!raw` commands require a TMUX session for session inspection and control.

The bot runs on the same machine as Claude Code CLI. No SSH, no VPN—just local process execution. The only network traffic is outbound HTTPS to Discord's API.

### User Flow

1. **Setup (One-time):** Create Discord bot, ensure Claude Code CLI is installed, start backchannel-bot
2. **Usage:** Send a message in Discord → Bot runs `claude -p` → Claude responds → Bot sends response back to Discord
3. **Session Management (optional):** Start a TMUX session to use `!status`, `!interrupt`, and `!raw` commands

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**, give it a name
3. Go to **Bot** in the sidebar, click **Add Bot**
4. Under **Privileged Gateway Intents**, enable **Message Content Intent**
5. Click **Reset Token** and copy your bot token (you'll need this later)
6. Go to **OAuth2 → URL Generator**:
   - Select scopes: `bot`
   - Select permissions: `Send Messages`, `Read Message History`
7. Copy the generated URL and open it to invite the bot to your server
8. Note the channel ID where you want the bot to operate (right-click channel → Copy ID, requires Developer Mode in Discord settings)

### 2. (Optional) Start a TMUX Session

> **Note:** A TMUX session is only required if you want to use the `!status`, `!interrupt`, or `!raw` commands. Normal message relay works without TMUX.

```bash
# Create a named TMUX session
tmux new -s claude-session

# Optionally run something in the session (e.g., Claude CLI for interactive use)
claude

# Detach from TMUX (leave it running in background)
# Press: Ctrl+B, then D
```

### 3. Configure Environment Variables

Copy the sample environment file and edit it with your values:

```bash
cp .env.sample .env
# Edit .env with your Discord bot token and TMUX session name
```

The `.env` file supports these variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | Your Discord bot token |
| `TMUX_SESSION_NAME` | Yes* | Name of your TMUX session (required only for `!` commands) |
| `DISCORD_CHANNEL_ID` | No | Restrict bot to one channel (recommended) |
| `DISCORD_ALLOWED_USER_ID` | No | Restrict bot to one user (recommended) |
| `TMUX_PANE` | No | Pane number for `!` commands (default: `0`) |
| ~~`POLL_INTERVAL_MS`~~ | — | *Deprecated: unused in current architecture* |
| ~~`RESPONSE_STABLE_SECONDS`~~ | — | *Deprecated: unused in current architecture* |
| ~~`OUTPUT_HISTORY_LINES`~~ | — | *Deprecated: unused in current architecture* |

### 4. Run the Bot

```bash
# Install dependencies
uv sync

# Run the bot
uv run python -m backchannel_bot.main
```

### 5. Test It

Send a message in your Discord channel. The bot will relay it to Claude and send back the response.

**Available commands:**
- `!status` — Check if the TMUX session exists and is attached/detached
- `!interrupt` — Send Ctrl+C to the TMUX pane (stop Claude mid-response)
- `!raw <cmd>` — Run arbitrary tmux commands (e.g., `!raw list-windows`)

## Ortus Automation

This project was scaffolded with [Ortus](https://github.com/who/ortus), which provides AI-powered development workflows including PRD-to-issues decomposition and automated implementation loops. See the `ortus/` directory for scripts and prompts.

## Tech Stack

- **Language**: Python
- **Package Manager**: uv
- **Linter**: ruff

## Quick Start

```bash
# Install dependencies
uv sync

# Run the project
uv run python -m app.main

# Run tests
uv run pytest

# Lint code
uv run ruff check .
uv run ruff format --check .
```

## Workflow

This project uses beads (`bd`) for issue tracking and Ralph automation loops for implementation.

### Kickstart Your Feature

Run `./ortus/idea.sh` to start. You'll be asked whether you have a PRD or just an idea:

**Option 1: You have a PRD (non-interactive)**
```bash
./ortus/idea.sh --prd path/to/your-prd.md
```
Your PRD will be automatically decomposed into a beads issue graph:
- Creates an epic with hierarchical implementation tasks
- Sets up proper dependencies between issues
- Uses parallel sub-agents for efficient issue creation
- Runs in automated mode (no permission prompts)

**Option 1b: You have a PRD (interactive)**
```bash
./ortus/idea.sh
# Choose [1] "Yes, I have a PRD"
# Provide the path to your PRD file
```

**Option 2: You have an idea**
```bash
./ortus/idea.sh "Your feature idea"
# Or run ./ortus/idea.sh and choose [2] "Nope, just an idea"
```
Claude will:
1. Expand your idea into a feature description
2. Run an interactive interview to clarify requirements
3. Generate a PRD document
4. Create implementation tasks from the PRD

### Implement with Ralph

Once tasks exist, run the implementation loop:

```bash
./ortus/ralph.sh
```

Ralph picks up tasks and implements them one by one, running tests and committing changes.

### Issue Tracking Commands

```bash
bd list              # List all issues
bd ready             # Show issues ready to work
bd show <id>         # View issue details
bd stats             # Project statistics
```

## Project Structure

```
backchannel-bot/
├── src/                  # Source code
│   └── app/              # Application package
├── tests/                # Test suite
├── ortus/                # Ortus automation scripts and prompts
│   └── prompts/          # AI prompt templates
├── prd/                  # Product requirements documents
├── .beads/               # Issue tracking data
└── .claude/              # Claude Code settings
```

## Repository

[who/backchannel-bot](https://github.com/who/backchannel-bot)

## License

MIT
