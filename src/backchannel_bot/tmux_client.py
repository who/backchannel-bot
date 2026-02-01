"""TMUX client module for backchannel-bot."""

import logging
import subprocess

logger = logging.getLogger(__name__)


class TmuxClient:
    """Client for interacting with TMUX sessions."""

    def __init__(self, session_name: str) -> None:
        """Initialize the TMUX client.

        Args:
            session_name: Name of the TMUX session to interact with.
        """
        self.session_name = session_name

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
