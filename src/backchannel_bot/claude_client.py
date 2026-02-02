"""Claude Code client module for backchannel-bot."""

import asyncio
import json
import logging
import os
import subprocess
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ClaudeError(Exception):
    """Exception raised for Claude Code-related errors."""

    pass


@dataclass
class PermissionRequest:
    """Represents a permission request from Claude Code."""

    tool_name: str
    tool_use_id: str
    tool_input: dict


@dataclass
class ClaudeStreamMessage:
    """A message from the Claude stream."""

    type: str
    subtype: str | None = None
    data: dict | None = None

    # For permission requests
    permission_request: PermissionRequest | None = None

    # For final results
    result: str | None = None
    is_complete: bool = False


class ClaudeStreamSession:
    """Manages a streaming session with Claude Code CLI.

    This class handles bidirectional communication with the Claude CLI using
    stream-json format, allowing permission requests to be intercepted and
    handled interactively.
    """

    def __init__(self, cwd: str | None = None) -> None:
        """Initialize a streaming session.

        Args:
            cwd: Working directory for the Claude process.
        """
        self._cwd = cwd or os.getcwd()
        self._process: asyncio.subprocess.Process | None = None
        self._session_id: str | None = None

    async def start(
        self,
        prompt: str,
        session_mode: str = "continue",
        timeout: int = 300,
    ) -> AsyncIterator[ClaudeStreamMessage]:
        """Start a streaming Claude session and yield messages.

        This method runs Claude with stream-json format and yields messages
        as they arrive. Permission requests will be yielded and the caller
        is responsible for calling respond_to_permission() to continue.

        Args:
            prompt: The prompt to send to Claude Code.
            session_mode: How to handle session continuation.
            timeout: Maximum seconds to wait for response.

        Yields:
            ClaudeStreamMessage objects for each event from Claude.

        Raises:
            ClaudeError: If Claude Code is not installed or command fails.
        """
        cmd = [
            "claude",
            "-p",
            prompt,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]

        if session_mode == "continue":
            cmd.append("--continue")
        elif session_mode.startswith("resume:"):
            session_id = session_mode[7:]
            cmd.extend(["--resume", session_id])

        logger.debug("Starting Claude stream session: %s", " ".join(cmd))

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )
        except FileNotFoundError as e:
            raise ClaudeError("Claude Code is not installed") from e

        assert self._process.stdout is not None
        assert self._process.stdin is not None

        try:
            async for message in self._read_stream():
                yield message
                if message.is_complete:
                    break
        except asyncio.TimeoutError as e:
            if self._process:
                self._process.terminate()
            raise ClaudeError(f"Claude command timed out after {timeout} seconds") from e
        finally:
            if self._process and self._process.returncode is None:
                self._process.terminate()
                await self._process.wait()

    async def _read_stream(self) -> AsyncIterator[ClaudeStreamMessage]:
        """Read and parse the JSON stream from Claude.

        Yields:
            ClaudeStreamMessage objects for each line of JSON.
        """
        assert self._process is not None
        assert self._process.stdout is not None

        while True:
            line = await self._process.stdout.readline()
            if not line:
                break

            try:
                data = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                logger.debug("Skipping non-JSON line: %s", line[:100])
                continue

            msg_type = data.get("type", "")
            msg_subtype = data.get("subtype")

            # Track session ID
            if msg_type == "system" and msg_subtype == "init":
                self._session_id = data.get("session_id")

            # Check for permission denial (tool result with permission error)
            if msg_type == "user":
                message = data.get("message", {})
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "tool_result"
                            and item.get("is_error")
                            and "permission" in str(item.get("content", "")).lower()
                        ):
                            # This is a permission denial
                            yield ClaudeStreamMessage(
                                type="permission_denied",
                                data=data,
                            )

            # Check for pending permission requests in result
            if msg_type == "result":
                result_text = data.get("result", "")
                permission_denials = data.get("permission_denials", [])

                if permission_denials:
                    # There are pending permission requests
                    for denial in permission_denials:
                        perm_req = PermissionRequest(
                            tool_name=denial.get("tool_name", ""),
                            tool_use_id=denial.get("tool_use_id", ""),
                            tool_input=denial.get("tool_input", {}),
                        )
                        yield ClaudeStreamMessage(
                            type="permission_request",
                            permission_request=perm_req,
                            data=data,
                        )

                yield ClaudeStreamMessage(
                    type="result",
                    result=result_text,
                    is_complete=True,
                    data=data,
                )
                break

            # Yield other messages for transparency
            yield ClaudeStreamMessage(type=msg_type, subtype=msg_subtype, data=data)

    async def respond_to_permission(
        self,
        tool_use_id: str,
        allow: bool,
        message: str | None = None,
    ) -> None:
        """Respond to a permission request.

        Note: The current Claude CLI in print mode doesn't support interactive
        permission responses via stdin in the same way the SDK does. This method
        is a placeholder for when that functionality is available.

        For now, permission responses need to be handled by:
        1. Using --allowedTools to pre-approve specific tools
        2. Using --permission-prompt-tool with an MCP server
        3. Using the Agent SDK directly

        Args:
            tool_use_id: The ID of the tool use request.
            allow: Whether to allow the tool use.
            message: Optional message to send (for denials).
        """
        # The CLI print mode doesn't support responding to permission requests
        # interactively via stdin. This would require the Agent SDK.
        logger.warning(
            "Cannot respond to permission %s interactively in CLI print mode. "
            "Use --allowedTools or the Agent SDK for interactive permissions.",
            tool_use_id,
        )


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
            # Use --dangerously-skip-permissions to bypass permission prompts
            # since we can't handle them interactively via Discord
            cmd = ["claude", "-p", prompt, "--dangerously-skip-permissions"]
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
