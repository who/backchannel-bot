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

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages.

        Filters messages based on configured channel and user restrictions.

        Args:
            message: The Discord message received.
        """
        # Ignore messages from all bots (including this bot)
        if message.author.bot:
            logger.debug("Ignoring bot message from %s", message.author)
            return

        # Check channel restriction if configured
        if (
            self.config.discord_channel_id is not None
            and str(message.channel.id) != self.config.discord_channel_id
        ):
            logger.debug(
                "Ignoring: wrong channel (got %s, expected %s)",
                message.channel.id,
                self.config.discord_channel_id,
            )
            return

        # Check user restriction if configured
        if (
            self.config.discord_allowed_user_id is not None
            and str(message.author.id) != self.config.discord_allowed_user_id
        ):
            logger.debug(
                "Ignoring: wrong user (got %s, expected %s)",
                message.author.id,
                self.config.discord_allowed_user_id,
            )
            return

        logger.info("Processing message from %s: %s", message.author, message.content)
        # TODO: Forward to TMUX session (implemented in separate issue)

    async def send_response(self, channel: discord.abc.Messageable, text: str) -> discord.Message:
        """Send a response message to a channel.

        Args:
            channel: The channel or DM to send the response to.
            text: The text content to send.

        Returns:
            The sent message object.
        """
        logger.debug("Sending response to channel %s", channel)
        return await channel.send(text)

    def run_bot(self) -> None:
        """Start the bot using the configured token."""
        self.run(self.config.discord_bot_token)
