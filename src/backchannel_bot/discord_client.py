"""Discord client module for backchannel-bot."""

import asyncio
import logging

import discord

from backchannel_bot.config import Config
from backchannel_bot.tmux_client import TmuxClient

logger = logging.getLogger(__name__)


class BackchannelBot(discord.Client):
    """Discord client for backchannel communication with TMUX sessions."""

    def __init__(self, config: Config, tmux_client: TmuxClient) -> None:
        """Initialize the backchannel bot.

        Args:
            config: Bot configuration containing Discord token and settings.
            tmux_client: Client for interacting with the TMUX session.
        """
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.config = config
        self.tmux_client = tmux_client

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

        # Route messages: commands (!) vs passthrough (everything else)
        if message.content.startswith("!"):
            await self._handle_command(message)
        else:
            await self._handle_passthrough(message)

    async def _handle_command(self, message: discord.Message) -> None:
        """Handle command messages (starting with !).

        Args:
            message: The Discord message containing a command.
        """
        logger.debug("Routing to command handler: %s", message.content)
        # TODO: Implement command handling (bcb-sb0 and related)

    async def _handle_passthrough(self, message: discord.Message) -> None:
        """Handle passthrough messages (sent directly to TMUX).

        Sends the message to TMUX, polls for output until stable,
        and relays the new content back to Discord.

        Args:
            message: The Discord message to pass through to TMUX.
        """
        logger.debug("Passing through to TMUX: %s", message.content)

        # Capture output before sending input
        output_before = self.tmux_client.capture_output()

        # Send input to TMUX
        if not self.tmux_client.send_input(message.content):
            await self.send_response(message.channel, "❌ Failed to send input to TMUX")
            return

        # Poll for response using configured intervals
        new_content = await self._poll_for_response(output_before)

        # Send new content to Discord if there is any
        if new_content:
            await self.send_response(message.channel, new_content)
        else:
            logger.debug("No new TMUX output to relay")

    async def _poll_for_response(self, output_before: str) -> str:
        """Poll TMUX pane for response until output stabilizes.

        Continuously captures output at configured intervals until
        no new content appears for response_stable_seconds.

        Args:
            output_before: TMUX output captured before sending input.

        Returns:
            The accumulated new content from the TMUX pane.
        """
        poll_interval = self.config.poll_interval_ms / 1000.0
        stable_duration = self.config.response_stable_seconds
        polls_needed_for_stable = max(1, int(stable_duration / poll_interval))

        logger.debug(
            "Starting poll loop: interval=%.2fs, stable after %d polls",
            poll_interval,
            polls_needed_for_stable,
        )

        last_output = output_before
        stable_poll_count = 0
        poll_cycle = 0

        while True:
            # Wait for poll interval
            await asyncio.sleep(poll_interval)
            poll_cycle += 1

            # Capture current output
            current_output = self.tmux_client.capture_output()
            logger.debug("Poll cycle %d: captured %d chars", poll_cycle, len(current_output))

            # Check if output changed since last poll
            if current_output == last_output:
                stable_poll_count += 1
                logger.debug(
                    "Output stable for %d/%d polls", stable_poll_count, polls_needed_for_stable
                )

                # Check if we've been stable long enough
                if stable_poll_count >= polls_needed_for_stable:
                    logger.debug("Response complete after %d poll cycles", poll_cycle)
                    break
            else:
                # Output changed, reset stability counter
                stable_poll_count = 0
                last_output = current_output
                logger.debug("New content detected, resetting stability counter")

        # Compute and return the diff
        return self._compute_output_diff(output_before, current_output)

    def _compute_output_diff(self, before: str, after: str) -> str:
        """Compute the new content in the TMUX output.

        Args:
            before: TMUX output captured before sending input.
            after: TMUX output captured after sending input.

        Returns:
            The new lines that appeared in the output.
        """
        if not before:
            return after

        # Find where the new content starts
        # The 'before' content should be a suffix of 'after' if nothing scrolled off
        if after.startswith(before):
            new_content = after[len(before) :].lstrip("\n")
            return new_content

        # If content scrolled, find the longest common suffix
        before_lines = before.split("\n")
        after_lines = after.split("\n")

        # Find where the before content ends in after
        # Look for the last few lines of 'before' appearing in 'after'
        overlap_start = 0
        for i in range(len(after_lines)):
            # Check if remaining after_lines match the end of before_lines
            after_suffix = after_lines[i:]
            before_suffix_len = min(len(after_suffix), len(before_lines))
            if before_suffix_len > 0:
                before_suffix = before_lines[-before_suffix_len:]
                if after_suffix[:before_suffix_len] == before_suffix:
                    overlap_start = i + before_suffix_len
                    break

        # If no overlap found, return everything after the first occurrence
        # of the last line of 'before'
        if overlap_start == 0 and before_lines:
            last_before_line = before_lines[-1]
            for i, line in enumerate(after_lines):
                if line == last_before_line:
                    overlap_start = i + 1
                    break

        new_lines = after_lines[overlap_start:]
        return "\n".join(new_lines)

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
