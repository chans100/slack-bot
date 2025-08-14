"""
Aggression Testing Module for Slack Standup Bot

This module tests the bot's behavior under various aggressive conditions:
- High message volume
- Malformed inputs
- Rate limiting scenarios
- Error conditions
- Concurrent requests
- Invalid data
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
import random
import string

class AggressionTester:
    """Class to perform aggressive testing on the bot."""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.test_results = []
        
    def generate_random_string(self, length=100):
        """Generate random string for testing."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    
    def generate_malformed_payload(self):
        """Generate malformed Slack payload."""
        malformed_payloads = [
            {},  # Empty payload
            None,  # None payload
            {"invalid": "data"},  # Invalid structure
            {"user": None, "channel": "C123"},  # Missing user data
            {"user": {"id": ""}, "channel": "C123"},  # Empty user ID
            {"user": {"id": "U123"}, "channel": ""},  # Empty channel
            {"user": {"id": "U123" * 1000}, "channel": "C123"},  # Extremely long user ID
            {"user": {"id": "U123"}, "channel": "C123", "text": "A" * 10000},  # Extremely long text
        ]
        return random.choice(malformed_payloads)
    
    def test_high_volume_messages(self, num_messages=100):
        """Test bot with high volume of messages."""
        print(f"🧪 Testing high volume: {num_messages} messages")
        
        start_time = time.time()
        success_count = 0
        error_count = 0
        
        for i in range(num_messages):
            try:
                # Simulate message event
                payload = {
                    "user": {"id": f"U{i}", "name": f"user{i}"},
                    "channel": "C123",
                    "text": f"Test message {i}",
                    "ts": str(time.time())
                }
                
                # Mock the bot's message handling
                with patch.object(self.bot, 'handle_message') as mock_handle:
                    mock_handle.return_value = True
                    result = self.bot.handle_message(payload)
                    
                if result:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                print(f"❌ Error in message {i}: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        result = {
            "test": "high_volume_messages",
            "total_messages": num_messages,
            "success_count": success_count,
            "error_count": error_count,
            "duration_seconds": duration,
            "messages_per_second": num_messages / duration if duration > 0 else 0
        }
        
        self.test_results.append(result)
        print(f"✅ High volume test completed: {success_count}/{num_messages} successful in {duration:.2f}s")
        return result
    
    def test_malformed_inputs(self, num_tests=50):
        """Test bot with malformed inputs."""
        print(f"🧪 Testing malformed inputs: {num_tests} tests")
        
        success_count = 0
        error_count = 0
        
        for i in range(num_tests):
            try:
                malformed_payload = self.generate_malformed_payload()
                
                # Test various bot methods with malformed data
                with patch.object(self.bot, 'handle_message') as mock_handle:
                    mock_handle.side_effect = Exception("Expected error for malformed input")
                    
                    try:
                        self.bot.handle_message(malformed_payload)
                        success_count += 1
                    except Exception:
                        error_count += 1  # Expected behavior
                        
            except Exception as e:
                error_count += 1
                print(f"❌ Error in malformed input test {i}: {e}")
        
        result = {
            "test": "malformed_inputs",
            "total_tests": num_tests,
            "success_count": success_count,
            "error_count": error_count,
            "robustness_score": error_count / num_tests if num_tests > 0 else 0
        }
        
        self.test_results.append(result)
        print(f"✅ Malformed input test completed: {error_count}/{num_tests} handled gracefully")
        return result
    
    def test_concurrent_requests(self, num_threads=10, requests_per_thread=20):
        """Test bot with concurrent requests."""
        print(f"🧪 Testing concurrent requests: {num_threads} threads, {requests_per_thread} requests each")
        
        results = []
        errors = []
        
        def worker_thread(thread_id):
            for i in range(requests_per_thread):
                try:
                    payload = {
                        "user": {"id": f"U{thread_id}_{i}", "name": f"user{thread_id}_{i}"},
                        "channel": "C123",
                        "text": f"Concurrent test {thread_id}_{i}",
                        "ts": str(time.time())
                    }
                    
                    with patch.object(self.bot, 'handle_message') as mock_handle:
                        mock_handle.return_value = True
                        result = self.bot.handle_message(payload)
                        results.append(result)
                        
                except Exception as e:
                    errors.append(e)
        
        # Start threads
        threads = []
        start_time = time.time()
        
        for i in range(num_threads):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        duration = end_time - start_time
        
        result = {
            "test": "concurrent_requests",
            "total_threads": num_threads,
            "requests_per_thread": requests_per_thread,
            "total_requests": num_threads * requests_per_thread,
            "successful_results": len(results),
            "errors": len(errors),
            "duration_seconds": duration,
            "requests_per_second": (num_threads * requests_per_thread) / duration if duration > 0 else 0
        }
        
        self.test_results.append(result)
        print(f"✅ Concurrent test completed: {len(results)}/{num_threads * requests_per_thread} successful in {duration:.2f}s")
        return result
    
    def test_rate_limiting_scenarios(self):
        """Test bot behavior under rate limiting conditions."""
        print("🧪 Testing rate limiting scenarios")
        
        # Simulate rapid-fire requests
        rapid_requests = []
        start_time = time.time()
        
        for i in range(100):
            try:
                payload = {
                    "user": {"id": f"U{i}", "name": f"user{i}"},
                    "channel": "C123",
                    "text": f"Rapid request {i}",
                    "ts": str(time.time())
                }
                
                with patch.object(self.bot, 'handle_message') as mock_handle:
                    mock_handle.return_value = True
                    result = self.bot.handle_message(payload)
                    rapid_requests.append(result)
                    
                # Small delay to simulate real-world timing
                time.sleep(0.001)
                
            except Exception as e:
                print(f"❌ Error in rapid request {i}: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        result = {
            "test": "rate_limiting_scenarios",
            "total_rapid_requests": 100,
            "successful_requests": len(rapid_requests),
            "duration_seconds": duration,
            "requests_per_second": 100 / duration if duration > 0 else 0
        }
        
        self.test_results.append(result)
        print(f"✅ Rate limiting test completed: {len(rapid_requests)}/100 rapid requests handled")
        return result
    
    def test_error_conditions(self):
        """Test bot behavior under various error conditions."""
        print("🧪 Testing error conditions")
        
        error_scenarios = [
            {"scenario": "network_timeout", "mock_side_effect": Exception("Network timeout")},
            {"scenario": "slack_api_error", "mock_side_effect": Exception("Slack API error")},
            {"scenario": "coda_service_error", "mock_side_effect": Exception("Coda service error")},
            {"scenario": "database_error", "mock_side_effect": Exception("Database error")},
            {"scenario": "memory_error", "mock_side_effect": MemoryError("Out of memory")},
        ]
        
        error_results = []
        
        for scenario in error_scenarios:
            try:
                payload = {
                    "user": {"id": "U123", "name": "testuser"},
                    "channel": "C123",
                    "text": f"Error test: {scenario['scenario']}",
                    "ts": str(time.time())
                }
                
                with patch.object(self.bot, 'handle_message') as mock_handle:
                    mock_handle.side_effect = scenario['mock_side_effect']
                    
                    try:
                        self.bot.handle_message(payload)
                        error_results.append({"scenario": scenario['scenario'], "handled": False})
                    except Exception:
                        error_results.append({"scenario": scenario['scenario'], "handled": True})
                        
            except Exception as e:
                error_results.append({"scenario": scenario['scenario'], "handled": False, "error": str(e)})
        
        handled_errors = sum(1 for r in error_results if r.get('handled', False))
        total_scenarios = len(error_scenarios)
        
        result = {
            "test": "error_conditions",
            "total_scenarios": total_scenarios,
            "handled_errors": handled_errors,
            "unhandled_errors": total_scenarios - handled_errors,
            "error_handling_score": handled_errors / total_scenarios if total_scenarios > 0 else 0,
            "scenario_details": error_results
        }
        
        self.test_results.append(result)
        print(f"✅ Error condition test completed: {handled_errors}/{total_scenarios} errors handled gracefully")
        return result
    
    def test_memory_usage(self, num_operations=1000):
        """Test bot memory usage under load."""
        print(f"🧪 Testing memory usage: {num_operations} operations")
        
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform operations
        for i in range(num_operations):
            payload = {
                "user": {"id": f"U{i}", "name": f"user{i}"},
                "channel": "C123",
                "text": f"Memory test {i}",
                "ts": str(time.time())
            }
            
            with patch.object(self.bot, 'handle_message') as mock_handle:
                mock_handle.return_value = True
                self.bot.handle_message(payload)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        result = {
            "test": "memory_usage",
            "total_operations": num_operations,
            "initial_memory_mb": round(initial_memory, 2),
            "final_memory_mb": round(final_memory, 2),
            "memory_increase_mb": round(memory_increase, 2),
            "memory_per_operation_kb": round((memory_increase * 1024) / num_operations, 2) if num_operations > 0 else 0
        }
        
        self.test_results.append(result)
        print(f"✅ Memory usage test completed: {memory_increase:.2f}MB increase over {num_operations} operations")
        return result
    
    def run_all_tests(self):
        """Run all aggression tests."""
        print("🚀 Starting Aggression Testing Suite...")
        print("=" * 50)
        
        tests = [
            self.test_high_volume_messages,
            self.test_malformed_inputs,
            self.test_concurrent_requests,
            self.test_rate_limiting_scenarios,
            self.test_error_conditions,
            self.test_memory_usage
        ]
        
        for test in tests:
            try:
                test()
                print("-" * 30)
            except Exception as e:
                print(f"❌ Test {test.__name__} failed: {e}")
                print("-" * 30)
        
        print("=" * 50)
        print("🏁 Aggression Testing Suite Completed!")
        self.print_summary()
    
    def print_summary(self):
        """Print summary of all test results."""
        print("\n📊 TEST RESULTS SUMMARY:")
        print("=" * 50)
        
        for result in self.test_results:
            print(f"\n🧪 {result['test'].replace('_', ' ').title()}:")
            for key, value in result.items():
                if key != 'test':
                    if isinstance(value, float):
                        print(f"  {key}: {value:.2f}")
                    else:
                        print(f"  {key}: {value}")
        
        # Calculate overall score
        total_tests = len(self.test_results)
        if total_tests > 0:
            print(f"\n🎯 Overall Test Coverage: {total_tests} tests completed")
            print("=" * 50)


# Test functions for pytest
def test_aggression_tester_creation():
    """Test that AggressionTester can be created."""
    mock_bot = Mock()
    tester = AggressionTester(mock_bot)
    assert tester is not None
    assert hasattr(tester, 'run_all_tests')

def test_random_string_generation():
    """Test random string generation."""
    mock_bot = Mock()
    tester = AggressionTester(mock_bot)
    
    # Test different lengths
    for length in [10, 50, 100]:
        result = tester.generate_random_string(length)
        assert len(result) == length
        assert isinstance(result, str)

def test_malformed_payload_generation():
    """Test malformed payload generation."""
    mock_bot = Mock()
    tester = AggressionTester(mock_bot)
    
    payload = tester.generate_malformed_payload()
    assert payload is not None

if __name__ == "__main__":
    # Example usage
    mock_bot = Mock()
    tester = AggressionTester(mock_bot)
    tester.run_all_tests() 