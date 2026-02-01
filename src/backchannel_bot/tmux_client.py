"""TMUX client module for backchannel-bot."""

import logging
import re
import subprocess

logger = logging.getLogger(__name__)


class TmuxError(Exception):
    """Exception raised for TMUX-related errors."""

    pass


# Regex to match ANSI escape sequences
# Matches: ESC[ followed by any number of parameters and ending with a letter
# Also matches other escape sequences like ESC]...BEL for terminal titles
ANSI_ESCAPE_PATTERN = re.compile(
    r"\x1b"  # ESC character
    r"(?:"
    r"\[[0-9;?]*[A-Za-z]"  # CSI sequences: ESC[...m, ESC[...H, etc.
    r"|\][^\x07]*\x07"  # OSC sequences: ESC]...BEL (terminal titles)
    r"|[PX^_][^\x1b]*\x1b\\"  # DCS/SOS/PM/APC sequences
    r"|[NO]."  # SS2/SS3 sequences
    r"|[=>]"  # Other simple sequences
    r")"
)


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text.

    Removes terminal escape sequences including:
    - Color codes (ESC[32m, ESC[0m, etc.)
    - Cursor control codes (ESC[H, ESC[2J, etc.)
    - Terminal title sequences (ESC]...BEL)

    Args:
        text: Text potentially containing ANSI escape codes.

    Returns:
        Text with all ANSI escape codes removed.
    """
    return ANSI_ESCAPE_PATTERN.sub("", text)


class TmuxClient:
    """Client for interacting with TMUX sessions."""

    def __init__(self, session_name: str, pane: int = 0, output_history_lines: int = 200) -> None:
        """Initialize the TMUX client.

        Args:
            session_name: Name of the TMUX session to interact with.
            pane: Pane number within the session (default: 0).
            output_history_lines: Number of lines to capture from pane (default: 200).
        """
        self.session_name = session_name
        self.pane = pane
        self.output_history_lines = output_history_lines

    def check_session(self) -> bool:
        """Check if the configured TMUX session exists.

        Returns:
            True if the session exists, False otherwise.

        Raises:
            TmuxError: If tmux is not installed.
        """
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", self.session_name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.debug("TMUX session '%s' exists", self.session_name)
                return True
            else:
                logger.error(
                    "TMUX session '%s' does not exist. Please create it with: tmux new -d -s %s",
                    self.session_name,
                    self.session_name,
                )
                return False
        except FileNotFoundError as e:
            logger.exception("tmux command not found")
            raise TmuxError("tmux is not installed") from e

    def send_input(self, text: str) -> bool:
        """Send input text to the TMUX pane.

        Args:
            text: The text to send to the TMUX pane.

        Returns:
            True if the input was sent successfully, False otherwise.

        Raises:
            TmuxError: If tmux is not installed or subprocess fails unexpectedly.
        """
        target = f"{self.session_name}:{self.pane}"
        logger.debug("Sending input to TMUX target '%s': %r", target, text)
        try:
            result = subprocess.run(
                ["tmux", "send-keys", "-t", target, text, "Enter"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.debug("Successfully sent input to TMUX")
                return True
            else:
                error_msg = result.stderr.strip() or "unknown error"
                logger.error("Failed to send input to TMUX: %s", error_msg)
                return False
        except FileNotFoundError as e:
            logger.exception("tmux command not found")
            raise TmuxError("tmux is not installed") from e
        except subprocess.SubprocessError as e:
            logger.exception("Subprocess error while sending input to TMUX")
            raise TmuxError(f"Failed to execute tmux command: {e}") from e

    def get_session_status(self) -> dict[str, str | bool]:
        """Get the status of the configured TMUX session.

        Returns:
            Dictionary containing session status info:
                - exists: bool - Whether the session exists
                - attached: bool | None - Whether session is attached (None if doesn't exist)
                - session_name: str - The session name

        Raises:
            TmuxError: If tmux is not installed or subprocess fails unexpectedly.
        """
        status: dict[str, str | bool] = {
            "session_name": self.session_name,
            "exists": False,
        }

        try:
            # Check if session exists using list-sessions
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}:#{session_attached}"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.debug("No tmux sessions found or tmux error: %s", result.stderr.strip())
                return status

            # Parse output to find our session
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 2 and parts[0] == self.session_name:
                    status["exists"] = True
                    status["attached"] = parts[1] == "1"
                    logger.debug(
                        "Session '%s' status: attached=%s", self.session_name, status["attached"]
                    )
                    break

        except FileNotFoundError as e:
            logger.exception("tmux command not found")
            raise TmuxError("tmux is not installed") from e
        except subprocess.SubprocessError as e:
            logger.exception("Subprocess error while getting session status")
            raise TmuxError(f"Failed to execute tmux command: {e}") from e

        return status

    def capture_output(self) -> str:
        """Capture output from the TMUX pane.

        Returns:
            String containing the captured pane content, with trailing empty lines stripped.

        Raises:
            TmuxError: If tmux is not installed, session doesn't exist, or subprocess fails.
        """
        target = f"{self.session_name}:{self.pane}"
        logger.debug(
            "Capturing output from TMUX target '%s' (last %d lines)",
            target,
            self.output_history_lines,
        )
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "capture-pane",
                    "-t",
                    target,
                    "-p",
                    "-S",
                    f"-{self.output_history_lines}",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                raw_output = result.stdout.rstrip()
                output = strip_ansi(raw_output)
                logger.debug(
                    "Captured %d characters from TMUX (%d after ANSI strip)",
                    len(raw_output),
                    len(output),
                )
                return output
            else:
                error_msg = result.stderr.strip() or "unknown error"
                logger.error("Failed to capture TMUX output: %s", error_msg)
                raise TmuxError(f"Failed to capture output: {error_msg}")
        except FileNotFoundError as e:
            logger.exception("tmux command not found")
            raise TmuxError("tmux is not installed") from e
        except subprocess.SubprocessError as e:
            logger.exception("Subprocess error while capturing TMUX output")
            raise TmuxError(f"Failed to execute tmux command: {e}") from e

    def send_interrupt(self) -> bool:
        """Send Ctrl+C (interrupt signal) to the TMUX pane.

        Returns:
            True if the interrupt was sent successfully, False otherwise.

        Raises:
            TmuxError: If tmux is not installed or subprocess fails unexpectedly.
        """
        target = f"{self.session_name}:{self.pane}"
        logger.debug("Sending interrupt (Ctrl+C) to TMUX target '%s'", target)
        try:
            result = subprocess.run(
                ["tmux", "send-keys", "-t", target, "C-c"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.debug("Successfully sent interrupt to TMUX")
                return True
            else:
                error_msg = result.stderr.strip() or "unknown error"
                logger.error("Failed to send interrupt to TMUX: %s", error_msg)
                return False
        except FileNotFoundError as e:
            logger.exception("tmux command not found")
            raise TmuxError("tmux is not installed") from e
        except subprocess.SubprocessError as e:
            logger.exception("Subprocess error while sending interrupt to TMUX")
            raise TmuxError(f"Failed to execute tmux command: {e}") from e

    def run_raw_command(self, command: str) -> str:
        """Run an arbitrary tmux command and return its output.

        Args:
            command: The tmux command to run (e.g., "list-windows", "display-message -p '#S'").

        Returns:
            The stdout from the tmux command.

        Raises:
            TmuxError: If tmux is not installed, command fails, or subprocess fails.
        """
        logger.debug("Running raw tmux command: %s", command)
        try:
            # Split command into parts for subprocess
            cmd_parts = ["tmux"] + command.split()
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                output = result.stdout.rstrip()
                logger.debug("Raw command succeeded, output: %d chars", len(output))
                return output
            else:
                error_msg = result.stderr.strip() or "command failed"
                logger.error("Raw tmux command failed: %s", error_msg)
                raise TmuxError(f"tmux command failed: {error_msg}")
        except FileNotFoundError as e:
            logger.exception("tmux command not found")
            raise TmuxError("tmux is not installed") from e
        except subprocess.SubprocessError as e:
            logger.exception("Subprocess error while running raw tmux command")
            raise TmuxError(f"Failed to execute tmux command: {e}") from e

    def run_claude_print(self, prompt: str, timeout: int = 300) -> str:
        """Run Claude Code in print mode and return the response.

        Executes `claude -p "prompt"` directly (not in tmux) to get a reliable
        text response without TUI complications.

        Args:
            prompt: The prompt to send to Claude Code.
            timeout: Maximum seconds to wait for response (default: 300).

        Returns:
            Claude's response text.

        Raises:
            TmuxError: If Claude Code is not installed or command fails.
        """
        logger.debug("Running Claude Code in print mode: %r", prompt[:100])
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
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
                raise TmuxError(f"Claude command failed: {error_msg}")
        except FileNotFoundError as e:
            logger.exception("claude command not found")
            raise TmuxError("Claude Code is not installed") from e
        except subprocess.TimeoutExpired as e:
            logger.exception("Claude command timed out after %d seconds", timeout)
            raise TmuxError(f"Claude command timed out after {timeout} seconds") from e
        except subprocess.SubprocessError as e:
            logger.exception("Subprocess error while running Claude")
            raise TmuxError(f"Failed to execute claude command: {e}") from e
