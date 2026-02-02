"""Discord client module for backchannel-bot."""

import asyncio
import logging

import discord

from backchannel_bot.claude_client import ClaudeClient, ClaudeError
from backchannel_bot.config import Config

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
    """Discord client for backchannel communication with Claude Code."""

    def __init__(self, config: Config, claude_client: ClaudeClient) -> None:
        """Initialize the backchannel bot.

        Args:
            config: Bot configuration containing Discord token and settings.
            claude_client: Client for interacting with Claude Code CLI.
        """
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.config = config
        self.claude_client = claude_client

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

        if command == "!session":
            await self._handle_session_command(message)
        else:
            logger.debug("Unknown command: %s", command)

    async def _handle_session_command(self, message: discord.Message) -> None:
        """Handle the !session command to list/switch Claude sessions.

        Usage:
            !session - List recent sessions
            !session <id> - Set session mode to resume that session

        Args:
            message: The Discord message containing the !session command.
        """
        logger.debug("Handling !session command")
        parts = message.content.split(maxsplit=1)

        if len(parts) == 1:
            # List sessions
            sessions = self.claude_client.list_claude_sessions()
            if not sessions:
                await self.send_response(
                    message.channel,
                    "No Claude sessions found for this directory.\n"
                    "Sessions are created when you run `claude` interactively.",
                )
                return

            # Format session list
            lines = ["**Recent Claude Sessions:**\n"]
            for i, session in enumerate(sessions):
                ts = session["timestamp"].strftime("%Y-%m-%d %H:%M")
                prompt = session["first_prompt"]
                if len(prompt) > 50:
                    prompt = prompt[:47] + "..."
                lines.append(f"{i + 1}. `{session['id']}` ({ts})")
                lines.append(f"   {prompt}\n")

            lines.append("\n**Current mode:** " + self.config.claude_session_mode)
            lines.append("\nTo switch: `!session <number>` or `!session <id>`")
            await self.send_response(message.channel, "\n".join(lines))
        else:
            # Set session mode to resume specific session
            arg = parts[1].strip()

            # Check if it's a number (for selecting from list)
            if arg.isdigit():
                session_num = int(arg)
                sessions = self.claude_client.list_claude_sessions()
                if sessions and 1 <= session_num <= len(sessions):
                    session_id = sessions[session_num - 1]["id"]
                    self.config.claude_session_mode = f"resume:{session_id}"
                    await self.send_response(
                        message.channel,
                        f"✅ Session mode set to resume `{session_id[:8]}...`\n"
                        "Future messages will continue that session.",
                    )
                else:
                    await self.send_response(
                        message.channel,
                        f"❌ Invalid session number: `{arg}`\n"
                        "Run `!session` to see available sessions.",
                    )
            # Validate it looks like a UUID
            elif len(arg) == 36 and arg.count("-") == 4:
                self.config.claude_session_mode = f"resume:{arg}"
                await self.send_response(
                    message.channel,
                    f"✅ Session mode set to resume `{arg[:8]}...`\n"
                    "Future messages will continue that session.",
                )
            elif arg.lower() in ("continue", "fresh"):
                self.config.claude_session_mode = arg.lower()
                await self.send_response(message.channel, f"✅ Session mode set to `{arg.lower()}`")
            else:
                await self.send_response(
                    message.channel,
                    f"❌ Invalid session ID: `{arg}`\n"
                    "Use a number, full session UUID, or 'continue' / 'fresh'.",
                )

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
        except ClaudeError as e:
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
        return await loop.run_in_executor(
            None,
            lambda: self.claude_client.run_claude_print(
                prompt, session_mode=self.config.claude_session_mode
            ),
        )

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
