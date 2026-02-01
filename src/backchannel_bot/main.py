"""Main entry point for backchannel-bot."""

import logging
import sys

from dotenv import load_dotenv

from backchannel_bot.config import Config, ConfigurationError
from backchannel_bot.discord_client import BackchannelBot
from backchannel_bot.logging_config import setup_logging
from backchannel_bot.tmux_client import TmuxClient, TmuxError

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the backchannel bot.

    Sets up logging, loads configuration, validates TMUX session exists,
    initializes the Discord client, and starts the bot.

    Exits with code 1 if configuration is invalid or TMUX session doesn't exist.
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

    # Create TMUX client and validate session exists
    tmux_client = TmuxClient(
        session_name=config.tmux_session_name,
        pane=config.tmux_pane,
        output_history_lines=config.output_history_lines,
    )

    try:
        if not tmux_client.check_session():
            logger.error(
                "TMUX session '%s' does not exist. Please create it with: tmux new -d -s %s",
                config.tmux_session_name,
                config.tmux_session_name,
            )
            sys.exit(1)
        logger.info("TMUX session '%s' validated", config.tmux_session_name)
    except TmuxError as e:
        logger.error("TMUX error: %s", e)
        sys.exit(1)

    # Initialize and run the Discord bot
    bot = BackchannelBot(config=config, tmux_client=tmux_client)
    logger.info("Starting Discord bot...")
    bot.run_bot()


if __name__ == "__main__":
    main()
