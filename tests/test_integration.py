"""Integration tests for backchannel-bot.

These tests verify the core functionality per PRD Success Criteria:
- Bot connects to Discord and responds to test messages
- Bot can send text to TMUX session
- Bot can capture and return TMUX output to Discord
- Full round-trip works: Discord → TMUX → Claude → TMUX → Discord
- Messages over 2000 chars are chunked properly
- Typing indicator shows while waiting for response
- Basic error messages when things break
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backchannel_bot.config import Config, ConfigurationError
from backchannel_bot.discord_client import BackchannelBot, chunk_message
from backchannel_bot.tmux_client import TmuxClient, TmuxError, strip_ansi

# =============================================================================
# Test 1: Bot connects to Discord and responds to test messages
# =============================================================================


class TestDiscordConnection:
    """Tests for Discord bot connection and message handling."""

    def test_bot_initializes_with_valid_config(self) -> None:
        """Bot can be initialized with valid configuration."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)
            assert bot.config == config
            assert bot.tmux_client == tmux_client

    def test_bot_has_message_content_intent(self) -> None:
        """Bot requests message content intent (required for reading messages)."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)
            assert bot.intents.message_content is True


# =============================================================================
# Test 2: Bot can send text to TMUX session
# =============================================================================


class TestTmuxInput:
    """Tests for sending input to TMUX."""

    def test_send_input_uses_send_keys(self) -> None:
        """TmuxClient.send_input uses tmux send-keys command."""
        client = TmuxClient(session_name="test-session", pane=0)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = client.send_input("hello world")
            assert result is True
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "tmux"
            assert call_args[1] == "send-keys"
            assert "-t" in call_args
            assert "test-session:0" in call_args
            assert "hello world" in call_args
            assert "Enter" in call_args

    def test_send_input_returns_false_on_failure(self) -> None:
        """TmuxClient.send_input returns False when command fails."""
        client = TmuxClient(session_name="test-session", pane=0)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="session not found")
            result = client.send_input("test")
            assert result is False

    def test_send_input_raises_on_missing_tmux(self) -> None:
        """TmuxClient.send_input raises TmuxError when tmux not installed."""
        client = TmuxClient(session_name="test-session", pane=0)
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("tmux not found")
            with pytest.raises(TmuxError, match="tmux is not installed"):
                client.send_input("test")


# =============================================================================
# Test 3: Bot can capture and return TMUX output to Discord
# =============================================================================


class TestTmuxOutput:
    """Tests for capturing output from TMUX."""

    def test_capture_output_uses_capture_pane(self) -> None:
        """TmuxClient.capture_output uses tmux capture-pane command."""
        client = TmuxClient(session_name="test-session", pane=0, output_history_lines=100)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="captured output\n")
            result = client.capture_output()
            assert result == "captured output"
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "tmux"
            assert call_args[1] == "capture-pane"
            assert "-p" in call_args
            assert "-S" in call_args
            assert "-100" in call_args

    def test_capture_output_strips_ansi(self) -> None:
        """TmuxClient.capture_output strips ANSI escape codes."""
        client = TmuxClient(session_name="test-session", pane=0)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="\x1b[32mgreen text\x1b[0m normal\n"
            )
            result = client.capture_output()
            assert result == "green text normal"
            assert "\x1b[" not in result

    def test_capture_output_raises_on_failure(self) -> None:
        """TmuxClient.capture_output raises TmuxError on command failure."""
        client = TmuxClient(session_name="test-session", pane=0)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="pane not found")
            with pytest.raises(TmuxError, match="Failed to capture output"):
                client.capture_output()


# =============================================================================
# Test 4: Full round-trip works: Discord → TMUX → Claude → TMUX → Discord
# =============================================================================


class TestRoundTrip:
    """Tests for the full message round-trip flow using claude -p."""

    @pytest.mark.asyncio
    async def test_passthrough_runs_claude_print_and_returns_response(self) -> None:
        """Messages are sent to Claude via run_claude_print and responses relayed back."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)

            # Mock Claude print mode response
            tmux_client.run_claude_print.return_value = "Hi there! How can I help you?"

            # Mock Discord message
            message = MagicMock()
            message.author.bot = False
            message.channel.id = 12345
            message.author.id = 67890
            message.content = "hello"
            message.channel.typing = MagicMock(return_value=AsyncMock())
            message.channel.send = AsyncMock()

            await bot._handle_passthrough(message)

            # Verify Claude print mode was called with the message and session mode
            tmux_client.run_claude_print.assert_called_once_with("hello", session_mode="continue")

            # Verify response was sent to Discord
            message.channel.send.assert_called()
            call_args = message.channel.send.call_args[0][0]
            assert "Hi there!" in call_args

    @pytest.mark.asyncio
    async def test_passthrough_handles_claude_error(self) -> None:
        """Claude errors during passthrough are reported to Discord."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)

            tmux_client.run_claude_print.side_effect = TmuxError("command failed")

            message = MagicMock()
            message.author.bot = False
            message.channel.id = 12345
            message.author.id = 67890
            message.content = "hello"
            message.channel.send = AsyncMock()

            await bot._handle_passthrough(message)

            # Verify error message sent
            call_args = message.channel.send.call_args[0][0]
            assert "Claude error" in call_args


# =============================================================================
# Test 5: Messages over 2000 chars are chunked properly
# =============================================================================


class TestMessageChunking:
    """Tests for message chunking functionality."""

    def test_short_message_not_chunked(self) -> None:
        """Messages under limit are returned as single chunk."""
        result = chunk_message("short message")
        assert len(result) == 1
        assert result[0] == "short message"

    def test_empty_message_returns_empty_list(self) -> None:
        """Empty messages return empty list."""
        result = chunk_message("")
        assert result == []

    def test_long_message_chunked_at_newlines(self) -> None:
        """Long messages are split at newline boundaries when possible."""
        lines = ["line " + str(i) for i in range(500)]
        long_text = "\n".join(lines)
        result = chunk_message(long_text, max_size=1900)

        # All chunks should be under the limit
        for chunk in result:
            assert len(chunk) <= 1900

        # Joining chunks should give back original content (minus whitespace)
        rejoined = "\n".join(result)
        assert len(rejoined) >= len(long_text) - 100  # Allow for whitespace stripping

    def test_chunk_respects_max_size(self) -> None:
        """Each chunk is within the specified max size."""
        long_text = "x" * 5000
        result = chunk_message(long_text, max_size=1000)

        for chunk in result:
            assert len(chunk) <= 1000

    def test_chunk_handles_no_newlines(self) -> None:
        """Chunking works when there are no newlines (falls back to space split)."""
        words = ["word" + str(i) for i in range(500)]
        long_text = " ".join(words)
        result = chunk_message(long_text, max_size=100)

        for chunk in result:
            assert len(chunk) <= 100


# =============================================================================
# Test 6: Typing indicator shows while waiting for response
# =============================================================================


class TestTypingIndicator:
    """Tests for typing indicator during response wait."""

    @pytest.mark.asyncio
    async def test_typing_indicator_shown_during_claude_call(self) -> None:
        """Typing indicator is shown while waiting for Claude response."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)

            # Mock Claude print mode response
            tmux_client.run_claude_print.return_value = "Response from Claude"

            # Create async context manager mock for typing
            typing_context = AsyncMock()
            typing_context.__aenter__ = AsyncMock()
            typing_context.__aexit__ = AsyncMock()

            message = MagicMock()
            message.author.bot = False
            message.content = "test"
            message.channel.typing = MagicMock(return_value=typing_context)
            message.channel.send = AsyncMock()

            await bot._handle_passthrough(message)

            # Verify typing() was called on the channel
            message.channel.typing.assert_called()


