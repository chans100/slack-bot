"""
Integration Tests for Slack Interactions

Tests the bot's integration with Slack API:
- Event handling
- Command processing
- Interactive components
- Webhook responses
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import time

class TestSlackIntegration:
    """Test class for Slack integration functionality."""
    
    def test_slack_event_subscription(self, mock_slack_client):
        """Test Slack event subscription handling."""
        from events import handle_slack_event
        
        # Test URL verification challenge
        challenge_event = {
            "type": "url_verification",
            "challenge": "test_challenge_string"
        }
        
        response = handle_slack_event(challenge_event)
        assert response == "test_challenge_string"
        
        # Test bot message event (should be ignored)
        bot_message_event = {
            "type": "message",
            "user": "U123",
            "text": "Hello",
            "bot_id": "B123"  # Bot message
        }
        
        response = handle_slack_event(bot_message_event)
        assert response is None
    
    def test_slack_command_handling(self, mock_slack_client):
        """Test Slack slash command handling."""
        from commands import handle_slack_command
        
        # Test standup command
        standup_command = {
            "user_id": "U123",
            "command": "/standup",
            "text": "",
            "channel_id": "C123"
        }
        
        with patch('commands._handle_standup_command') as mock_standup:
            mock_standup.return_value = "Standup handled"
            response = handle_slack_command(standup_command)
            assert response == "Standup handled"
        
        # Test health command
        health_command = {
            "user_id": "U123",
            "command": "/health",
            "text": "",
            "channel_id": "C123"
        }
        
        with patch('commands._handle_health_command') as mock_health:
            mock_health.return_value = "Health check handled"
            response = handle_slack_command(health_command)
            assert response == "Health check handled"
    
    def test_interactive_component_handling(self, mock_slack_client):
        """Test interactive component handling."""
        from events import handle_interactive_components
        
        # Test button click
        button_payload = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "actions": [{"action_id": "test_button", "value": "test_value"}],
            "channel": {"id": "C123"}
        }
        
        with patch('events.handle_button_click') as mock_button:
            mock_button.return_value = True
            response = handle_interactive_components(button_payload)
            assert response is True
        
        # Test modal submission
        modal_payload = {
            "type": "view_submission",
            "user": {"id": "U123"},
            "view": {"callback_id": "test_modal"}
        }
        
        with patch('events.handle_modal_submission') as mock_modal:
            mock_modal.return_value = True
            response = handle_interactive_components(modal_payload)
            assert response is True
    
    def test_modal_creation_and_submission(self, mock_slack_client):
        """Test modal creation and submission flow."""
        from events import handle_open_blocker_report_modal, handle_submit_blocker_form
        
        # Test opening blocker modal
        open_payload = {
            "user": {"id": "U123"},
            "trigger_id": "trigger123"
        }
        
        with patch('events.bot.open_modal') as mock_open:
            mock_open.return_value = True
            response = handle_open_blocker_report_modal(mock_slack_client, open_payload)
            assert response is True
        
        # Test modal submission
        submit_payload = {
            "user": {"id": "U123"},
            "view": {
                "state": {
                    "values": {
                        "kr_name": {"kr_name": {"value": "Test KR"}},
                        "blocker_description": {"blocker_description": {"value": "Test blocker"}},
                        "urgency": {"urgency": {"selected_option": {"value": "high"}}},
                        "sprint_number": {"sprint_number": {"value": "5"}}
                    }
                }
            }
        }
        
        with patch('events.bot.escalate_blocker_with_details') as mock_escalate:
            mock_escalate.return_value = True
            response = handle_submit_blocker_form(mock_slack_client, submit_payload)
            assert response is True
    
    def test_message_threading(self, mock_slack_client):
        """Test message threading functionality."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test thread creation
        thread_message = {
            "channel": "C123",
            "text": "Thread reply",
            "thread_ts": "1234567890.123"
        }
        
        with patch.object(bot.client, 'chat_postMessage') as mock_post:
            mock_post.return_value = {'ok': True}
            result = bot.send_thread_message("C123", "Thread reply", "1234567890.123")
            assert result is True
            
            # Verify thread_ts was passed
            mock_post.assert_called_with(
                channel="C123",
                text="Thread reply",
                thread_ts="1234567890.123"
            )
    
    def test_channel_management(self, mock_slack_client):
        """Test channel management functionality."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test getting channel info
        mock_slack_client.conversations_info.return_value = {
            'ok': True,
            'channel': {'name': 'test-channel', 'id': 'C123'}
        }
        
        channel_info = bot.get_channel_info("C123")
        assert channel_info['name'] == 'test-channel'
        assert channel_info['id'] == 'C123'
        
        # Test listing channels
        mock_slack_client.conversations_list.return_value = {
            'ok': True,
            'channels': [
                {'name': 'general', 'id': 'C123'},
                {'name': 'random', 'id': 'C456'}
            ]
        }
        
        channels = bot.list_channels()
        assert len(channels) == 2
        assert channels[0]['name'] == 'general'
    
    def test_user_management(self, mock_slack_client):
        """Test user management functionality."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test getting user info
        mock_slack_client.users_info.return_value = {
            'ok': True,
            'user': {
                'id': 'U123',
                'name': 'testuser',
                'real_name': 'Test User',
                'is_bot': False,
                'is_admin': False
            }
        }
        
        user_info = bot.get_user_info("U123")
        assert user_info['name'] == 'testuser'
        assert user_info['real_name'] == 'Test User'
        assert user_info['is_bot'] is False
        
        # Test listing users
        mock_slack_client.users_list.return_value = {
            'ok': True,
            'members': [
                {'id': 'U123', 'name': 'user1', 'is_bot': False},
                {'id': 'U456', 'name': 'user2', 'is_bot': False}
            ]
        }
        
        users = bot.list_users()
        assert len(users) == 2
        assert users[0]['name'] == 'user1'
    
    def test_file_upload(self, mock_slack_client):
        """Test file upload functionality."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test file upload
        mock_slack_client.files_upload.return_value = {
            'ok': True,
            'file': {'id': 'F123', 'name': 'test.txt'}
        }
        
        result = bot.upload_file("C123", "test.txt", "Test content")
        assert result is True
        
        # Verify file upload was called
        mock_slack_client.files_upload.assert_called_once()
    
    def test_reaction_handling(self, mock_slack_client):
        """Test reaction handling functionality."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Test adding reaction
        mock_slack_client.reactions_add.return_value = {'ok': True}
        
        result = bot.add_reaction("C123", "1234567890.123", "thumbsup")
        assert result is True
        
        # Test removing reaction
        mock_slack_client.reactions_remove.return_value = {'ok': True}
        
        result = bot.remove_reaction("C123", "1234567890.123", "thumbsup")
        assert result is True
    
    def test_webhook_response_formatting(self, mock_slack_client):
        """Test webhook response formatting."""
        from events import format_webhook_response
        
        # Test success response
        success_response = format_webhook_response(True, "Success message")
        assert success_response['response_type'] == 'in_channel'
        assert 'Success message' in success_response['text']
        
        # Test error response
        error_response = format_webhook_response(False, "Error message")
        assert error_response['response_type'] == 'ephemeral'
        assert 'Error message' in error_response['text']
    
    def test_rate_limiting_handling(self, mock_slack_client):
        """Test rate limiting handling."""
        from bot import SlackBot
        
        bot = SlackBot()
        bot.client = mock_slack_client
        
        # Simulate rate limiting error
        mock_slack_client.chat_postMessage.side_effect = Exception("rate_limited")
        
        # Should handle rate limiting gracefully
        result = bot.send_dm("U123", "Test message")
        assert result is False
        
        # Test retry logic
        with patch('time.sleep') as mock_sleep:
            mock_slack_client.chat_postMessage.side_effect = [Exception("rate_limited"), {'ok': True}]
            result = bot.send_dm_with_retry("U123", "Test message", max_retries=2)
            assert result is True
            mock_sleep.assert_called()


# Test fixtures for Slack integration
@pytest.fixture
def sample_slack_event():
    """Sample Slack event for testing."""
    return {
        "type": "message",
        "user": "U123",
        "text": "Hello bot",
        "channel": "C123",
        "ts": "1234567890.123"
    }

@pytest.fixture
def sample_slack_command():
    """Sample Slack command for testing."""
    return {
        "user_id": "U123",
        "command": "/standup",
        "text": "",
        "channel_id": "C123",
        "response_url": "https://hooks.slack.com/commands/T123/456/789"
    }

@pytest.fixture
def sample_interactive_payload():
    """Sample interactive payload for testing."""
    return {
        "type": "block_actions",
        "user": {"id": "U123", "username": "testuser"},
        "actions": [{"action_id": "test_action", "value": "test_value"}],
        "channel": {"id": "C123"},
        "message": {"ts": "1234567890.123"}
    } 