"""Discord client module for backchannel-bot."""

import asyncio
import logging

import discord

from backchannel_bot.config import Config
from backchannel_bot.tmux_client import TmuxClient, TmuxError

logger = logging.getLogger(__name__)

# Discord message limit is 2000 chars; use 1900 for safety buffer
MAX_CHUNK_SIZE = 1900


def chunk_message(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split a message into chunks that fit within Discord's message limit.

    Splits at newline boundaries when possible to preserve formatting.

    Args:
        text: The text to split into chunks.
        max_size: Maximum size per chunk (default: 1900).

    Returns:
        List of text chunks, each under max_size characters.
    """
    if not text:
        return []

    if len(text) <= max_size:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_size:
            chunks.append(remaining)
            break

        # Find a good split point within the max_size limit
        chunk = remaining[:max_size]
        split_pos = max_size

        # Prefer splitting at newline boundaries
        last_newline = chunk.rfind("\n")
        if last_newline > 0:
            # Split at the newline (keep newline with current chunk)
            split_pos = last_newline + 1
        else:
            # No newline found, try splitting at last space
            last_space = chunk.rfind(" ")
            if last_space > 0:
                split_pos = last_space + 1

        chunks.append(remaining[:split_pos].rstrip())
        remaining = remaining[split_pos:].lstrip()

    return chunks


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

    async def on_error(self, event: str, *args: object, **kwargs: object) -> None:
        """Handle errors in event handlers.

        Logs the error with full traceback instead of crashing.

        Args:
            event: Name of the event that raised the exception.
            *args: Positional arguments passed to the event handler.
            **kwargs: Keyword arguments passed to the event handler.
        """
        logger.exception("Error in event handler '%s'", event)

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages.

        Filters messages based on configured channel and user restrictions.
        Catches all exceptions to prevent bot crashes on transient failures.

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

        try:
            # Route messages: commands (!) vs passthrough (everything else)
            if message.content.startswith("!"):
                await self._handle_command(message)
            else:
                await self._handle_passthrough(message)
        except Exception:
            # Catch any unexpected errors to prevent bot crash
            logger.exception("Unexpected error while processing message")
            try:
                await self.send_response(
                    message.channel,
                    "❌ An unexpected error occurred. Please try again.",
                )
            except Exception:
                # If we can't even send the error message, just log it
                logger.exception("Failed to send error message to Discord")

    async def _handle_command(self, message: discord.Message) -> None:
        """Handle command messages (starting with !).

        Args:
            message: The Discord message containing a command.
        """
        logger.debug("Routing to command handler: %s", message.content)
        command = message.content.split()[0].lower()

        if command == "!status":
            await self._handle_status_command(message)
        elif command == "!raw":
            await self._handle_raw_command(message)
        elif command == "!interrupt":
            await self._handle_interrupt_command(message)
        else:
            logger.debug("Unknown command: %s", command)

    async def _handle_status_command(self, message: discord.Message) -> None:
        """Handle the !status command to report TMUX session health.

        Args:
            message: The Discord message containing the !status command.
        """
        logger.debug("Handling !status command")
        try:
            status = self.tmux_client.get_session_status()

            session_name = status["session_name"]
            exists = status.get("exists", False)

            if not exists:
                response = f"**{session_name}**: does not exist"
            else:
                attached = status.get("attached", False)
                state = "attached" if attached else "detached"
                response = f"**{session_name}**: exists, {state}"

            await self.send_response(message.channel, response)
        except TmuxError as e:
            logger.exception("TMUX error while handling !status command")
            await self.send_response(message.channel, f"❌ TMUX error: {e}")

    async def _handle_raw_command(self, message: discord.Message) -> None:
        """Handle the !raw command to execute arbitrary tmux commands.

        Args:
            message: The Discord message containing the !raw command.
        """
        logger.debug("Handling !raw command")

        # Parse the tmux command from the message (everything after "!raw ")
        parts = message.content.split(maxsplit=1)
        if len(parts) < 2:
            await self.send_response(
                message.channel, "Usage: `!raw <tmux command>`\nExample: `!raw list-windows`"
            )
            return

        tmux_command = parts[1]
        logger.info("Executing raw tmux command: %s", tmux_command)

        try:
            output = self.tmux_client.run_raw_command(tmux_command)
            if output:
                await self.send_response(message.channel, f"```\n{output}\n```")
            else:
                await self.send_response(message.channel, "(no output)")
        except TmuxError as e:
            logger.exception("TMUX error while handling !raw command")
            await self.send_response(message.channel, f"❌ TMUX error: {e}")

    async def _handle_interrupt_command(self, message: discord.Message) -> None:
        """Handle the !interrupt command to send Ctrl+C to the TMUX pane.

        Args:
            message: The Discord message containing the !interrupt command.
        """
        logger.debug("Handling !interrupt command")
        try:
            if self.tmux_client.send_interrupt():
                await self.send_response(message.channel, "✅ Sent Ctrl+C to TMUX pane")
            else:
                await self.send_response(
                    message.channel,
                    "❌ Failed to send interrupt. The TMUX session may not exist.",
                )
        except TmuxError as e:
            logger.exception("TMUX error while handling !interrupt command")
            await self.send_response(message.channel, f"❌ TMUX error: {e}")

    async def _handle_passthrough(self, message: discord.Message) -> None:
        """Handle passthrough messages by running Claude Code in print mode.

        Executes `claude -p` with the message content and relays the response
        back to Discord. Shows typing indicator while waiting for response.

        Args:
            message: The Discord message to send to Claude Code.
        """
        logger.debug("Running Claude Code with prompt: %s", message.content)

        try:
            # Run Claude in print mode with typing indicator
            # Wrap typing indicator in try/except to handle Discord API errors
            try:
                async with message.channel.typing():
                    response = await self._run_claude_async(message.content)
            except discord.DiscordException:
                # Typing indicator failed, but we can still run without it
                logger.warning("Failed to show typing indicator, running without it")
                response = await self._run_claude_async(message.content)

            # Send response to Discord if there is any
            if response:
                await self.send_response(message.channel, response)
            else:
                logger.debug("No response from Claude")
        except TmuxError as e:
            logger.exception("Error while running Claude Code")
            await self.send_response(message.channel, f"❌ Claude error: {e}")

    async def _run_claude_async(self, prompt: str) -> str:
        """Run Claude Code in print mode asynchronously.

        Args:
            prompt: The prompt to send to Claude Code.

        Returns:
            Claude's response text.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.tmux_client.run_claude_print, prompt)

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

    async def send_response(
        self, channel: discord.abc.Messageable, text: str
    ) -> list[discord.Message]:
        """Send a response message to a channel, chunking if necessary.

        If the message exceeds Discord's limit, it will be split into multiple
        messages sent sequentially. Handles Discord API errors gracefully without
        crashing the bot.

        Args:
            channel: The channel or DM to send the response to.
            text: The text content to send.

        Returns:
            List of sent message objects (may be partial if some sends failed).
        """
        chunks = chunk_message(text)
        logger.debug("Sending response to channel %s (%d chunks)", channel, len(chunks))

        messages: list[discord.Message] = []
        for chunk in chunks:
            try:
                msg = await channel.send(chunk)
                messages.append(msg)
            except discord.HTTPException as e:
                logger.exception("Failed to send message to Discord: HTTP %s", e.status)
            except discord.Forbidden:
                logger.exception("Bot lacks permission to send messages in this channel")
                break
            except discord.DiscordException as e:
                logger.exception("Discord error while sending message: %s", e)

        return messages

    def run_bot(self) -> None:
        """Start the bot using the configured token."""
        self.run(self.config.discord_bot_token)
