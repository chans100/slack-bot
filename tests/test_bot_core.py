"""
Unit Tests for Core Bot Functionality

Tests the main bot methods and functionality:
- Message handling
- Command processing
- User management
- Channel interactions
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

class TestBotCore:
    """Test class for core bot functionality."""
    
    def test_bot_initialization(self, mock_slack_client, mock_coda_service):
        """Test bot initialization."""
        from bot import SlackBot
        
        # Mock environment variables
        with patch.dict('os.environ', {
            'SLACK_BOT_TOKEN': 'xoxb-test-token',
            'SLACK_APP_TOKEN': 'xapp-test-token',
            'CODA_API_TOKEN': 'test-coda-token',
            'HEALTH_CHECK_TABLE': 'test-health-table',
            'BLOCKER_TABLE': 'test-blocker-table',
            'KR_TABLE': 'test-kr-table'
        }):
            bot = SlackBot()
            
            assert bot.client is not None
            assert bot.coda is not None
            assert bot.admin_users == set()
    
    def test_send_dm(self, mock_slack_client):
        """Test sending direct messages."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test sending simple message
        result = bot.send_dm("U123", "Hello there!")
        assert result is True
        
        # Test sending message with blocks
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Test block"}}]
        result = bot.send_dm("U123", "Message with blocks", blocks=blocks)
        assert result is True
        
        # Verify Slack client was called
        mock_slack_client.conversations_open.assert_called()
        mock_slack_client.chat_postMessage.assert_called()
    
    def test_get_user_name(self, mock_slack_client):
        """Test getting user names."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Mock user info response
        mock_slack_client.users_info.return_value = {
            'ok': True,
            'user': {'name': 'testuser', 'real_name': 'Test User'}
        }
        
        user_name = bot.get_user_name("U123")
        assert user_name == "testuser"
        
        # Test with real name fallback
        mock_slack_client.users_info.return_value = {
            'ok': True,
            'user': {'name': '', 'real_name': 'Test User'}
        }
        
        user_name = bot.get_user_name("U123")
        assert user_name == "Test User"
    
    def test_handle_message(self, mock_slack_client):
        """Test message handling."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test valid message
        message_payload = {
            "user": "U123",
            "channel": "C123",
            "text": "Hello bot",
            "ts": "1234567890.123"
        }
        
        with patch.object(bot, 'process_message') as mock_process:
            mock_process.return_value = True
            result = bot.handle_message(message_payload)
            assert result is True
    
    def test_command_parsing(self, mock_slack_client):
        """Test command parsing."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test various command formats
        test_cases = [
            ("/standup", ("standup", "")),
            ("/health", ("health", "")),
            ("/blocker", ("blocker", "")),
            ("/kr 5", ("kr", "5")),
            ("/kr 5 user engagement", ("kr", "5 user engagement")),
            ("/help", ("help", "")),
            ("/admin", ("admin", "")),
        ]
        
        for command_text, expected in test_cases:
            command, args = bot.parse_command(command_text)
            assert (command, args) == expected
    
    def test_admin_validation(self, mock_slack_client):
        """Test admin user validation."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        bot.admin_users = {"U123", "U456"}
        
        # Test admin users
        assert bot.is_admin("U123") is True
        assert bot.is_admin("U456") is True
        
        # Test non-admin users
        assert bot.is_admin("U789") is False
        assert bot.is_admin("") is False
    
    def test_open_modal(self, mock_slack_client):
        """Test opening modals."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test modal opening
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Test"}}]
        result = bot.open_modal(
            trigger_id="trigger123",
            title="Test Modal",
            blocks=blocks,
            submit_text="Submit",
            callback_id="test_callback"
        )
        
        assert result is True
        mock_slack_client.views_open.assert_called_once()
    
    def test_error_handling(self, mock_slack_client):
        """Test error handling in bot operations."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test Slack API error
        mock_slack_client.chat_postMessage.side_effect = Exception("Slack API error")
        
        # Should handle error gracefully
        result = bot.send_dm("U123", "Test message")
        assert result is False
    
    def test_coda_integration(self, mock_slack_client, mock_coda_service):
        """Test Coda service integration."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        bot.coda = mock_coda_service
        
        # Test health check saving
        result = bot.coda.add_response(
            user_id="U123",
            response_text="Feeling great today!",
            username="testuser"
        )
        assert result is True
        
        # Test blocker saving
        result = bot.coda.add_blocker(
            user_id="U123",
            blocker_description="API integration issue",
            kr_name="KR1: Improve performance",
            urgency="high"
        )
        assert result is True
    
    def test_scheduling_functionality(self, mock_slack_client):
        """Test scheduling functionality."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test scheduling standup
        with patch('schedule.every') as mock_schedule:
            bot.schedule_standup()
            mock_schedule.assert_called()
        
        # Test scheduling health check
        with patch('schedule.every') as mock_schedule:
            bot.schedule_health_check()
            mock_schedule.assert_called()
    
    def test_message_formatting(self, mock_slack_client):
        """Test message formatting utilities."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test formatting standup message
        standup_text = bot.format_standup_message()
        assert "standup" in standup_text.lower()
        assert "today" in standup_text.lower()
        
        # Test formatting health check message
        health_text = bot.format_health_check_message()
        assert "health" in health_text.lower()
        assert "feeling" in health_text.lower()
    
    def test_user_interaction_handling(self, mock_slack_client):
        """Test user interaction handling."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test button click handling
        button_payload = {
            "user": {"id": "U123"},
            "actions": [{"action_id": "test_action", "value": "test_value"}],
            "channel": {"id": "C123"}
        }
        
        with patch.object(bot, 'handle_button_click') as mock_handle:
            mock_handle.return_value = True
            result = bot.handle_interaction(button_payload)
            assert result is True
    
    def test_data_persistence(self, mock_slack_client):
        """Test data persistence functionality."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test storing pending data
        bot.store_kr_pending_data("U123", search_term="test", sprint_number="5")
        assert "U123" in bot.pending_kr_search
        
        # Test clearing pending data
        bot.clear_pending_data("U123", "kr")
        assert "U123" not in bot.pending_kr_search
        
        # Test storing blocker data
        bot.store_blocker_pending_data("U123", kr_name="test", urgency="high")
        assert "U123" in bot.pending_blocker_sprint


# Test fixtures for pytest
@pytest.fixture
def sample_message_payload():
    """Sample message payload for testing."""
    return {
        "user": "U123",
        "channel": "C123",
        "text": "Hello bot",
        "ts": "1234567890.123"
    }

@pytest.fixture
def sample_command_payload():
    """Sample command payload for testing."""
    return {
        "user_id": "U123",
        "command": "/standup",
        "text": "",
        "channel_id": "C123"
    }

@pytest.fixture
def sample_interaction_payload():
    """Sample interaction payload for testing."""
    return {
        "user": {"id": "U123"},
        "actions": [{"action_id": "test_action", "value": "test_value"}],
        "channel": {"id": "C123"}
    } 