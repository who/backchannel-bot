"""TMUX client module for backchannel-bot."""

import logging
import subprocess

logger = logging.getLogger(__name__)


class TmuxClient:
    """Client for interacting with TMUX sessions."""

    def __init__(self, session_name: str, pane: int = 0) -> None:
        """Initialize the TMUX client.

        Args:
            session_name: Name of the TMUX session to interact with.
            pane: Pane number within the session (default: 0).
        """
        self.session_name = session_name
        self.pane = pane

    def check_session(self) -> bool:
        """Check if the configured TMUX session exists.

        Returns:
            True if the session exists, False otherwise.
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
        except FileNotFoundError:
            logger.error("tmux command not found. Please install tmux.")
            return False

    def send_input(self, text: str) -> bool:
        """Send input text to the TMUX pane.

        Args:
            text: The text to send to the TMUX pane.

        Returns:
            True if the input was sent successfully, False otherwise.
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
                logger.error("Failed to send input to TMUX: %s", result.stderr.strip())
                return False
        except FileNotFoundError:
            logger.error("tmux command not found. Please install tmux.")
            return False
