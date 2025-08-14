import pytest
from unittest.mock import Mock, MagicMock
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

@pytest.fixture
def mock_slack_client():
    """Mock Slack client for testing."""
    client = Mock()
    client.chat_postMessage = Mock(return_value={'ok': True})
    client.conversations_open = Mock(return_value={'ok': True, 'channel': {'id': 'D123456'}})
    client.views_open = Mock(return_value={'ok': True})
    return client

@pytest.fixture
def mock_coda_service():
    """Mock Coda service for testing."""
    coda = Mock()
    coda.add_response = Mock(return_value=True)
    coda.add_blocker = Mock(return_value=True)
    coda.search_kr_table = Mock(return_value=[{'name': 'Test KR', 'owner': 'Test User'}])
    coda.get_user_blockers_by_sprint = Mock(return_value=[])
    return coda

@pytest.fixture
def sample_user():
    """Sample user data for testing."""
    return {
        'id': 'U123456',
        'name': 'testuser',
        'real_name': 'Test User'
    }

@pytest.fixture
def sample_channel():
    """Sample channel data for testing."""
    return {
        'id': 'C123456',
        'name': 'test-channel'
    } 