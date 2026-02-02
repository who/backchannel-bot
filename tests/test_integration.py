"""Integration tests for backchannel-bot.

These tests verify the core functionality per PRD Success Criteria:
- Bot connects to Discord and responds to test messages
- Bot can run Claude Code in print mode
- Full round-trip works: Discord → Claude → Discord
- Messages over 2000 chars are chunked properly
- Typing indicator shows while waiting for response
- Basic error messages when things break
- Permission requests are displayed in Discord (bcb-ygj)
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backchannel_bot.claude_client import ClaudeClient, ClaudeError, PermissionRequest
from backchannel_bot.config import Config, ConfigurationError
from backchannel_bot.discord_client import (
    PERMISSION_ALLOW_EMOJI,
    PERMISSION_DENY_EMOJI,
    BackchannelBot,
    chunk_message,
)

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
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)
            assert bot.config == config
            assert bot.claude_client == claude_client

    def test_bot_has_message_content_intent(self) -> None:
        """Bot requests message content intent (required for reading messages)."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)
            assert bot.intents.message_content is True


# =============================================================================
# Test 2: Bot can run Claude Code in print mode
# =============================================================================


class TestClaudeClient:
    """Tests for Claude Code client."""

    def test_run_claude_print_calls_subprocess(self) -> None:
        """ClaudeClient.run_claude_print executes claude -p command."""
        client = ClaudeClient()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Claude response\n")
            result = client.run_claude_print("test prompt")
            assert result == "Claude response"
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "claude"
            assert call_args[1] == "-p"
            assert "test prompt" in call_args
            assert "--continue" in call_args

    def test_run_claude_print_fresh_mode(self) -> None:
        """ClaudeClient.run_claude_print with fresh mode doesn't add --continue."""
        client = ClaudeClient()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Response\n")
            client.run_claude_print("test", session_mode="fresh")
            call_args = mock_run.call_args[0][0]
            assert "--continue" not in call_args
            assert "--resume" not in call_args

    def test_run_claude_print_resume_mode(self) -> None:
        """ClaudeClient.run_claude_print with resume mode adds --resume flag."""
        client = ClaudeClient()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Response\n")
            client.run_claude_print("test", session_mode="resume:abc-123-def")
            call_args = mock_run.call_args[0][0]
            assert "--resume" in call_args
            assert "abc-123-def" in call_args

    def test_run_claude_print_raises_on_failure(self) -> None:
        """ClaudeClient.run_claude_print raises ClaudeError on command failure."""
        client = ClaudeClient()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error message")
            with pytest.raises(ClaudeError, match="Claude command failed"):
                client.run_claude_print("test")

    def test_run_claude_print_raises_on_missing_claude(self) -> None:
        """ClaudeClient.run_claude_print raises ClaudeError when claude not installed."""
        client = ClaudeClient()
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("claude not found")
            with pytest.raises(ClaudeError, match="Claude Code is not installed"):
                client.run_claude_print("test")


# =============================================================================
# Test 3: Full round-trip works: Discord → Claude → Discord
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
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            # Mock Claude print mode response
            claude_client.run_claude_print.return_value = "Hi there! How can I help you?"

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
            claude_client.run_claude_print.assert_called_once_with("hello", session_mode="continue")

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
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            claude_client.run_claude_print.side_effect = ClaudeError("command failed")

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
# Test: !session command with full IDs and numeric selection
# =============================================================================


