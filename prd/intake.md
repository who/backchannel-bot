# Product Requirements Document: backchannel-bot

**Version:** 0.1.0-alpha  
**Status:** MVP / Alpha  
**Date:** February 2026  
**Codename:** backchannel-bot  
**Issue Prefix:** `bcb` (for Beads decomposition)

---

## Project Tracking

This PRD will be decomposed into Beads issues using the `bcb-` prefix (e.g., `bcb-001`, `bcb-002`, etc.).

---

## Executive Summary

**backchannel-bot** is a lightweight, hacky Discord bot that bridges Discord chat with an active Claude CLI session running inside TMUX on your local machine. This enables remote interaction with Claude from anywhere via Discord—from your phone, another computer, wherever—treating the bot as a transparent relay layer between Discord and your terminal.

---

## Problem Statement

When away from the development machine, there's no easy way to continue or interact with an ongoing Claude CLI session. Existing solutions require direct terminal access or complex remote desktop setups. A simple Discord-based relay would allow asynchronous, mobile-friendly interaction with Claude sessions.

---

## Goals

- **Primary:** Enable Discord ↔ Claude CLI communication via local TMUX relay
- **Secondary:** Keep it dead simple—MVP quality, minimal features, "it works" engineering
- **Non-Goal:** Production hardening, security audits, multi-user support, high availability

---

## Target User

Single developer (you) accessing your own Claude session remotely via Discord. No multi-tenancy, no public deployment.

---

## System Architecture

```
┌─────────────┐         ┌──────────────────────────────────────┐
│   Discord   │         │   Dev Machine (Desktop)              │
│   Client    │◄───────►│  ┌─────────────────┐                 │
│  (Mobile/   │ Discord │  │ backchannel-bot │◄───┐            │
│   Desktop)  │   API   │  └─────────────────┘    │ local      │
└─────────────┘         │  ┌─────────────────┐    │ tmux       │
                        │  │  TMUX Session   │◄───┘ commands   │
                        │  │  └─► Claude CLI │                 │
                        │  └─────────────────┘                 │
                        └──────────────────────────────────────┘
```

The bot runs on the same machine as the Claude CLI session. No SSH, no VPN—just local TMUX commands. The only network traffic is outbound HTTPS to Discord's API.

---

## Functional Requirements

### FR-1: Discord Bot Core

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | Bot connects to Discord using bot token | Must Have |
| FR-1.2 | Bot listens to messages in a designated channel OR DMs only | Must Have |
| FR-1.3 | Bot responds in the same channel/DM thread | Must Have |
| FR-1.4 | Bot ignores its own messages and other bots | Must Have |
| FR-1.5 | No prefix required—raw messages in dedicated channel go straight to Claude | Must Have |

### FR-2: TMUX Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | Bot runs on same machine as TMUX session | Must Have |
| FR-2.2 | Bot attaches to existing named TMUX session (e.g., `claude-session`) | Must Have |
| FR-2.3 | Bot sends user input to TMUX pane via `tmux send-keys` | Must Have |
| FR-2.4 | Bot captures TMUX pane output via `tmux capture-pane` | Must Have |
| FR-2.5 | Configurable TMUX session name | Must Have |

### FR-3: Message Relay

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | Discord message → send to TMUX pane as input | Must Have |
| FR-3.2 | TMUX pane output → send back to Discord | Must Have |
| FR-3.3 | Handle Claude's streaming output (poll-based capture with reasonable interval) | Must Have |
| FR-3.4 | Basic output chunking for Discord's 2000-char message limit | Must Have |
| FR-3.5 | "Typing" indicator while waiting for Claude response | Must Have |
| FR-3.6 | Detect when Claude is "done" responding (heuristic: output stable for N seconds) | Must Have |

### FR-4: Session Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | Command to check TMUX session status (e.g., `!status`) | Should Have |
| FR-4.2 | Command to send raw TMUX commands (e.g., `!raw <command>`) | Nice to Have |
| FR-4.3 | Command to send interrupt signal (e.g., `!interrupt` sends Ctrl+C) | Nice to Have |

---

## Non-Functional Requirements

| ID | Requirement | Notes |
|----|-------------|-------|
| NFR-1 | Single-user operation | No auth beyond Discord permissions |
| NFR-2 | Local execution | Bot runs on same machine as TMUX/Claude |
| NFR-3 | Minimal dependencies | Python preferred; Node.js acceptable |
| NFR-4 | Config via environment variables or simple config file | No database |
| NFR-5 | Logging to stdout/file for debugging | Basic print statements fine |
| NFR-6 | Runs on Linux or macOS | |

