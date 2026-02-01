"""Logging configuration for backchannel-bot."""

import logging
import os


def setup_logging() -> None:
    """Configure logging for the application.

    Reads LOG_LEVEL from environment (default: INFO).
    Logs include timestamp, level, and message.
    """
    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