class TestSessionCommand:
    """Tests for the !session command functionality."""

    @pytest.mark.asyncio
    async def test_session_list_shows_full_ids(self) -> None:
        """Session list shows full UUIDs, not truncated IDs."""
        from datetime import datetime

        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            # Mock session list with full UUIDs
            full_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            claude_client.list_claude_sessions.return_value = [
                {
                    "id": full_uuid,
                    "timestamp": datetime(2026, 2, 1, 15, 30),
                    "first_prompt": "Fix the login bug",
                }
            ]

            message = MagicMock()
            message.content = "!session"
            message.channel.send = AsyncMock()

            await bot._handle_session_command(message)

            # Verify full UUID is in output
            call_args = message.channel.send.call_args[0][0]
            assert full_uuid in call_args
            assert "a1b2c3d4..." not in call_args  # Should NOT be truncated

    @pytest.mark.asyncio
    async def test_session_numeric_selection(self) -> None:
        """Users can select session by number (e.g., !session 1)."""
        from datetime import datetime

        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            full_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            claude_client.list_claude_sessions.return_value = [
                {
                    "id": full_uuid,
                    "timestamp": datetime(2026, 2, 1, 15, 30),
                    "first_prompt": "Fix the login bug",
                }
            ]

            message = MagicMock()
            message.content = "!session 1"
            message.channel.send = AsyncMock()

            await bot._handle_session_command(message)

            # Verify session mode was set
            assert config.claude_session_mode == f"resume:{full_uuid}"
            call_args = message.channel.send.call_args[0][0]
            assert "✅" in call_args

    @pytest.mark.asyncio
    async def test_session_invalid_number(self) -> None:
        """Invalid session number gives helpful error."""
        from datetime import datetime

        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            claude_client.list_claude_sessions.return_value = [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "timestamp": datetime(2026, 2, 1, 15, 30),
                    "first_prompt": "Fix the login bug",
                }
            ]

            message = MagicMock()
            message.content = "!session 99"  # Invalid number
            message.channel.send = AsyncMock()

            await bot._handle_session_command(message)

            # Verify error message
            call_args = message.channel.send.call_args[0][0]
            assert "❌" in call_args
            assert "Invalid session number" in call_args


