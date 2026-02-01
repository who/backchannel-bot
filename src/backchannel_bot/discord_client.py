"""Discord client module for backchannel-bot."""

import logging

import discord

from backchannel_bot.config import Config

logger = logging.getLogger(__name__)


class BackchannelBot(discord.Client):
    """Discord client for backchannel communication with TMUX sessions."""

    def __init__(self, config: Config) -> None:
        """Initialize the backchannel bot.

        Args:
            config: Bot configuration containing Discord token and settings.
        """
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.config = config

    async def on_ready(self) -> None:
        """Handle successful connection to Discord."""
        logger.info("Logged in as %s", self.user)

    async def on_disconnect(self) -> None:
        """Handle disconnection from Discord."""
        logger.warning("Disconnected from Discord")

    def run_bot(self) -> None:
        """Start the bot using the configured token."""
        self.run(self.config.discord_bot_token)