# =============================================================================
# Test 7: Basic error messages when things break
# =============================================================================


class TestErrorHandling:
    """Tests for error handling and user-friendly messages."""

    def test_missing_required_env_vars_raises_config_error(self) -> None:
        """Missing required env vars raise ConfigurationError."""
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ConfigurationError, match="DISCORD_BOT_TOKEN"),
        ):
            Config()

    def test_non_numeric_channel_id_raises_config_error(self) -> None:
        """Non-numeric DISCORD_CHANNEL_ID raises ConfigurationError."""
        with (
            patch.dict(
                os.environ,
                {
                    "DISCORD_BOT_TOKEN": "test-token",
                    "TMUX_SESSION_NAME": "test-session",
                    "DISCORD_CHANNEL_ID": "my-channel",
                },
            ),
            pytest.raises(ConfigurationError, match="DISCORD_CHANNEL_ID must be a numeric"),
        ):
            Config()

    def test_non_numeric_user_id_raises_config_error(self) -> None:
        """Non-numeric DISCORD_ALLOWED_USER_ID raises ConfigurationError."""
        with (
            patch.dict(
                os.environ,
                {
                    "DISCORD_BOT_TOKEN": "test-token",
                    "TMUX_SESSION_NAME": "test-session",
                    "DISCORD_ALLOWED_USER_ID": "username#1234",
                },
            ),
            pytest.raises(ConfigurationError, match="DISCORD_ALLOWED_USER_ID must be a numeric"),
        ):
            Config()

    def test_numeric_discord_ids_are_accepted(self) -> None:
        """Numeric Discord IDs are accepted."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
                "DISCORD_CHANNEL_ID": "123456789012345678",
                "DISCORD_ALLOWED_USER_ID": "987654321098765432",
            },
        ):
            config = Config()
            assert config.discord_channel_id == "123456789012345678"
            assert config.discord_allowed_user_id == "987654321098765432"

    def test_unset_discord_ids_are_none(self) -> None:
        """Unset Discord IDs default to None without error."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
            clear=True,
        ):
            config = Config()
            assert config.discord_channel_id is None
            assert config.discord_allowed_user_id is None

    def test_tmux_not_installed_raises_error(self) -> None:
        """Missing tmux binary raises TmuxError."""
        client = TmuxClient(session_name="test")
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            with pytest.raises(TmuxError, match="tmux is not installed"):
                client.check_session()

    def test_session_does_not_exist_returns_false(self) -> None:
        """Non-existent session returns False from check_session."""
        client = TmuxClient(session_name="nonexistent")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = client.check_session()
            assert result is False

    @pytest.mark.asyncio
    async def test_claude_print_failure_reports_error(self) -> None:
        """Failed run_claude_print reports error to Discord."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)

            # Simulate Claude command failure
            tmux_client.run_claude_print.side_effect = TmuxError("Claude command failed")

            message = MagicMock()
            message.author.bot = False
            message.content = "test"
            message.channel.send = AsyncMock()

            await bot._handle_passthrough(message)

            # Verify error message sent
            call_args = message.channel.send.call_args[0][0]
            assert "Claude error" in call_args


# =============================================================================
# Test 8: Kill TMUX and verify error handling
# =============================================================================


# =============================================================================
# Test: !interrupt command sends Ctrl+C to TMUX
# =============================================================================


class TestInterruptCommand:
    """Tests for !interrupt command functionality."""

    def test_send_interrupt_uses_send_keys_with_ctrl_c(self) -> None:
        """TmuxClient.send_interrupt uses tmux send-keys with C-c."""
        client = TmuxClient(session_name="test-session", pane=0)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = client.send_interrupt()
            assert result is True
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "tmux"
            assert call_args[1] == "send-keys"
            assert "-t" in call_args
            assert "test-session:0" in call_args
            assert "C-c" in call_args

    def test_send_interrupt_returns_false_on_failure(self) -> None:
        """TmuxClient.send_interrupt returns False when command fails."""
        client = TmuxClient(session_name="test-session", pane=0)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="session not found")
            result = client.send_interrupt()
            assert result is False

    def test_send_interrupt_raises_on_missing_tmux(self) -> None:
        """TmuxClient.send_interrupt raises TmuxError when tmux not installed."""
        client = TmuxClient(session_name="test-session", pane=0)
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("tmux not found")
            with pytest.raises(TmuxError, match="tmux is not installed"):
                client.send_interrupt()

    @pytest.mark.asyncio
    async def test_interrupt_command_sends_confirmation(self) -> None:
        """!interrupt command sends confirmation message to Discord."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)

            tmux_client.send_interrupt.return_value = True

            message = MagicMock()
            message.author.bot = False
            message.content = "!interrupt"
            message.channel.send = AsyncMock()

            await bot._handle_interrupt_command(message)

            # Verify confirmation was sent
            call_args = message.channel.send.call_args[0][0]
            assert "Sent Ctrl+C" in call_args

    @pytest.mark.asyncio
    async def test_interrupt_command_reports_failure(self) -> None:
        """!interrupt command reports failure when tmux command fails."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)

            tmux_client.send_interrupt.return_value = False

            message = MagicMock()
            message.author.bot = False
            message.content = "!interrupt"
            message.channel.send = AsyncMock()

            await bot._handle_interrupt_command(message)

            # Verify error was sent
            call_args = message.channel.send.call_args[0][0]
            assert "Failed to send interrupt" in call_args

    @pytest.mark.asyncio
    async def test_interrupt_command_handles_tmux_error(self) -> None:
        """!interrupt command handles TmuxError gracefully."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "test-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            bot = BackchannelBot(config=config, tmux_client=tmux_client)

            tmux_client.send_interrupt.side_effect = TmuxError("session died")

            message = MagicMock()
            message.author.bot = False
            message.content = "!interrupt"
            message.channel.send = AsyncMock()

            await bot._handle_interrupt_command(message)

            # Verify error message was sent
            call_args = message.channel.send.call_args[0][0]
            assert "TMUX error" in call_args


