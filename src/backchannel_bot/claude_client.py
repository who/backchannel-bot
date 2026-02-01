"""Claude Code client module for backchannel-bot."""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ClaudeError(Exception):
    """Exception raised for Claude Code-related errors."""

    pass


class ClaudeClient:
    """Client for interacting with Claude Code CLI."""

    def __init__(self) -> None:
        """Initialize the Claude Code client."""
        pass

    def run_claude_print(
        self, prompt: str, timeout: int = 300, session_mode: str = "continue"
    ) -> str:
        """Run Claude Code in print mode and return the response.

        Executes `claude -p "prompt"` to get a reliable text response.

        Args:
            prompt: The prompt to send to Claude Code.
            timeout: Maximum seconds to wait for response (default: 300).
            session_mode: How to handle session continuation (default: "continue").
                - "fresh": Start a new session each time
                - "continue": Continue the most recent session (--continue)
                - "resume:<session_id>": Resume a specific session (--resume <id>)

        Returns:
            Claude's response text.

        Raises:
            ClaudeError: If Claude Code is not installed or command fails.
        """
        logger.debug(
            "Running Claude Code in print mode (session_mode=%s): %r",
            session_mode,
            prompt[:100],
        )
        try:
            # Build command based on session mode
            cmd = ["claude", "-p", prompt]
            if session_mode == "continue":
                cmd.append("--continue")
            elif session_mode.startswith("resume:"):
                session_id = session_mode[7:]
                cmd.extend(["--resume", session_id])
            # "fresh" mode uses no additional flags

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                output = result.stdout.rstrip()
                logger.debug("Claude print mode succeeded, output: %d chars", len(output))
                return output
            else:
                error_msg = result.stderr.strip() or "command failed"
                logger.error("Claude print mode failed: %s", error_msg)
                raise ClaudeError(f"Claude command failed: {error_msg}")
        except FileNotFoundError as e:
            logger.exception("claude command not found")
            raise ClaudeError("Claude Code is not installed") from e
        except subprocess.TimeoutExpired as e:
            logger.exception("Claude command timed out after %d seconds", timeout)
            raise ClaudeError(f"Claude command timed out after {timeout} seconds") from e
        except subprocess.SubprocessError as e:
            logger.exception("Subprocess error while running Claude")
            raise ClaudeError(f"Failed to execute claude command: {e}") from e

    def list_claude_sessions(self, cwd: str | None = None, limit: int = 5) -> list[dict]:
        """List Claude Code sessions for the current or specified working directory.

        Args:
            cwd: Working directory to list sessions for (default: current directory).
            limit: Maximum number of sessions to return (default: 5).

        Returns:
            List of session dictionaries with id, timestamp, and first_prompt fields,
            sorted by most recent first.
        """
        if cwd is None:
            cwd = os.getcwd()

        # Claude stores sessions in ~/.claude/projects/<escaped-path>/
        claude_projects_dir = Path.home() / ".claude" / "projects"
        escaped_path = cwd.replace("/", "-")
        project_sessions_dir = claude_projects_dir / escaped_path

        if not project_sessions_dir.exists():
            logger.debug("No Claude sessions directory found at %s", project_sessions_dir)
            return []

        sessions = []
        for session_file in project_sessions_dir.glob("*.jsonl"):
            session_id = session_file.stem
            # Skip if not a valid UUID pattern
            if len(session_id) != 36:
                continue

            try:
                # Get file modification time as timestamp
                mtime = session_file.stat().st_mtime
                timestamp = datetime.fromtimestamp(mtime)

                # Try to extract first user prompt from the session
                first_prompt = None
                with open(session_file, encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            # Look for user messages
                            if entry.get("type") == "user" and entry.get("message"):
                                msg = entry["message"]
                                if isinstance(msg, dict) and msg.get("content"):
                                    content = msg["content"]
                                    if isinstance(content, list) and len(content) > 0:
                                        text_block = content[0]
                                        if isinstance(text_block, dict):
                                            first_prompt = text_block.get("text", "")[:80]
                                            break
                                    elif isinstance(content, str):
                                        first_prompt = content[:80]
                                        break
                        except json.JSONDecodeError:
                            continue

                sessions.append(
                    {
                        "id": session_id,
                        "timestamp": timestamp,
                        "first_prompt": first_prompt or "(no prompt found)",
                    }
                )
            except (OSError, PermissionError) as e:
                logger.debug("Could not read session file %s: %s", session_file, e)
                continue

        # Sort by timestamp (most recent first) and limit
        sessions.sort(key=lambda s: s["timestamp"], reverse=True)
        return sessions[:limit]