# =============================================================================
# Test 4: Messages over 2000 chars are chunked properly
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
# Test 5: Typing indicator shows while waiting for response
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
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            # Mock Claude print mode response
            claude_client.run_claude_print.return_value = "Response from Claude"

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
# Test 6: Basic error messages when things break
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
            },
            clear=True,
        ):
            config = Config()
            assert config.discord_channel_id is None
            assert config.discord_allowed_user_id is None

    def test_claude_not_installed_raises_error(self) -> None:
        """Missing claude binary raises ClaudeError."""
        client = ClaudeClient()
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            with pytest.raises(ClaudeError, match="Claude Code is not installed"):
                client.run_claude_print("test")

    @pytest.mark.asyncio
    async def test_claude_print_failure_reports_error(self) -> None:
        """Failed run_claude_print reports error to Discord."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            # Simulate Claude command failure
            claude_client.run_claude_print.side_effect = ClaudeError("Claude command failed")

            message = MagicMock()
            message.author.bot = False
            message.content = "test"
            message.channel.send = AsyncMock()

            await bot._handle_passthrough(message)

            # Verify error message sent
            call_args = message.channel.send.call_args[0][0]
            assert "Claude error" in call_args


# =============================================================================
# Test: Permission request display (bcb-ygj)
# =============================================================================


class TestPermissionRequestDisplay:
    """Tests for permission request display functionality."""

    @pytest.mark.asyncio
    async def test_format_bash_permission_request(self) -> None:
        """Bash permission requests are formatted correctly."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            perm_req = PermissionRequest(
                tool_name="Bash",
                tool_use_id="test-123",
                tool_input={
                    "command": "rm -rf /tmp/test",
                    "description": "Delete test files",
                },
            )

            formatted = await bot._format_permission_request(perm_req)

            assert "Permission Request" in formatted
            assert "Bash command" in formatted
            assert "rm -rf /tmp/test" in formatted
            assert "Delete test files" in formatted
            assert PERMISSION_ALLOW_EMOJI in formatted
            assert PERMISSION_DENY_EMOJI in formatted

    @pytest.mark.asyncio
    async def test_format_write_permission_request(self) -> None:
        """Write permission requests are formatted correctly."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            perm_req = PermissionRequest(
                tool_name="Write",
                tool_use_id="test-456",
                tool_input={
                    "file_path": "/tmp/hello.txt",
                    "content": "Hello, world!",
                },
            )

            formatted = await bot._format_permission_request(perm_req)

            assert "Permission Request" in formatted
            assert "write to file" in formatted
            assert "/tmp/hello.txt" in formatted
            assert "Hello, world!" in formatted

    @pytest.mark.asyncio
    async def test_format_edit_permission_request(self) -> None:
        """Edit permission requests are formatted correctly."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            perm_req = PermissionRequest(
                tool_name="Edit",
                tool_use_id="test-789",
                tool_input={
                    "file_path": "/tmp/config.py",
                    "old_string": "DEBUG = False",
                    "new_string": "DEBUG = True",
                },
            )

            formatted = await bot._format_permission_request(perm_req)

            assert "Permission Request" in formatted
            assert "edit file" in formatted
            assert "/tmp/config.py" in formatted
            assert "DEBUG = False" in formatted
            assert "DEBUG = True" in formatted

    @pytest.mark.asyncio
    async def test_format_generic_permission_request(self) -> None:
        """Generic/unknown tool permission requests are formatted correctly."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            perm_req = PermissionRequest(
                tool_name="CustomTool",
                tool_use_id="test-abc",
                tool_input={"param1": "value1", "param2": "value2"},
            )

            formatted = await bot._format_permission_request(perm_req)

            assert "Permission Request" in formatted
            assert "CustomTool" in formatted
            assert "param1" in formatted
            assert "value1" in formatted


class TestPermissionRequestFlow:
    """Tests for the permission request flow."""

    @pytest.mark.asyncio
    async def test_permission_request_adds_reactions(self) -> None:
        """Permission request message gets both reaction buttons added."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            # Mock the channel and message
            mock_message = AsyncMock()
            mock_message.add_reaction = AsyncMock()

            mock_channel = MagicMock()
            mock_channel.send = AsyncMock(return_value=mock_message)

            # Mock wait_for to simulate user allowing
            bot.wait_for = AsyncMock(
                return_value=(MagicMock(emoji=PERMISSION_ALLOW_EMOJI), MagicMock())
            )

            perm_req = PermissionRequest(
                tool_name="Bash",
                tool_use_id="test-123",
                tool_input={"command": "ls"},
            )

            result = await bot._request_permission(mock_channel, perm_req, 12345)

            # Verify reactions were added
            assert mock_message.add_reaction.call_count == 2
            calls = [call[0][0] for call in mock_message.add_reaction.call_args_list]
            assert PERMISSION_ALLOW_EMOJI in calls
            assert PERMISSION_DENY_EMOJI in calls

            # User allowed
            assert result is True

    @pytest.mark.asyncio
    async def test_permission_request_deny_returns_false(self) -> None:
        """Permission request returns False when user denies."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            mock_message = AsyncMock()
            mock_message.add_reaction = AsyncMock()

            mock_channel = MagicMock()
            mock_channel.send = AsyncMock(return_value=mock_message)

            # Mock wait_for to simulate user denying
            bot.wait_for = AsyncMock(
                return_value=(MagicMock(emoji=PERMISSION_DENY_EMOJI), MagicMock())
            )

            perm_req = PermissionRequest(
                tool_name="Bash",
                tool_use_id="test-123",
                tool_input={"command": "rm -rf /"},
            )

            result = await bot._request_permission(mock_channel, perm_req, 12345)

            assert result is False

    @pytest.mark.asyncio
    async def test_permission_request_timeout_returns_false(self) -> None:
        """Permission request returns False on timeout."""
        import asyncio

        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-token",
            },
        ):
            config = Config()
            claude_client = MagicMock(spec=ClaudeClient)
            bot = BackchannelBot(config=config, claude_client=claude_client)

            mock_message = AsyncMock()
            mock_message.add_reaction = AsyncMock()

            mock_channel = MagicMock()
            mock_channel.send = AsyncMock(return_value=mock_message)

            # Mock wait_for to simulate timeout
            bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError())

            perm_req = PermissionRequest(
                tool_name="Write",
                tool_use_id="test-456",
                tool_input={"file_path": "/test", "content": "test"},
            )

            result = await bot._request_permission(mock_channel, perm_req, 12345)

            assert result is False
            # Message should be edited to show timeout
            mock_message.edit.assert_called()
