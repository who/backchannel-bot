"""Configuration module for backchannel-bot."""

import os
from dataclasses import dataclass, field


class ConfigurationError(Exception):
    """Raised when required configuration is missing."""


@dataclass
class Config:
    """Bot configuration loaded from environment variables.

    Required:
        DISCORD_BOT_TOKEN: Discord bot authentication token
        TMUX_SESSION_NAME: Name of the TMUX session to attach to

    Optional:
        DISCORD_CHANNEL_ID: Restrict bot to a specific channel
        DISCORD_ALLOWED_USER_ID: Restrict bot to a specific user
        TMUX_PANE: TMUX pane number (default: 0)
        POLL_INTERVAL_MS: Polling interval in milliseconds (default: 750)
        RESPONSE_STABLE_SECONDS: Seconds of stability before response is complete (default: 2)
        OUTPUT_HISTORY_LINES: Number of lines to capture from TMUX (default: 200)
    """

    discord_bot_token: str = field(default_factory=lambda: _get_required("DISCORD_BOT_TOKEN"))
    tmux_session_name: str = field(default_factory=lambda: _get_required("TMUX_SESSION_NAME"))
    discord_channel_id: str | None = field(
        default_factory=lambda: os.environ.get("DISCORD_CHANNEL_ID")
    )
    discord_allowed_user_id: str | None = field(
        default_factory=lambda: os.environ.get("DISCORD_ALLOWED_USER_ID")
    )
    tmux_pane: int = field(default_factory=lambda: int(os.environ.get("TMUX_PANE", "0")))
    poll_interval_ms: int = field(
        default_factory=lambda: int(os.environ.get("POLL_INTERVAL_MS", "750"))
    )
    response_stable_seconds: int = field(
        default_factory=lambda: int(os.environ.get("RESPONSE_STABLE_SECONDS", "2"))
    )
    output_history_lines: int = field(
        default_factory=lambda: int(os.environ.get("OUTPUT_HISTORY_LINES", "200"))
    )


def _get_required(env_var: str) -> str:
    """Get a required environment variable or raise ConfigurationError."""
    value = os.environ.get(env_var)
    if value is None:
        raise ConfigurationError(f"Required environment variable {env_var} is not set")
    return value
