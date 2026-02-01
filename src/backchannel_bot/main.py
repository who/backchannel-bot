"""Main entry point for backchannel-bot."""

import logging
import sys

from dotenv import load_dotenv

from backchannel_bot.claude_client import ClaudeClient
from backchannel_bot.config import Config, ConfigurationError
from backchannel_bot.discord_client import BackchannelBot
from backchannel_bot.logging_config import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the backchannel bot.

    Sets up logging, loads configuration, initializes the Discord client,
    and starts the bot.

    Exits with code 1 if configuration is invalid.
    """
    # Load environment variables from .env file
    load_dotenv()

    # Set up logging first so we can log any errors
    setup_logging()

    logger.info("Backchannel Bot starting...")

    # Load configuration (will raise ConfigurationError if required env vars missing)
    try:
        config = Config()
        logger.info("Configuration loaded successfully")
    except ConfigurationError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    # Create Claude client
    claude_client = ClaudeClient()

    # Initialize and run the Discord bot
    bot = BackchannelBot(config=config, claude_client=claude_client)
    logger.info("Starting Discord bot...")
    bot.run_bot()


if __name__ == "__main__":
    main()
