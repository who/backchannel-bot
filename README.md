# backchannel-bot

A hacky Discord back channel for remote communication with Claude Code CLI

## Overview

**backchannel-bot** is a lightweight Discord bot that bridges Discord chat with Claude Code CLI on your local machine. This enables remote interaction with Claude from anywhere via Discord—from your phone, another computer, wherever—treating the bot as a transparent relay layer between Discord and Claude.

> **🚨 SECURITY WARNING 🚨**
>
> This is alpha-quality, hacky software with **no security hardening**. Anyone with access to your Discord bot token can execute Claude Code prompts on your machine. Do not use this on shared systems, with sensitive data, or in any environment where security matters. You have been warned.

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
                        └──────────────────────────────────────┘
```

Messages are sent via `claude -p <prompt>` (print mode), which runs Claude Code headlessly and returns clean text output.

The bot runs on the same machine as Claude Code CLI. No SSH, no VPN—just local process execution. The only network traffic is outbound HTTPS to Discord's API.

### User Flow

1. **Setup (One-time):** Create Discord bot, ensure Claude Code CLI is installed, start backchannel-bot
2. **Usage:** Send a message in Discord → Bot runs `claude -p` → Claude responds → Bot sends response back to Discord

### Typical Workflow: Continue From Where You Left Off

The core use case is picking up a Claude session remotely:

1. **Start a Claude session on your dev machine:**
   ```bash
   cd /path/to/your/project
   claude
   # Work with Claude interactively...
   ```

2. **When ready to leave, open a new terminal and start the bot from your project directory:**
   ```bash
   cd /path/to/your/project  # Directory where your Claude session is running
   uv run --project /path/to/backchannel-bot python -m backchannel_bot.main
   ```
   Replace `/path/to/backchannel-bot` with wherever you cloned this repo.

3. **Walk away** — continue via Discord from your phone or another device

**Why it works:** By default, `CLAUDE_SESSION_MODE=continue` uses `claude -p --continue`, which continues the most recent Claude session in the current working directory. Since you start the bot from the same directory as your original session, it automatically connects to that conversation.

**Important:** The bot must be started from the same directory where you ran your original Claude session.

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

### 2. Configure Environment Variables

Copy the sample environment file and edit it with your values:

```bash
cp .env.sample .env
# Edit .env with your Discord bot token
```

The `.env` file supports these variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | Your Discord bot token |
| `DISCORD_CHANNEL_ID` | No | Restrict bot to one channel (recommended) |
| `DISCORD_ALLOWED_USER_ID` | No | Restrict bot to one user (recommended) |
| `CLAUDE_SESSION_MODE` | No | Session continuation mode (default: `continue`). See [Session Continuation](#session-continuation) |

### 3. Run the Bot

```bash
# Clone and install (one-time setup)
git clone https://github.com/who/backchannel-bot.git /path/to/backchannel-bot
cd /path/to/backchannel-bot
uv sync

# Run the bot from your project directory
cd /path/to/your/project
uv run --project /path/to/backchannel-bot python -m backchannel_bot.main
```

### 4. Test It

Send a message in your Discord channel. The bot will relay it to Claude and send back the response.

**Available commands:**
- `!session` — List recent Claude sessions and view/change session mode
- `!session <id>` — Switch to resume a specific session by its UUID

## Session Continuation

By default, the bot continues the most recent Claude Code session in the working directory. This is the core use case: you're working in Claude on your dev machine, start the bot, walk away, and the bot continues that same conversation.

### Session Modes

Set `CLAUDE_SESSION_MODE` in your `.env` file:

| Mode | Description |
|------|-------------|
| `continue` | (Default) Continue the most recent session in the directory |
| `fresh` | Start a new session each time |
| `resume:<session_id>` | Resume a specific session by UUID |

### Managing Sessions

Use `!session` in Discord to manage sessions at runtime:

```
!session                    # List recent sessions
!session continue           # Switch to continue mode
!session fresh              # Switch to fresh mode
!session abc12345-...       # Resume specific session (full UUID)
```

The `!session` command shows recent sessions with timestamps and the first prompt, making it easy to find and resume a specific conversation.

## Ortus Automation

This project was scaffolded with [Ortus](https://github.com/who/ortus), which provides AI-powered development workflows including PRD-to-issues decomposition and automated implementation loops. See the `ortus/` directory for scripts and prompts.

## Tech Stack

- **Language**: Python
- **Package Manager**: uv
- **Linter**: ruff

## License

MIT
