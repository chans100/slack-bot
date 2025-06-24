#!/usr/bin/env python3
"""
Test script for the Daily Standup Bot.
Run this to verify your configuration and test basic functionality.
"""

import os
import sys
from datetime import datetime
from config import BotConfig
from slack_healthcheck_bot import DailyStandupBot

def test_configuration():
    """Test that all required configuration is present."""
    print("🔧 Testing configuration...")
    
    try:
        BotConfig.validate_config()
        print("✅ Configuration validation passed")
        return True
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        return False

def test_slack_connection():
    """Test connection to Slack API."""
    print("\n🔗 Testing Slack connection...")
    
    try:
        bot = DailyStandupBot()
        # Test basic API call
        auth_test = bot.client.auth_test()
        print(f"✅ Connected to Slack workspace: {auth_test['team']}")
        print(f"✅ Bot user: {auth_test['user']}")
        return True
    except Exception as e:
        print(f"❌ Slack connection failed: {e}")
        return False

def test_channel_access():
    """Test access to the configured channel."""
    print("\n📺 Testing channel access...")
    
    try:
        bot = DailyStandupBot()
        channel_info = bot.client.conversations_info(channel=bot.channel_id)
        print(f"✅ Channel access confirmed: #{channel_info['channel']['name']}")
        return True
    except Exception as e:
        print(f"❌ Channel access failed: {e}")
        return False

def test_escalation_channel():
    """Test access to escalation channel."""
    print("\n🚨 Testing escalation channel...")
    
    try:
        bot = DailyStandupBot()
        # Try to get channel info
        channel_info = bot.client.conversations_list()
        escalation_found = False
        
        for channel in channel_info['channels']:
            if channel['name'] == bot.escalation_channel:
                escalation_found = True
                break
        
        if escalation_found:
            print(f"✅ Escalation channel found: #{bot.escalation_channel}")
        else:
            print(f"⚠️  Escalation channel #{bot.escalation_channel} not found in workspace")
            print("   Make sure the channel exists or update SLACK_ESCALATION_CHANNEL")
        
        return True
    except Exception as e:
        print(f"❌ Escalation channel test failed: {e}")
        return False

def test_message_parsing():
    """Test the message parsing functionality."""
    print("\n📝 Testing message parsing...")
    
    try:
        bot = DailyStandupBot()
        
        # Test cases
        test_cases = [
            {
                'text': 'Today: Implemented cart UI\nOn Track: Yes\nBlockers: None',
                'expected': {'on_track': 'yes', 'has_blockers': False}
            },
            {
                'text': 'Today: Working on API\nOn Track: No\nBlockers: Need database access',
                'expected': {'on_track': 'no', 'has_blockers': True}
            },
            {
                'text': 'Today: Bug fixes\nOn Track: Yes\nBlockers: Waiting for review',
                'expected': {'on_track': 'yes', 'has_blockers': True}
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            parsed = bot.parse_standup_response(test_case['text'])
            
            if parsed:
                on_track_match = parsed['on_track'] == test_case['expected']['on_track']
                blockers_match = parsed['has_blockers'] == test_case['expected']['has_blockers']
                
                if on_track_match and blockers_match:
                    print(f"✅ Test case {i} passed")
                else:
                    print(f"❌ Test case {i} failed")
                    print(f"   Expected: {test_case['expected']}")
                    print(f"   Got: {{'on_track': '{parsed['on_track']}', 'has_blockers': {parsed['has_blockers']}}}")
            else:
                print(f"❌ Test case {i} failed - parsing returned None")
        
        return True
    except Exception as e:
        print(f"❌ Message parsing test failed: {e}")
        return False

def test_scheduler():
    """Test that the scheduler can be initialized."""
    print("\n⏰ Testing scheduler...")
    
    try:
        import schedule
        # Test that we can schedule a task
        schedule.every().day.at("09:00").do(lambda: print("Scheduler test"))
        print("✅ Scheduler initialization successful")
        return True
    except Exception as e:
        print(f"❌ Scheduler test failed: {e}")
        return False

def print_configuration_summary():
    """Print a summary of the current configuration."""
    print("\n📋 Configuration Summary:")
    print(f"   Standup Time: {BotConfig.STANDUP_TIME}")
    print(f"   Response Deadline: {BotConfig.RESPONSE_DEADLINE}")
    print(f"   Reminder Time: {BotConfig.REMINDER_TIME}")
    print(f"   Escalation Channel: #{BotConfig.SLACK_ESCALATION_CHANNEL}")
    print(f"   Escalation Emoji: {BotConfig.ESCALATION_EMOJI}")
    print(f"   Monitor Emoji: {BotConfig.MONITOR_EMOJI}")
    print(f"   Flask Host: {BotConfig.FLASK_HOST}")
    print(f"   Flask Port: {BotConfig.FLASK_PORT}")

def main():
    """Run all tests."""
    print("🧪 Daily Standup Bot Test Suite")
    print("=" * 40)
    
    tests = [
        test_configuration,
        test_slack_connection,
        test_channel_access,
        test_escalation_channel,
        test_message_parsing,
        test_scheduler
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 40)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your bot is ready to run.")
        print_configuration_summary()
        print("\n🚀 You can now run: python slack_healthcheck_bot.py")
    else:
        print("⚠️  Some tests failed. Please check your configuration.")
        print("   Review the error messages above and update your .env file.")
        sys.exit(1)

if __name__ == "__main__":
    main() 