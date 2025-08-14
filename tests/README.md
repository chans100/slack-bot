# Testing Framework for Slack Standup Bot

This directory contains comprehensive testing for the Slack Standup Bot, including unit tests, integration tests, and aggression testing.

## 🧪 Test Structure

```
tests/
├── __init__.py              # Package initialization
├── conftest.py              # Pytest configuration and fixtures
├── test_aggression.py       # Aggression testing (load, stress, edge cases)
├── test_bot_core.py         # Core bot functionality tests
├── test_slack_integration.py # Slack API integration tests
└── README.md                # This file
```

## 🚀 Quick Start

### Install Test Dependencies
```bash
pip install -r requirements-test.txt
```

### Run All Tests
```bash
python run_tests.py --all
```

### Run Specific Test Types
```bash
# Unit tests only
python run_tests.py --unit

# Integration tests only
python run_tests.py --integration

# Aggression tests only
python run_tests.py --aggression

# With coverage report
python run_tests.py --coverage

# Code quality checks
python run_tests.py --lint

# Security checks
python run_tests.py --security
```

## 🎯 Test Categories

### 1. Unit Tests (`test_bot_core.py`)
- **Bot Initialization**: Tests bot setup and configuration
- **Message Handling**: Tests message processing and routing
- **Command Parsing**: Tests slash command parsing
- **User Management**: Tests user validation and admin checks
- **Modal Operations**: Tests modal creation and handling
- **Error Handling**: Tests graceful error handling
- **Data Persistence**: Tests pending data storage and retrieval

### 2. Integration Tests (`test_slack_integration.py`)
- **Event Subscription**: Tests Slack event handling
- **Command Processing**: Tests slash command responses
- **Interactive Components**: Tests button clicks and modal submissions
- **Message Threading**: Tests thread creation and replies
- **Channel Management**: Tests channel operations
- **User Management**: Tests user information retrieval
- **File Operations**: Tests file uploads and reactions
- **Rate Limiting**: Tests API rate limit handling

### 3. Aggression Tests (`test_aggression.py`)
- **High Volume Testing**: Tests bot under high message load
- **Malformed Inputs**: Tests bot with invalid/corrupted data
- **Concurrent Requests**: Tests bot with multiple simultaneous requests
- **Rate Limiting Scenarios**: Tests bot under rapid-fire conditions
- **Error Conditions**: Tests bot behavior during various failures
- **Memory Usage**: Tests memory consumption under load

## 🔧 Test Configuration

### Pytest Configuration (`pytest.ini`)
- **Coverage Reporting**: HTML, JSON, and terminal coverage reports
- **Test Markers**: Organized test categorization
- **Output Formats**: JUnit XML and HTML test reports
- **Warning Filters**: Suppresses deprecation warnings

### Test Fixtures (`conftest.py`)
- **Mock Slack Client**: Simulates Slack API responses
- **Mock Coda Service**: Simulates Coda API responses
- **Sample Data**: Provides test user and channel data
- **Environment Setup**: Configures test environment

## 📊 Coverage and Reports

### Coverage Reports
- **HTML Coverage**: `htmlcov/index.html` - Visual coverage report
- **JSON Coverage**: `coverage.json` - Machine-readable coverage data
- **Terminal Output**: Shows missing lines in terminal

### Test Reports
- **HTML Report**: `test-report.html` - Comprehensive test results
- **JUnit XML**: `test-results.xml` - CI/CD integration format
- **Console Output**: Detailed test execution information

## 🚨 Aggression Testing Details

### What is Aggression Testing?
Aggression testing pushes the bot to its limits to ensure it remains stable and performant under extreme conditions.

### Test Scenarios
1. **High Volume**: 100+ messages in rapid succession
2. **Malformed Data**: Invalid payloads, empty fields, extreme lengths
3. **Concurrency**: Multiple threads making simultaneous requests
4. **Rate Limiting**: Rapid-fire API calls to test throttling
5. **Error Conditions**: Network failures, API errors, memory issues
6. **Memory Usage**: Long-running operations to detect leaks

### Performance Metrics
- **Throughput**: Messages per second
- **Response Time**: Average response latency
- **Memory Usage**: Memory consumption per operation
- **Error Rate**: Percentage of failed operations
- **Recovery Time**: Time to recover from errors

## 🛠️ Running Tests Manually

### Using Pytest Directly
```bash
# Run specific test file
pytest tests/test_bot_core.py -v

# Run specific test function
pytest tests/test_aggression.py::test_high_volume_messages -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run in parallel
pytest tests/ -n auto
```

### Using Coverage
```bash
# Generate coverage report
coverage run -m pytest tests/
coverage report
coverage html
```

## 🔍 Debugging Tests

### Verbose Output
```bash
pytest tests/ -v -s --tb=long
```

### Debug Specific Test
```bash
pytest tests/test_bot_core.py::TestBotCore::test_send_dm -v -s --pdb
```

### Generate Test Report
```bash
python run_tests.py --report
```

## 📝 Adding New Tests

### Test Naming Convention
- **Files**: `test_<module_name>.py`
- **Classes**: `Test<ClassName>`
- **Functions**: `test_<function_name>`

### Test Structure
```python
def test_functionality():
    """Test description."""
    # Arrange - Setup test data
    test_data = "test"
    
    # Act - Execute function
    result = function_under_test(test_data)
    
    # Assert - Verify results
    assert result == "expected"
```

### Adding Fixtures
```python
@pytest.fixture
def new_fixture():
    """Description of fixture."""
    return fixture_data
```

## 🚀 CI/CD Integration

### GitHub Actions
The test framework is designed to work with GitHub Actions for automated testing.

### Test Results
- **Coverage**: Minimum 80% coverage required
- **All Tests**: Must pass before deployment
- **Security**: No high-severity vulnerabilities
- **Performance**: Memory usage within acceptable limits

## 📚 Additional Resources

- **Pytest Documentation**: https://docs.pytest.org/
- **Coverage.py**: https://coverage.readthedocs.io/
- **Mock Library**: https://docs.python.org/3/library/unittest.mock.html
- **Slack API Testing**: https://api.slack.com/docs/testing

## 🤝 Contributing

When adding new features, please:
1. Add corresponding unit tests
2. Add integration tests if applicable
3. Add aggression tests for performance-critical features
4. Ensure test coverage remains above 80%
5. Update this README if adding new test categories 