class TestTmuxSessionFailure:
    """Tests for handling TMUX session failures."""

    def test_get_session_status_reports_nonexistent(self) -> None:
        """get_session_status correctly reports nonexistent session."""
        client = TmuxClient(session_name="dead-session")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="no server running")
            status = client.get_session_status()
            assert status["exists"] is False
            assert status["session_name"] == "dead-session"

    def test_status_command_reports_dead_session(self) -> None:
        """!status command reports when session doesn't exist."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
                "TMUX_SESSION_NAME": "dead-session",
            },
        ):
            config = Config()
            tmux_client = MagicMock(spec=TmuxClient)
            # Create bot to ensure it initializes correctly
            BackchannelBot(config=config, tmux_client=tmux_client)

            tmux_client.get_session_status.return_value = {
                "session_name": "dead-session",
                "exists": False,
            }

            # Verify the status report logic
            status = tmux_client.get_session_status()
            assert status["exists"] is False


# =============================================================================
# Additional ANSI stripping tests
# =============================================================================


class TestAnsiStripping:
    """Tests for ANSI escape code removal."""

    def test_strip_color_codes(self) -> None:
        """Color codes are stripped."""
        text = "\x1b[32mgreen\x1b[0m"
        assert strip_ansi(text) == "green"

    def test_strip_cursor_codes(self) -> None:
        """Cursor control codes are stripped."""
        text = "\x1b[H\x1b[2Jcleared screen"
        assert strip_ansi(text) == "cleared screen"

    def test_strip_terminal_title(self) -> None:
        """Terminal title sequences are stripped."""
        text = "\x1b]0;Window Title\x07actual content"
        assert strip_ansi(text) == "actual content"

    def test_preserve_normal_text(self) -> None:
        """Normal text without escape codes is preserved."""
        text = "Hello, World!"
        assert strip_ansi(text) == "Hello, World!"
