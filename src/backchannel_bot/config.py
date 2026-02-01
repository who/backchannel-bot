"""Configuration module for backchannel-bot."""

import os
from dataclasses import dataclass, field


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""


def _validate_discord_id(env_var: str, value: str | None) -> str | None:
    """Validate that a Discord ID is numeric.

    Args:
        env_var: Name of the environment variable (for error messages)
        value: The value to validate

    Returns:
        The validated value (unchanged if valid, None if not set)

    Raises:
        ConfigurationError: If the value is set but not numeric
    """
    if value is None:
        return None
    if not value.isdigit():
        raise ConfigurationError(
            f"{env_var} must be a numeric Discord ID, not '{value}'. "
            f"To get a Discord ID: Enable Developer Mode in Discord settings, "
            f"then right-click the user/channel and select 'Copy ID'."
        )
    return value


def _validate_session_mode(value: str) -> str:
    """Validate CLAUDE_SESSION_MODE value.

    Args:
        value: The session mode value to validate.

    Returns:
        The validated value.

    Raises:
        ConfigurationError: If the value is not a valid mode.
    """
    valid_modes = ("fresh", "continue")
    if value in valid_modes:
        return value
    if value.startswith("resume:"):
        session_id = value[7:]
        if session_id:
            return value
        raise ConfigurationError(
            "CLAUDE_SESSION_MODE 'resume:' requires a session ID. Use 'resume:<session_id>' format."
        )
    raise ConfigurationError(
        f"CLAUDE_SESSION_MODE must be 'fresh', 'continue', or 'resume:<session_id>', not '{value}'"
    )


@dataclass
class Config:
    """Bot configuration loaded from environment variables.

    Required:
        DISCORD_BOT_TOKEN: Discord bot authentication token

    Optional:
        DISCORD_CHANNEL_ID: Restrict bot to a specific channel
        DISCORD_ALLOWED_USER_ID: Restrict bot to a specific user
        CLAUDE_SESSION_MODE: Session continuation mode (default: "continue")
            - "fresh": Start a new session each time (`claude -p`)
            - "continue": Continue the most recent session (`claude -p --continue`)
            - "resume:<session_id>": Resume a specific session (`claude -p --resume <id>`)
    """

    discord_bot_token: str = field(default_factory=lambda: _get_required("DISCORD_BOT_TOKEN"))
    discord_channel_id: str | None = field(
        default_factory=lambda: _validate_discord_id(
            "DISCORD_CHANNEL_ID", os.environ.get("DISCORD_CHANNEL_ID")
        )
    )
    discord_allowed_user_id: str | None = field(
        default_factory=lambda: _validate_discord_id(
            "DISCORD_ALLOWED_USER_ID", os.environ.get("DISCORD_ALLOWED_USER_ID")
        )
    )
    claude_session_mode: str = field(
        default_factory=lambda: _validate_session_mode(
            os.environ.get("CLAUDE_SESSION_MODE", "continue")
        )
    )


def _get_required(env_var: str) -> str:
    """Get a required environment variable or raise ConfigurationError."""
    value = os.environ.get(env_var)
    if value is None:
        raise ConfigurationError(f"Required environment variable {env_var} is not set")
    return value