---

## Technical Approach (Suggested)

### Language & Libraries

**Python (Recommended):**
- `discord.py` — Discord bot framework
- `subprocess` — Run local TMUX commands
- `asyncio` — Async coordination

**Alternative (Node.js):**
- `discord.js` — Discord bot framework
- `child_process` — Run local TMUX commands

### Key Implementation Details

1. **TMUX Interaction Pattern:**
   ```bash
   # Send input to Claude
   tmux send-keys -t claude-session "user message here" Enter
   
   # Capture output (last N lines)
   tmux capture-pane -t claude-session -p -S -100
   ```

2. **Output Detection Heuristic:**
   - Poll `capture-pane` every 500ms–1s
   - Compare output to previous capture
   - If unchanged for 2-3 seconds, assume response complete
   - Send accumulated new content to Discord

3. **Message Chunking:**
   - Split responses at 1900 chars (buffer for formatting)
   - Use code blocks for better readability: ` ```text ``` `

4. **Session Bootstrap (Manual):**
   - User manually starts TMUX session: `tmux new -s claude-session`
   - User manually starts Claude CLI in that session
   - Bot attaches to existing session—does not create it

---

## Configuration

```env
# Discord
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_CHANNEL_ID=123456789  # Restrict to one channel
DISCORD_ALLOWED_USER_ID=your_user_id  # Restrict to one user

# TMUX
TMUX_SESSION_NAME=claude-session
TMUX_PANE=0  # Usually 0 for single-pane window

# Behavior
POLL_INTERVAL_MS=750
RESPONSE_STABLE_SECONDS=2
OUTPUT_HISTORY_LINES=200
```

---

## User Flow

1. **Setup (One-time):**
   - Create Discord bot, get token, invite to server/channel
   - Start TMUX session and Claude CLI on dev machine
   - Start backchannel-bot on same machine with config

2. **Usage:**
   - Send message in Discord: `How do I reverse a linked list?`
   - Bot sends text to TMUX pane
   - Bot polls for Claude's response
   - Bot sends response back to Discord (chunked if needed)

3. **Session Management:**
   - `!status` — Check TMUX session health
   - `!interrupt` — Send Ctrl+C to TMUX pane

---

## Known Limitations & Gotchas (Alpha Quality)

| Issue | Mitigation |
|-------|------------|
| Output detection is heuristic | May cut off early or delay; tune `RESPONSE_STABLE_SECONDS` |
| No handling of Claude's "thinking" state | User just waits |
| Long responses may flood Discord | Chunking helps, but may still be noisy |
| TMUX session must pre-exist | Document in README |
| No conversation isolation | Bot sees whatever is in the TMUX pane |
| ANSI escape codes in output | Strip them before sending to Discord |
| Multi-line input awkward | May need special delimiter or handling |
| Machine must stay on | No wake-on-LAN or sleep handling |

---

## Out of Scope (v0.1)

- Remote/SSH deployment (bot runs locally)
- Multi-user support
- Conversation threading/history in Discord
- File uploads/downloads
- Voice interaction
- Web dashboard
- Persistent storage
- Rate limiting
- Security hardening
- Windows support

---

## Future Considerations (Post-MVP)

- Remote mode via SSH (run bot on different host)
- Slash commands instead of prefix commands
- Discord threads for conversation isolation
- Markdown rendering passthrough
- Image/file handling via Claude's capabilities
- Multiple TMUX sessions/profiles
- Health check endpoint for monitoring
- Docker packaging

---

## Success Criteria (MVP)

- [ ] Bot connects to Discord and responds to test messages
- [ ] Bot can send text to TMUX session
- [ ] Bot can capture and return TMUX output to Discord
- [ ] Full round-trip: Discord → TMUX → Claude → TMUX → Discord works
- [ ] Messages over 2000 chars are chunked properly
- [ ] Typing indicator shows while waiting for response
- [ ] Basic error messages when things break

---

## Appendix: Quick Start Commands

```bash
# Terminal 1: Start Claude session
tmux new -s claude-session
claude  # or however you start Claude CLI

# Detach from TMUX (leave it running)
# Ctrl+B, then D

# Terminal 2: Run backchannel-bot
export DISCORD_BOT_TOKEN="..."
export DISCORD_CHANNEL_ID="..."
export DISCORD_ALLOWED_USER_ID="..."
python backchannel_bot.py
```

---

*backchannel-bot is alpha software. It will break. That's fine.*
