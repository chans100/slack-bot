import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv('token.env')  # Explicitly load from .env file
import time
import schedule
import re
import json
from datetime import datetime, timezone, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from flask import Flask, request, jsonify
from src.config import BotConfig
from .coda_service import CodaService
import requests
# Use a simple approach that works without additional packages
# EST is UTC-5, EDT is UTC-4 (during daylight saving)
def get_est_time():
    utc_now = datetime.now(timezone.utc)
    # Simple EST calculation (UTC-5)
    est_offset = timedelta(hours=5)
    est_time = utc_now - est_offset
    return est_time

# Initialize Flask app
app = Flask(__name__)

class DailyStandupBot:
    """
    A comprehensive Slack bot for daily standup management with hybrid interaction workflows.
    
    Features:
    - Daily standup prompts at 9:00 AM
    - Hybrid interaction: reactions + thread replies
    - Automated response parsing and follow-up
    - Blocker detection and escalation
    - Configurable workflow settings
    """
    
    def __init__(self):
        # Load configuration
        self.config = BotConfig()
        
        # Initialize Slack client
        self.client = WebClient(token=self.config.SLACK_BOT_TOKEN)
        self.channel_id = self.config.SLACK_CHANNEL_ID
        
        # Initialize Coda service
        self.coda = None
        try:
            from .coda_service import CodaService
            self.coda = CodaService()
            print("✅ Coda service initialized")
        except Exception as e:
            print(f"⚠️ Could not initialize Coda service: {e}")
        
        # Initialize Mistral service
        self.mistral = None
        try:
            from mistral_service import MistralService
            self.mistral = MistralService()
            print("✅ Mistral service initialized")
        except Exception as e:
            print(f"⚠️ Could not initialize Mistral service: {e}")
        
        # Track responses to prevent duplicates
        self.health_check_responses = set()
        self.processed_events = set()
        
        # Initialize tracked blockers for follow-up
        self.tracked_blockers = {}
        
        # Initialize follow-up tracking to prevent duplicates
        self.last_followup_sent = {}
        
        # User roles mapping - can be loaded from Coda or config
        self.user_roles = {
            # Format: 'user_id': ['role1', 'role2']
            # Example roles: 'pm', 'lead', 'developer', 'designer', 'qa', 'devops', 'sm'
            'U0919MVQLLU': ['developer', 'lead', 'admin'],  # alexanderchan486
            'U0912DJRNSF': ['pm', 'admin'],  # bot admin
            # Add more users as needed
        }
        
        # Role-based channel mappings
        self.role_channels = {
            'pm': 'general',  # PMs get notified in general channel
            'lead': 'general',  # Leads get notified in general channel
            'developer': 'dev-team',  # Developers get notified in dev-team channel
            'designer': 'design-team',  # Designers get notified in design-team channel
            'qa': 'qa-team',  # QA gets notified in qa-team channel
            'devops': 'devops-team',  # DevOps gets notified in devops-team channel
            'sm': 'general',  # Scrum Masters get notified in general channel
            'admin': 'general'  # Admins get notified in general channel
        }
        
        # Role-based escalation hierarchy
        self.escalation_hierarchy = {
            'blocker': ['developer', 'lead', 'sm', 'pm'],  # Escalate blockers to dev -> lead -> sm -> pm
            'health_check': ['pm', 'admin'],  # Escalate health issues to pm -> admin
            'standup': ['pm', 'lead'],  # Escalate standup issues to pm -> lead
            'kr_issue': ['lead', 'pm']  # Escalate KR issues to lead -> pm
        }
        
        # Initialize tracking dictionaries
        self.active_standups = {}
        self.user_responses = {}
        
        # Track active standups and user responses
        self.standup_responses = set()  # Track users who have submitted standup responses today
        
        # Track help offers to prevent duplicates
        self.help_offers = set()  # Track help offers by message_ts
        
        # Track KR name mappings for sanitized button values
        self.kr_name_mappings = {}  # Map sanitized names to original names
        
        # Track daily prompts to ensure they only send once
        self.daily_prompts_sent = {
            'standup': False,
            'health_check': False
        }
        
        # Schedule daily standup and health checks
        schedule.every().day.at("00:00").do(self.reset_daily_prompts)  # Reset at midnight
        schedule.every().day.at(self.config.STANDUP_TIME).do(self.send_standup_to_all_users)
        schedule.every().day.at(self.config.REMINDER_TIME).do(self.check_missing_responses)
        # Schedule daily health check to all users via DM
        schedule.every().day.at("09:00").do(self.send_health_check_to_all_users)
        # Schedule daily blocker digest at 15:30
        # schedule.every().day.at("15:30").do(self.send_daily_blocker_digest)  # In production, send at 3:30 PM
        # For development, send digest at startup instead:
        self.send_daily_blocker_digest()
        self.send_daily_standup_digest()
        
        self._user_list_cache = None
        self._user_list_cache_time = 0

        # Add this at the top of the file or in the class __init__
        self.BLOCKER_FOLLOWUP_DELAY_HOURS = 24  # Change this value to adjust the follow-up delay
        
    def send_daily_standup(self):
        """Send the daily standup prompt message with hybrid interaction options."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "�� *Good morning team! Time for the daily standup!*\n\n"
                                   "You have two ways to respond:\n\n"
                                   "**Option 1: Quick Status (Reactions)**\n"
                                   "React to this message with:\n"
                                   "• ✅ = All good, on track\n"
                                   "• ⚠️ = Minor issues, but manageable\n"
                                   "• 🚨 = Need help/blocked\n\n"
                                   "**Option 2: Detailed Response (Thread Reply)**\n"
                                   "Reply in this thread with:\n"
                                   "• Today: [what you did]\n"
                                   "• On Track: Yes/No\n"
                                   "• Do you have any blockers? (Yes/No)\n\n"
                                   f"<!channel> please respond by {self.config.RESPONSE_DEADLINE}. Let's stay aligned! 💬"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "💡 *Tip: Use reactions for quick status, thread replies for detailed updates*"
                            }
                        ]
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                blocks=message["blocks"],
                text="Daily Standup - React for quick status or reply in thread for details"
            )
            
            # Track this standup
            self.active_standups[response['ts']] = {
                'timestamp': datetime.now(),
                'responses': {},
                'quick_responses': {}
            }
            
            print(f"Daily standup sent successfully: {response['ts']}")
            return response['ts']
            
        except SlackApiError as e:
            print(f"Error sending daily standup: {e.response['error']}")
            return None
    
    def handle_quick_reaction(self, user_id, standup_ts, reaction):
        """Handle quick status reactions to the main standup message."""
        try:
            # Check if user has already submitted a standup response today
            today = datetime.now().strftime('%Y-%m-%d')
            standup_key = f"{user_id}_{today}"
            if standup_key in self.standup_responses:
                print(f"⚠️ User {user_id} has already submitted a standup response today (quick reaction)")
                # Send a polite message informing them they've already responded
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=standup_ts,
                    text=f"<@{user_id}>, you've already submitted your standup response for today! Thanks for staying on top of it! ✅"
                )
                return
            
            # Get user info
            user_info = self.client.users_info(user=user_id)
            user_name = user_info['user']['real_name']
            
            # Map reactions to status
            status_map = {
                'white_check_mark': {'status': 'on_track', 'message': 'All good! ✅'},
                'warning': {'status': 'minor_issues', 'message': 'Minor issues noted ⚠️'},
                'rotating_light': {'status': 'needs_help', 'message': 'Help needed! 🚨'}
            }
            
            if reaction not in status_map:
                return
            
            status_info = status_map[reaction]
            
            # Store quick response
            if standup_ts not in self.active_standups:
                self.active_standups[standup_ts] = {'responses': {}, 'quick_responses': {}}
            
            self.active_standups[standup_ts]['quick_responses'][user_id] = {
                'status': status_info['status'],
                'reaction': reaction,
                'timestamp': datetime.now(),
                'user_name': user_name
            }
            
            # Mark user as having submitted standup response today
            self.standup_responses.add(standup_key)
            print(f"✅ User {user_id} marked as having submitted standup response for {today} (quick reaction)")
            
            # Respond based on status
            if status_info['status'] == 'needs_help':
                # Send detailed follow-up for help requests
                self.send_help_followup(user_id, standup_ts, user_name)
            else:
                # Acknowledge quick status
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=standup_ts,
                    text=f"<@{user_id}>: {status_info['message']}"
                )
                
        except SlackApiError as e:
            print(f"Error handling quick reaction: {e.response['error']}")
    
    def send_mentor_check(self, user_id, standup_ts, user_name, request_type, channel, search_term=None):
        """Send a mentor check prompt to the user. If search_term is provided, store it for use after mentor check."""
        try:
            # Store the search term in a temporary dict for the user (for follow-up after mentor check)
            if not hasattr(self, 'pending_kr_search'):
                self.pending_kr_search = {}
            if request_type == "kr":
                self.pending_kr_search[user_id] = search_term if search_term else None
            # Send the mentor check prompt
            self.client.chat_postMessage(
                channel=channel,
                text=(
                    f"@{user_name}, before we proceed with your KR request, I need to ask:\n"
                    ":thinking_face: Have you reached out to your mentor yet?"
                ),
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"@{user_name}, before we proceed with your KR request, I need to ask:\n:thinking_face: Have you reached out to your mentor yet?"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Yes"},
                                "value": f"mentor_yes_{request_type}_{user_id}",
                                "action_id": "mentor_yes"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "No"},
                                "value": f"mentor_no_{request_type}_{user_id}",
                                "action_id": "mentor_no"
                            }
                        ]
                    }
                ]
            )
        except Exception as e:
            print(f"❌ Error sending mentor check: {e}")
    
    def send_help_followup(self, user_id, standup_ts, user_name, channel=None):
        """Send enhanced blocker follow-up with structured questions."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"<@{user_id}>, I see you need help! 🚨\n\n"
                                   "Let me help you get unblocked. Please provide the following information:"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "blocker_description",
                        "label": {
                            "type": "plain_text",
                            "text": "What's blocking you?"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "blocker_description_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Describe the blocker in detail..."
                            },
                            "multiline": True
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "kr_name",
                        "label": {
                            "type": "plain_text",
                            "text": "Key Result (KR) Name"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "kr_name_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "e.g., KR1: Increase user engagement"
                            }
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "urgency",
                        "label": {
                            "type": "plain_text",
                            "text": "Urgency Level"
                        },
                        "element": {
                            "type": "static_select",
                            "action_id": "urgency_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Select urgency level"
                            },
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Low - Can wait a few days"
                                    },
                                    "value": "Low"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Medium - Need help this week"
                                    },
                                    "value": "Medium"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "High - Blocking progress now"
                                    },
                                    "value": "High"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Critical - Blocking team/delivery"
                                    },
                                    "value": "Critical"
                                }
                            ]
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "notes",
                        "label": {
                            "type": "plain_text",
                            "text": "Additional Notes (Optional)"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "notes_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Any additional context or details..."
                            },
                            "multiline": True
                        },
                        "optional": True
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Submit Blocker Details",
                                    "emoji": True
                                },
                                "value": "submit_blocker",
                                "action_id": "submit_blocker_details",
                                "style": "primary"
                            }
                        ]
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=channel or self.channel_id,
                thread_ts=standup_ts,
                blocks=message["blocks"],
                text=f"<@{user_id}>, I see you need help! Please fill out the blocker details above."
            )
            
            print(f"Enhanced blocker follow-up sent to {user_name} ({user_id})")
            return response['ts']
            
        except SlackApiError as e:
            print(f"Error sending enhanced blocker follow-up: {e.response['error']}")
            return None
    
    def parse_standup_response(self, text):
        """Parse standup response text: 1st line = today, 2nd = on_track, 3rd = blockers."""
        lines = [l.strip().lower() for l in text.strip().split('\n') if l.strip()]
        parsed = {
            'today': lines[0] if len(lines) > 0 else '',
            'on_track': lines[1] if len(lines) > 1 else '',
            'blockers': lines[2] if len(lines) > 2 else ''
        }
        return parsed

    def handle_standup_response(self, user_id, message_ts, thread_ts, text, channel_id=None):
        """Handle standup response in thread."""
        try:
            print(f"🔍 DEBUG: Processing standup response from user {user_id}")
            print(f"🔍 DEBUG: Message text: {text[:100]}...")
            print(f"🔍 DEBUG: Channel ID: {channel_id}")
            
            # Check if this specific message has already been processed
            if message_ts in self.processed_events:
                print(f"⚠️ Message {message_ts} already processed, skipping")
                return
            
            # Check if user has already submitted a standup response today
            today = datetime.now().strftime('%Y-%m-%d')
            standup_key = f"{user_id}_{today}"
            if standup_key in self.standup_responses:
                print(f"⚠️ User {user_id} has already submitted a standup response today")
                # Send a polite message informing them they've already responded
                target_channel = channel_id or self.channel_id
                self.client.chat_postMessage(
                    channel=target_channel,
                    thread_ts=thread_ts,
                    text=f"<@{user_id}>, you've already submitted your standup response for today! Thanks for staying on top of it! ✅"
                )
                return
            
            # Get user info
            user_info = self.client.users_info(user=user_id)
            user_name = user_info['user']['real_name']
            print(f"🔍 DEBUG: User name: {user_name}")
            
            # Parse the response
            parsed_data = self.parse_standup_response(text)
            print(f"🔍 DEBUG: Parsed data: {parsed_data}")
            
            # Generate AI-powered analysis of the standup response
            ai_analysis = ""
            try:
                from mistral_service import MistralService
                mistral = MistralService()
                analysis_result = mistral.analyze_standup_response(text)
                if analysis_result and isinstance(analysis_result, dict):
                    sentiment = analysis_result.get('sentiment', 'neutral')
                    urgency = analysis_result.get('urgency', 'medium')
                    suggestions = analysis_result.get('suggestions', [])
                    key_points = analysis_result.get('key_points', [])
                    
                    # Create AI analysis text
                    sentiment_emoji = {'positive': '😊', 'neutral': '😐', 'negative': '😟'}.get(sentiment, '😐')
                    urgency_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(urgency, '🟡')
                    
                    ai_analysis = f"\n\n🤖 *AI Analysis:*\n• Sentiment: {sentiment_emoji} {sentiment.title()}\n• Urgency: {urgency_emoji} {urgency.title()}"
                    
                    if suggestions:
                        ai_analysis += f"\n• Suggestions: {'; '.join(suggestions[:2])}"
                    
                    if key_points:
                        ai_analysis += f"\n• Key Points: {'; '.join(key_points[:2])}"
                    
                    print(f"🔍 DEBUG: AI Analysis - Sentiment: {sentiment}, Urgency: {urgency}")
            except Exception as ai_error:
                print(f"⚠️ Error generating AI analysis: {ai_error}")
                ai_analysis = ""
            
            # Store response in Coda
            success = False
            
            # Try Coda (standup table)
            if self.coda and self.coda.standup_table_id:
                try:
                    success = self.coda.add_standup_response(
                        user_id=user_id,
                        response_text=text,
                        username=user_name
                    )
                    if success:
                        print("✅ Standup response stored in Coda successfully")
                except Exception as e:
                    print(f"❌ Error storing response in Coda: {e}")
            else:
                print("⚠️ Standup table ID not configured - skipping Coda storage")
            
            if not success:
                print("❌ Failed to store response in Coda")
                # Don't fail the request - just log the issue
                success = True  # Mark as success to continue processing
            
            # Mark this message as processed
            self.processed_events.add(message_ts)
            
            # Mark user as having submitted standup response today
            today = datetime.now().strftime('%Y-%m-%d')
            standup_key = f"{user_id}_{today}"
            self.standup_responses.add(standup_key)
            print(f"✅ User {user_id} marked as having submitted standup response for {today}")
            print("✅ Message marked as processed")
            
            # Check if user needs follow-up with more flexible parsing
            on_track_text = parsed_data.get('on_track', '').lower()
            blockers_text = parsed_data.get('blockers', '').lower()
            
            # More comprehensive detection for not being on track
            not_on_track_phrases = [
                'no', 'not on track', 'not on', 'behind', 'off track', 'off', 
                'not track', 'not meeting', 'not going well', 'struggling',
                'falling behind', 'behind schedule', 'delayed', 'late'
            ]
            not_on_track = any(phrase in on_track_text for phrase in not_on_track_phrases)
            
            # More comprehensive detection for blockers
            blocker_phrases = [
                'yes', 'blocker', 'blocked', 'stuck', 'issue', 'problem', 'yes i have',
                'have blocker', 'need help', 'help', 'trouble', 'difficulty',
                'challenge', 'obstacle', 'impediment', 'barrier'
            ]
            has_blockers = any(phrase in blockers_text for phrase in blocker_phrases)
            
            needs_followup = not_on_track or has_blockers
            
            print(f"🔍 DEBUG: on_track_text: '{on_track_text}', blockers_text: '{blockers_text}'")
            print(f"🔍 DEBUG: not_on_track: {not_on_track}, has_blockers: {has_blockers}")
            
            print(f"🔍 DEBUG: Needs followup: {needs_followup}")
            
            if needs_followup:
                # Check if we've already sent a followup to this user in this thread
                followup_key = f"followup_{user_id}_{thread_ts}"
                if followup_key not in self.health_check_responses:
                    print(f"🔍 DEBUG: Sending followup message to {user_name}")
                    self.send_followup_message(user_id, thread_ts, parsed_data, channel_id, ai_analysis)
                else:
                    print(f"⚠️ Followup already sent to {user_id} in thread {thread_ts}")
            else:
                print(f"🔍 DEBUG: No followup needed for {user_name}")
                # Send acknowledgment to the correct channel with AI analysis
                target_channel = channel_id or self.channel_id
                acknowledgment_text = f"Thanks <@{user_id}> for your standup update! ✅{ai_analysis}"
                self.client.chat_postMessage(
                    channel=target_channel,
                    thread_ts=thread_ts,
                    text=acknowledgment_text
                )
                
        except SlackApiError as e:
            print(f"Error handling standup response: {e.response['error']}")
        except Exception as e:
            print(f"Unexpected error in handle_standup_response: {e}")
            import traceback
            traceback.print_exc()

    def send_followup_message(self, user_id, thread_ts, parsed_data, channel_id=None, ai_analysis=""):
        """Send follow-up message for users who need help."""
        try:
            # Check if we've already sent a followup to this user in this thread
            followup_key = f"followup_{user_id}_{thread_ts}"
            if followup_key in self.health_check_responses:
                print(f"⚠️ Already sent followup to {user_id} in thread {thread_ts}")
                return
            
            # Mark that we've sent a followup
            self.health_check_responses.add(followup_key)
            
            # Determine status for display
            on_track_status = parsed_data.get('on_track', 'None')
            blockers_status = parsed_data.get('blockers', 'None')
            
            # Clean up status display
            if on_track_status.lower() in ['yes', 'true']:
                on_track_display = 'yes ✅'
            elif on_track_status.lower() in ['no', 'false']:
                on_track_display = 'no ❌'
            else:
                on_track_display = 'None'
                
            if blockers_status.lower() in ['yes', 'true']:
                blockers_display = 'yes 🚧'
            elif blockers_status.lower() in ['no', 'false', 'none']:
                blockers_display = 'None ✅'
            else:
                blockers_display = 'None'
            
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"<@{user_id}>, thanks for the detailed update! :handshake: Since you're either not on track or facing a blocker, would you like help?\n\n*Your status:* :bar_chart:\n• On Track: {on_track_display}\n• Blockers: {blockers_display}{ai_analysis}\n\nReact with one of the following:\n• :sos: = Need help now\n• :clock4: = Can wait / just keeping team informed"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":sos: Need help now",
                                    "emoji": True
                                },
                                "value": "escalate",
                                "action_id": "escalate_help"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":clock4: Can wait",
                                    "emoji": True
                                },
                                "value": "monitor",
                                "action_id": "monitor_issue",
                                "style": "primary"
                            }
                        ]
                    }
                ]
            }
            
            # Use the provided channel_id or fall back to the original channel
            target_channel = channel_id or self.channel_id
            
            response = self.client.chat_postMessage(
                channel=target_channel,
                thread_ts=thread_ts,
                blocks=message["blocks"],
                text=f"Follow-up for <@{user_id}> - React for help options"
            )
            
            # Mark followup as sent
            followup_key = f"followup_{user_id}_{thread_ts}"
            self.health_check_responses.add(followup_key)
            print(f"✅ Followup message marked as sent: {response['ts']}")
            
            # Store user data for button handling
            self.user_responses[user_id] = {
                'followup_ts': response['ts'],
                'thread_ts': thread_ts,
                'parsed_data': parsed_data,
                'user_name': self.client.users_info(user=user_id)['user']['real_name']
            }
            
        except SlackApiError as e:
            print(f"Error sending followup message: {e.response['error']}")

    def handle_reaction(self, user_id, message_ts, reaction):
        """Handle reactions to follow-up messages."""
        try:
            # Find the user data for this message
            user_data = None
            for uid, data in self.user_responses.items():
                if data.get('followup_ts') == message_ts:
                    user_data = data
                    break
            
            if not user_data:
                print(f"No user data found for message {message_ts}")
                return
            
            # Handle escalation reactions
            if reaction == 'sos':
                # Send message with button to open blocker form
                message = {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"<@{user_id}>, I see you need help! 🚨\n\n"
                                       "Let me help you get unblocked. Please click the button below to provide details:"
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Report Blocker",
                                        "emoji": True
                                    },
                                    "value": f"open_blocker_form_{user_id}",
                                    "action_id": "escalate_help"
                                }
                            ]
                        }
                    ]
                }
                
                response = self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=user_data['thread_ts'],
                    blocks=message["blocks"],
                    text=f"<@{user_id}>, please click the button to report your blocker details."
                )
                print(f"✅ Blocker form button sent to {user_data['user_name']}")
                
            elif reaction == 'clock4':
                # Acknowledge monitoring
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=user_data['thread_ts'],
                    text=f"Got it <@{user_id}>, we'll keep an eye on this. Please keep your mentor informed of any updates! 🚧"
                )
                # Clean up
                del self.user_responses[user_id]
                
        except SlackApiError as e:
            print(f"Error handling reaction: {e.response['error']}")

    def handle_resolution_modal_submission(self, payload):
        """Handle resolution modal submission."""
        try:
            print("🔍 DEBUG: Received resolution modal submission")
            print(f"🔍 DEBUG: Payload keys: {list(payload.keys())}")
            
            # Extract form data from the payload
            state = payload.get('view', {}).get('state', {})
            values = state.get('values', {})
            
            print(f"🔍 DEBUG: State keys: {list(state.keys())}")
            print(f"🔍 DEBUG: Values keys: {list(values.keys())}")
            
            # Get resolution details from form
            resolution_notes = values.get('resolution_notes', {}).get('resolution_notes_input', {}).get('value', '')
            hidden_data = values.get('hidden_data', {}).get('hidden_data_input', {}).get('value', '')
            
            print(f"🔍 DEBUG: Extracted values:")
            print(f"   Resolution Notes: {resolution_notes}")
            print(f"   Hidden Data: {hidden_data}")
            
            # Parse hidden data
            # Format: "blocker_id" or "dm_user_id_kr_name_description"
            blocker_id = hidden_data.strip()
            if not blocker_id:
                print(f"❌ Invalid hidden data format: {hidden_data}")
                return {"response_action": "clear"}, 200
            
            # Get blocker info from active_blockers, tracked_blockers, or DM format
            blocker_info = None
            blocked_user_id = None
            kr_name = None
            blocker_description = None
            channel_id = None
            message_ts = None
            
            # Check if this is a DM format blocker
            if blocker_id.startswith('dm_'):
                # DM format: "dm_user_id_kr_name_description"
                parts = blocker_id.split('_', 3)
                if len(parts) >= 4:
                    blocked_user_id = parts[1]
                    kr_name = parts[2]
                    blocker_description = parts[3]
                    
                    # Create minimal blocker_info for DM blockers
                    blocker_info = {
                        'user_id': blocked_user_id,
                        'user_name': 'Unknown',  # Will be looked up if needed
                        'kr_name': kr_name,
                        'blocker_description': blocker_description,
                        'urgency': 'Unknown',
                        'notes': '',
                        'source': 'dm_resolution'
                    }
                    print(f"✅ Parsed DM format blocker: {blocker_id}")
                    print(f"   - User ID: {blocked_user_id}")
                    print(f"   - KR Name: {kr_name}")
                    print(f"   - Description: {blocker_description}")
                else:
                    print(f"❌ Invalid DM format: {blocker_id}")
                    return {"response_action": "clear"}, 200
            else:
                # Regular format - try to find in active_blockers
                if hasattr(self, 'active_blockers') and blocker_id in self.active_blockers:
                    blocker_info = self.active_blockers[blocker_id]
                    blocked_user_id = blocker_info['user_id']
                    kr_name = blocker_info['kr_name']
                    blocker_description = blocker_info['blocker_description']
                    channel_id = blocker_info.get('channel_id')
                    message_ts = blocker_info.get('message_ts')
                    print(f"✅ Found blocker in active_blockers: {blocker_id}")
                # If not found in active_blockers, try to find in tracked_blockers
                elif hasattr(self, 'tracked_blockers'):
                    for tracked_id, tracked_info in self.tracked_blockers.items():
                        if tracked_id == blocker_id:
                            blocker_info = tracked_info
                            blocked_user_id = tracked_info['user_id']
                            kr_name = tracked_info['kr_name']
                            blocker_description = tracked_info['blocker_description']
                            channel_id = tracked_info.get('channel_id')
                            message_ts = tracked_info.get('escalation_ts')
                            print(f"✅ Found blocker in tracked_blockers: {blocker_id}")
                            print(f"🔍 DEBUG: Tracked blocker info keys: {list(tracked_info.keys())}")
                            print(f"🔍 DEBUG: Tracked blocker info: {tracked_info}")
                            break
            
            if not blocker_info:
                print(f"❌ Blocker {blocker_id} not found in active_blockers or tracked_blockers")
                print(f"❌ Fallback: Could not find blocker info for deletion or Coda update.")
                return {"response_action": "clear"}, 200
            
            print(f"🔍 DEBUG: Parsed hidden data:")
            print(f"   Blocked User ID: {blocked_user_id}")
            print(f"   KR Name: {kr_name}")
            print(f"   Blocker Description: {blocker_description}")
            
            # Get user info (the person resolving)
            user = payload.get('user', {}).get('id', 'unknown')
            username = payload.get('user', {}).get('name', 'unknown')
            
            print(f"🔍 DEBUG: Resolver: {user} ({username})")
            
            # Log the blocker resolution to Coda (optional - don't fail if Coda is down)
            success = True  # Start with success, only fail if critical errors occur
            if self.coda:
                try:
                    # Log resolution to Blocker Resolution table
                    coda_success = self.coda.resolve_blocker(
                        user_id=blocked_user_id,
                        kr_name=kr_name,
                        blocker_description=blocker_description,
                        resolved_by=username,
                        resolution_notes=resolution_notes,
                        slack_client=self.client,
                        user_name=blocker_info.get('user_name', blocked_user_id)
                    )
                    if coda_success:
                        print(f"✅ Blocker resolution logged in Coda by {username}")
                    else:
                        print("⚠️ Failed to log blocker resolution in Coda, but continuing...")
                        
                except Exception as e:
                    print(f"⚠️ Error logging blocker resolution in Coda: {e}")
                    print("⚠️ Continuing with resolution process...")
                    import traceback
                    traceback.print_exc()
            else:
                print("⚠️ Coda not available, skipping Coda logging")
            
            # Mark as resolved in tracked blockers (if exists)
            if hasattr(self, 'tracked_blockers'):
                for blocker_id, blocker_info in self.tracked_blockers.items():
                    if (blocker_info['user_id'] == blocked_user_id and 
                        blocker_info['kr_name'] == kr_name and
                        blocker_info['blocker_description'] == blocker_description):
                        blocker_info['resolved'] = True
                        blocker_info['resolution_time'] = datetime.now()
                        blocker_info['resolved_by'] = username
                        blocker_info['resolution_notes'] = resolution_notes
                        print(f"✅ Blocker marked as resolved in tracked blockers: {blocker_id}")
                        break
            
            # Mark as resolved in active blockers (new system)
            if hasattr(self, 'active_blockers'):
                resolved_blocker_id = blocker_id
                resolved_blocker_info = None
                if blocker_id in self.active_blockers:
                    # Mark as resolved
                    self.active_blockers[blocker_id]['resolved'] = True
                    self.active_blockers[blocker_id]['resolved_by'] = username
                    self.active_blockers[blocker_id]['resolved_at'] = time.time()
                    self.active_blockers[blocker_id]['resolution_notes'] = resolution_notes
                    resolved_blocker_info = self.active_blockers[blocker_id]
                    print(f"✅ Blocker marked as resolved in active blockers: {blocker_id}")
                else:
                    print(f"❌ Blocker {blocker_id} not found in active blockers")
            
            # Send confirmation messages
            if success:
                # Send confirmation to resolver only (remove duplicate to blocked user)
                try:
                    self.client.chat_postMessage(
                        channel=user,
                        text=f"🎉 Successfully marked blocker as resolved!\n\n**KR:** {kr_name}\n**Description:** {blocker_description}\n**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                    )
                    print(f"✅ Confirmation sent to resolver {username}")
                except Exception as e:
                    print(f"❌ Error sending confirmation to resolver: {e}")
                
                # Delete the blocker message from the channel and update details
                print(f"🔍 DEBUG: Attempting to delete blocker message")
                print(f"🔍 DEBUG: Channel ID: {channel_id}")
                print(f"🔍 DEBUG: Message TS: {message_ts}")
                
                # If we don't have channel_id, try to get it from config and search for the original message
                if not channel_id:
                    # Get accessible channels first
                    accessible_channels = self.get_accessible_channels()
                    if not accessible_channels:
                        print("❌ No accessible channels found for message deletion")
                        accessible_channels = ['general']  # Fallback
                    
                    original_message_deleted = False
                    for channel_name in accessible_channels:
                        print(f"🔍 DEBUG: Trying accessible channel: #{channel_name}")
                        try:
                            # Try to find and delete the original blocker escalation message
                            original_message_deleted = self._find_and_delete_original_blocker_message(
                                channel_name, blocked_user_id, kr_name, blocker_description, username
                            )
                            if original_message_deleted:
                                leads_channel = channel_name
                                print(f"✅ Successfully deleted original message from #{channel_name}")
                                break
                        except Exception as e:
                            print(f"❌ Error trying to delete from #{channel_name}: {e}")
                            continue
                    
                    if original_message_deleted:
                        # Send completion message to leads channel after successful deletion
                        completion_message = f"✅ *Blocker Resolved*\n\n"
                        completion_message += f"**KR:** {kr_name}\n"
                        completion_message += f"**Description:** {blocker_description}\n"
                        completion_message += f"**Resolved by:** {username}\n"
                        completion_message += f"**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                        
                        try:
                            self.client.chat_postMessage(
                                channel=f"#{leads_channel}",
                                text=completion_message
                            )
                            print(f"✅ Sent completion summary to leads channel #{leads_channel}")
                        except Exception as e:
                            print(f"❌ Error sending completion message: {e}")
                    else:
                        print(f"⚠️ Could not find original blocker message to delete")
                        # Try to send completion message to an accessible channel
                        completion_message = f"✅ *Blocker Resolved*\n\n"
                        completion_message += f"**KR:** {kr_name}\n"
                        completion_message += f"**Description:** {blocker_description}\n"
                        completion_message += f"**Resolved by:** {username}\n"
                        completion_message += f"**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                        
                        message_sent = self.send_completion_message_to_accessible_channel(completion_message)
                        
                        if not message_sent:
                            print(f"❌ Could not send completion message to any accessible channel")
                        
                        # Log missing channel/message timestamps for debugging
                        if not channel_id or not message_ts:
                            print(f"❌ Missing channel_id or message_ts for deletion")
                            print(f"❌ channel_id: {channel_id}, message_ts: {message_ts}")
                        
                        return {"response_action": "clear"}, 200
                
                if channel_id and message_ts:
                    try:
                        # Delete the original blocker message
                        self.client.chat_delete(channel=channel_id, ts=message_ts)
                        print(f"✅ Deleted blocker message from channel {channel_id}")
                        
                        # Send a completion summary to the channel
                        completion_message = f"✅ *Blocker Resolved*\n\n"
                        completion_message += f"**KR:** {kr_name}\n"
                        completion_message += f"**Description:** {blocker_description}\n"
                        completion_message += f"**Resolved by:** {username}\n"
                        completion_message += f"**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                        
                        self.client.chat_postMessage(
                            channel=channel_id,
                            text=completion_message
                        )
                        print(f"✅ Sent completion summary to channel {channel_id}")
                        
                    except Exception as e:
                        print(f"❌ Error deleting blocker message or sending completion summary: {e}")
                        import traceback
                        traceback.print_exc()
                        
                        # Fallback: try to update the message instead of deleting it
                        try:
                            completion_message = f"✅ *Blocker Resolved*\n\n"
                            completion_message += f"**KR:** {kr_name}\n"
                            completion_message += f"**Description:** {blocker_description}\n"
                            completion_message += f"**Resolved by:** {username}\n"
                            completion_message += f"**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                            
                            self.client.chat_update(
                                channel=channel_id,
                                ts=message_ts,
                                text=completion_message
                            )
                            print(f"✅ Updated blocker message in channel {channel_id} with resolution")
                        except Exception as update_error:
                            print(f"❌ Error updating blocker message: {update_error}")
                else:
                    print(f"❌ Missing channel_id or message_ts for deletion")
                    print(f"❌ channel_id: {channel_id}, message_ts: {message_ts}")
                
                # Remove from active blockers if it exists there
                if hasattr(self, 'active_blockers') and blocker_id in self.active_blockers:
                    del self.active_blockers[blocker_id]
                    print(f"✅ Removed resolved blocker {blocker_id} from active blockers")
                
                # Delete the original unresolved blocker message if tracked
                if hasattr(self, 'tracked_blockers'):
                    for blocker_id, blocker_info in self.tracked_blockers.items():
                        if (
                            blocker_info['user_id'] == blocked_user_id and
                            blocker_info['kr_name'] == kr_name and
                            blocker_info['blocker_description'] == blocker_description
                        ):
                            # Try to delete the reminder/escalation message
                            channel_id = blocker_info.get('channel_id')
                            message_ts = blocker_info.get('escalation_ts')
                            if channel_id and message_ts:
                                try:
                                    self.client.chat_delete(channel=channel_id, ts=message_ts)
                                    print(f"✅ Deleted unresolved blocker message in channel {channel_id} at ts {message_ts}")
                                except Exception as e:
                                    print(f"❌ Error deleting unresolved blocker message: {e}")
                            break
                
                # Delete unresolved reminder messages
                if hasattr(self, 'unresolved_reminder_messages'):
                    # Try multiple key formats for reminder messages
                    reminder_keys_to_try = [
                        f"{blocked_user_id}_{kr_name}_{blocker_description[:30]}",
                        f"{blocked_user_id}_{kr_name}_{blocker_description}",
                        f"{blocked_user_id}_{kr_name}_From Coda check"
                    ]
                    
                    reminder_deleted = False
                    for reminder_key in reminder_keys_to_try:
                        if reminder_key in self.unresolved_reminder_messages:
                            reminder_info = self.unresolved_reminder_messages[reminder_key]
                            try:
                                self.client.chat_delete(
                                    channel=reminder_info['channel_id'], 
                                    ts=reminder_info['message_ts']
                                )
                                print(f"✅ Deleted unresolved reminder message for {reminder_key}")
                                # Remove from tracking
                                del self.unresolved_reminder_messages[reminder_key]
                                reminder_deleted = True
                                break
                            except Exception as e:
                                print(f"❌ Error deleting unresolved reminder message: {e}")
                    
                    if not reminder_deleted:
                        print(f"⚠️ No tracked reminder message found for any key: {reminder_keys_to_try}")
            else:
                # Send error message
                self.client.chat_postMessage(
                    channel=user,
                    text=f"❌ Sorry, there was an error marking the blocker as resolved. Please try again or contact the team."
                )
            
            # Always return a successful response to close the modal
            print("✅ Resolution modal submission completed successfully")
            return {"response_action": "clear"}, 200
        except Exception as e:
            print(f"❌ Error in handle_resolution_modal_submission: {e}")
            import traceback
            traceback.print_exc()
            return {"response_action": "clear"}, 200

    def _find_and_delete_original_blocker_message(self, channel_name, user_id, kr_name, blocker_description, resolver_name=None):
        """Find and delete the original blocker escalation message from the channel."""
        try:
            print(f"🔍 DEBUG: Searching for original blocker message in #{channel_name}")
            print(f"🔍 DEBUG: Looking for user: {user_id}, KR: {kr_name}, Description: {blocker_description}")
            
            # First, validate that the channel exists and we have access
            try:
                # Try to get channel info to validate access
                channel_info = self.client.conversations_info(channel=f"#{channel_name}")
                if not channel_info['ok']:
                    print(f"❌ Channel #{channel_name} not found or no access: {channel_info.get('error', 'Unknown error')}")
                    return False
                print(f"✅ Channel #{channel_name} validated")
            except Exception as e:
                print(f"❌ Error validating channel #{channel_name}: {e}")
                return False
            
            # Get recent messages from the channel
            try:
                response = self.client.conversations_history(
                    channel=f"#{channel_name}",
                    limit=50  # Get last 50 messages
                )
                
                if not response['ok']:
                    print(f"❌ Failed to get channel history: {response.get('error', 'Unknown error')}")
                    return False
                
                messages = response.get('messages', [])
                print(f"🔍 DEBUG: Found {len(messages)} messages in channel")
                
                # Look for the blocker escalation message
                for message in messages:
                    # Skip bot messages that aren't blocker escalations
                    if message.get('user') != 'U0912DJRNSF':  # Bot user ID
                        continue
                    
                    # Check if this is a blocker escalation message
                    text = message.get('text', '')
                    if 'BLOCKER ESCALATION' in text and 'is blocked and needs assistance' in text:
                        # Check if this message matches our blocker
                        if (user_id in text and 
                            kr_name in text and 
                            blocker_description in text):
                            
                            print(f"✅ Found matching blocker escalation message")
                            print(f"🔍 DEBUG: Message TS: {message.get('ts')}")
                            
                            # Delete the message
                            try:
                                delete_response = self.client.chat_delete(
                                    channel=f"#{channel_name}",
                                    ts=message.get('ts')
                                )
                                if delete_response['ok']:
                                    print(f"✅ Deleted original blocker escalation message from #{channel_name}")
                                    return True
                                else:
                                    print(f"❌ Failed to delete message: {delete_response.get('error', 'Unknown error')}")
                                    return False
                                
                            except Exception as e:
                                print(f"❌ Error deleting message: {e}")
                                return False
                
                print(f"⚠️ No matching blocker escalation message found")
                return False
                
            except Exception as e:
                print(f"❌ Error accessing channel history: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Error in _find_and_delete_original_blocker_message: {e}")
            return False

    def handle_blocker_form_submission(self, payload):
        """Handle blocker form submission from modal."""
        try:
            print("🔍 DEBUG: Received blocker form submission")
            print(f"🔍 DEBUG: Payload keys: {list(payload.keys())}")
            
            # Extract form data from the payload
            state = payload.get('view', {}).get('state', {})
            values = state.get('values', {})
            
            print(f"🔍 DEBUG: State keys: {list(state.keys())}")
            print(f"🔍 DEBUG: Values keys: {list(values.keys())}")
            
            # Get blocker details from form
            blocker_description = values.get('blocker_description', {}).get('blocker_description_input', {}).get('value', '')
            kr_name = values.get('kr_name', {}).get('kr_name_input', {}).get('value', '')
            urgency = values.get('urgency', {}).get('urgency_input', {}).get('selected_option', {}).get('value', '')
            notes = values.get('notes', {}).get('notes_input', {}).get('value', '')
            
            print(f"🔍 DEBUG: Extracted values:")
            print(f"   Blocker Description: {blocker_description}")
            print(f"   KR Name: {kr_name}")
            print(f"   Urgency: {urgency}")
            print(f"   Notes: {notes}")
            
            # Get user info
            user = payload.get('user', {}).get('id', 'unknown')
            username = payload.get('user', {}).get('name', 'unknown')
            
            print(f"🔍 DEBUG: User: {user} ({username})")
            
            # Store in Coda (primary) and MongoDB (fallback)
            success = False
            
            # Try Coda first
            if self.coda and self.coda.blocker_table_id:
                try:
                    print("🔍 DEBUG: Attempting to store in Coda...")
                    success = self.coda.add_blocker(
                        user_id=user,
                        blocker_description=blocker_description,
                        kr_name=kr_name,
                        urgency=urgency,
                        notes=notes,
                        username=username
                    )
                    if success:
                        print(f"✅ Blocker details stored in Coda for {username}")
                    else:
                        print("❌ Coda storage failed")
                except Exception as e:
                    print(f"❌ Error storing blocker in Coda: {e}")
            
            # Send confirmation and escalate
            if success:
                print("🔍 DEBUG: Storage successful, escalating...")
                # Escalate with detailed information
                self.escalate_blocker_with_details(user, username, blocker_description, kr_name, urgency, notes)
            else:
                print("❌ DEBUG: Storage failed in Coda")
            
            return {"response_action": "clear"}, 200
            
        except Exception as e:
            print(f"❌ Error in handle_blocker_form_submission: {e}")
            return {"response_action": "clear"}, 200
    
    def escalate_blocker_with_details(self, user_id, user_name, blocker_description, kr_name, urgency, notes):
        """Escalate blocker with detailed information to leads channel with claim functionality."""
        try:
            import time
            
            # Format urgency with emoji
            urgency_emoji = {
                'Low': '🟢',
                'Medium': '🟡', 
                'High': '🟠',
                'Critical': '🔴'
            }.get(urgency, '⚪')
            
            # Get current KR status from Coda
            kr_status_info = "Unknown"
            print(f"🔍 DEBUG: Attempting to fetch KR status for '{kr_name}'")
            if self.coda and kr_name and kr_name != "Unknown KR":
                try:
                    print(f"🔍 DEBUG: Coda service available, calling get_kr_details for '{kr_name}'")
                    kr_details = self.coda.get_kr_details(kr_name)
                    print(f"🔍 DEBUG: get_kr_details returned: {kr_details}")
                    if kr_details:
                        current_status = kr_details.get('status', 'Unknown')
                        current_helper = kr_details.get('helper', '')
                        print(f"🔍 DEBUG: Current status: '{current_status}', helper: '{current_helper}'")
                        if current_status and current_status != 'Unknown':
                            if current_helper:
                                kr_status_info = f"{current_status} (by {current_helper})"
                            else:
                                kr_status_info = current_status
                        else:
                            kr_status_info = "In Progress"
                        print(f"🔍 DEBUG: Final kr_status_info: '{kr_status_info}'")
                    else:
                        kr_status_info = "Not Found in KR Table"
                        print(f"⚠️ KR '{kr_name}' not found in Coda table - may be a placeholder or incorrect name")
                except Exception as kr_error:
                    print(f"❌ Error fetching KR status: {kr_error}")
                    kr_status_info = "Error fetching status"
            else:
                print(f"🔍 DEBUG: Skipping KR status fetch - Coda: {self.coda is not None}, kr_name: '{kr_name}'")
            
            # Create unique blocker ID for tracking
            blocker_id = f"blocker_{user_id}_{int(time.time())}"
            
            # Create escalation message with claim functionality
            escalation_message = f"🚨 *BLOCKER ESCALATION - {urgency_emoji} {urgency} Priority*\n\n"
            escalation_message += f"<@{user_id}> ({user_name}) is blocked and needs assistance!\n\n"
            escalation_message += f"*Blocker Details:*\n"
            escalation_message += f"• **Description:** {blocker_description}\n"
            escalation_message += f"• **KR:** {kr_name}\n"
            escalation_message += f"• **Urgency:** {urgency_emoji} {urgency}\n"
            escalation_message += f"• **Notes:** {notes if notes else 'None'}\n"
            escalation_message += f"• **Current KR Status:** {kr_status_info}\n\n"
            escalation_message += f"*Status:* ⏳ Unclaimed - Available for leads to claim"
            
            # Create message blocks with claim buttons
            message_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                        "text": escalation_message
                        }
                    },
                    {
                        "type": "actions",
                    "block_id": f"claim_blocker_{blocker_id}",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                "text": "🎯 Claim Blocker",
                                    "emoji": True
                                },
                            "value": f"claim_{blocker_id}_{user_id}_{user_name}",
                            "action_id": "claim_blocker",
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                "text": "📋 View Details",
                                    "emoji": True
                                },
                            "value": f"view_{blocker_id}",
                            "action_id": "view_blocker_details"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Mark Resolved",
                                "emoji": True
                            },
                            "value": f"resolve_{blocker_id}",
                            "action_id": "mark_resolved",
                            "style": "primary"
                        }
                    ]
                }
            ]
            
            # Send to leads channel (or general if no leads channel)
            leads_channel = getattr(self.config, 'SLACK_LEADS_CHANNEL', 'leads')
            try:
                response = self.client.chat_postMessage(
                    channel=f"#{leads_channel}",
                    blocks=message_blocks,
                    text=f"🚨 Blocker Alert: {user_name} needs help with {kr_name}"
                )
                print(f"✅ Blocker escalation sent to #{leads_channel} for {user_name}")
            except Exception as e:
                print(f"❌ Error sending to leads channel, falling back to general: {e}")
                # Fallback to general channel
                response = self.client.chat_postMessage(
                    channel="#general",
                    blocks=message_blocks,
                    text=f"🚨 Blocker Alert: {user_name} needs help with {kr_name}"
                )
                print(f"✅ Blocker escalation sent to #general for {user_name}")
            
            # Store blocker info for tracking
            blocker_info = {
                'blocker_id': blocker_id,
                'user_id': user_id,
                'user_name': user_name,
                'blocker_description': blocker_description,
                'kr_name': kr_name,
                'urgency': urgency,
                'notes': notes,
                'kr_status_info': kr_status_info,
                'escalation_ts': response['ts'],
                'channel': leads_channel,
                'channel_id': response.get('channel'),
                'message_ts': response['ts'],
                'status': 'unclaimed',
                'claimed_by': None,
                'claimed_at': None,
                'progress_updates': []
            }
            if not hasattr(self, 'active_blockers'):
                self.active_blockers = {}
            self.active_blockers[blocker_id] = blocker_info
            # Pass channel_id and message_ts to tracking
            self.track_blocker_for_followup(
                user_id=user_id,
                user_name=user_name,
                blocker_description=blocker_description,
                kr_name=kr_name,
                urgency=urgency,
                notes=notes,
                escalation_ts=response['ts'],
                channel_id=response.get('channel'),
                message_ts=response['ts']
            )
            
            return response['ts']
            
        except SlackApiError as e:
            print(f"❌ Error escalating blocker with details: {e.response['error']}")
            print(f"🔍 DEBUG: Error details: {e.response}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error in escalate_blocker_with_details: {e}")
            return None

    def escalate_help_request(self, user_id, user_name, user_data):
        """Show enhanced blocker form as a modal instead of immediate escalation."""
        try:
            # Open a modal with the blocker form
            modal_view = {
                "type": "modal",
                "callback_id": "blocker_form",
                "title": {
                    "type": "plain_text",
                    "text": "Report Blocker",
                    "emoji": True
                },
                "submit": {
                    "type": "plain_text",
                    "text": "Submit",
                    "emoji": True
                },
                "close": {
                    "type": "plain_text",
                    "text": "Cancel",
                    "emoji": True
                },
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"<@{user_id}>, I see you need help! 🚨\n\n"
                                   "Let me help you get unblocked. Please provide the following information:"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "blocker_description",
                        "label": {
                            "type": "plain_text",
                            "text": "What's blocking you?",
                            "emoji": True
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "blocker_description_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Describe the blocker in detail..."
                            },
                            "multiline": True
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "kr_name",
                        "label": {
                            "type": "plain_text",
                            "text": "Key Result (KR) Name",
                            "emoji": True
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "kr_name_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "e.g., KR1: Increase user engagement"
                            }
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "urgency",
                        "label": {
                            "type": "plain_text",
                            "text": "Urgency Level",
                            "emoji": True
                        },
                        "element": {
                            "type": "static_select",
                            "action_id": "urgency_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Select urgency level"
                            },
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Low - Can wait a few days"
                                    },
                                    "value": "Low"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Medium - Need help this week"
                                    },
                                    "value": "Medium"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "High - Blocking progress now"
                                    },
                                    "value": "High"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Critical - Blocking team/delivery"
                                    },
                                    "value": "Critical"
                                }
                            ]
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "notes",
                        "label": {
                            "type": "plain_text",
                            "text": "Additional Notes (Optional)",
                            "emoji": True
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "notes_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Any additional context or details..."
                            },
                            "multiline": True
                        },
                        "optional": True
                    }
                ]
            }
            
            # Open the modal
            response = self.client.views_open(
                trigger_id=user_data.get('trigger_id', ''),
                view=modal_view
            )
            
            print(f"✅ Blocker modal opened for {user_name}")
            
        except SlackApiError as e:
            print(f"Error opening blocker modal: {e.response['error']}")
            # Fallback: send a simple message if modal fails
            self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=user_data['thread_ts'],
                text=f"<@{user_id}>, I see you need help! Please contact your mentor or team lead directly. 🚨"
            )

    def escalate_issue(self, user_id, user_name, parsed_data):
        """Escalate issue based on parsed standup data."""
        try:
            escalation_message = f"🚨 *Issue Escalation*\n\n<@{user_id}> reported issues in standup:\n\n*Details:*\n• On Track: {parsed_data.get('on_track', 'Unknown')}\n• Blockers: {parsed_data.get('blockers', 'Unknown')}\n• Today's Work: {parsed_data.get('today', 'Not specified')}\n\nPlease check the standup thread and offer support."
            
            self.client.chat_postMessage(
                channel=f"#{getattr(self.config, 'SLACK_ESCALATION_CHANNEL', 'leads')}",
                text=escalation_message
            )
            
        except SlackApiError as e:
            print(f"Error escalating issue: {e.response['error']}")

    def check_missing_responses(self):
        """Check for missing responses and send reminders."""
        try:
            # Get current time
            now = datetime.now()
            
            # Check each active standup
            for standup_ts, standup_data in self.active_standups.items():
                # Calculate time since standup
                time_since = now - standup_data['timestamp']
                
                # If more than 2 hours have passed, send reminder
                if time_since.total_seconds() > 7200:  # 2 hours
                    reminder_message = "⏰ *Reminder: Please respond to the daily standup!*\n\nIf you haven't already, please either:\n• React to the main message with your status\n• Reply in the thread with your detailed update\n\nYour input helps the team stay aligned! 💬"
                    
                    self.client.chat_postMessage(
                        channel=self.channel_id,
                        thread_ts=standup_ts,
                        text=reminder_message
                    )
                    
                    print(f"Reminder sent for standup {standup_ts}")
                    
        except SlackApiError as e:
            print(f"Error checking missing responses: {e.response['error']}")

    def handle_button_click(self, payload):
        trigger_id = payload.get('trigger_id')  # Ensure trigger_id is always available
        try:
            print("Received button click payload:", payload)
            user = payload['user']['id']
            username = payload['user'].get('name', payload['user'].get('username', 'Unknown'))
            
            # Handle different action types
            action_data = payload['actions'][0]
            action_id = action_data['action_id']
            
            # Get action value safely (not all actions have 'value')
            action = action_data.get('value', '')
            
            message_ts = payload['message']['ts']
            channel_id = payload['channel']['id']
            print(f"User {username} ({user}) clicked {action_id} with value: {action}")
            
            # Handle health check buttons
            if action_id in ['great', 'okay', 'not_great']:
                # Check if user has already responded to this health check
                response_key = f"{user}_{message_ts}"
                if response_key in self.health_check_responses:
                    print(f"❌ User {username} already responded to health check")
                    return {"response_action": "errors", "errors": ["User already responded"]}, 200
                
                # Store response and mark user as responded
                success = False
                
                # Try Coda first (primary storage)
                if self.coda and self.coda.main_table_id:
                    try:
                        success = self.coda.add_response(
                            user_id=user,
                            response=action,
                            username=username
                        )
                        if success:
                            print(f"✅ Health check response stored in Coda for {username}")
                    except Exception as e:
                        print(f"❌ Error storing health check in Coda: {e}")
                
                if not success:
                    print("❌ Failed to store health check response in Coda")
                
                self.health_check_responses.add(response_key)
                
                # Send follow-up prompt asking why they feel that way
                followup_prompt_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Thanks for your response! Could you tell us a bit more about why you're feeling {action.replace('_', ' ')} today?"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "health_check_explanation",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "explanation_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Share your thoughts, feelings, or any context that might help us understand better..."
                            }
                        },
                        "label": {
                            "type": "plain_text",
                            "text": "Why do you feel this way?",
                            "emoji": True
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Public Chat",
                                    "emoji": True
                                },
                                "value": f"public_{action}",
                                "action_id": "public_chat",
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Private Chat",
                                    "emoji": True
                                },
                                "value": f"private_{action}",
                                "action_id": "private_chat"
                            }
                        ]
                    }
                ]
                
                # Send the follow-up prompt
                self.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    blocks=followup_prompt_blocks,
                    text="Tell us more about how you're feeling"
                )
                
                return {"response_action": "clear"}, 200
            
            # Handle mentor response
            elif action_id in ['mentor_response_yes', 'mentor_response_no']:
                # Extract mentor response and request type from action value
                mentor_response = "Yes" if action_id == 'mentor_response_yes' else "No"
                request_type = action.split('_')[-1] if '_' in action else "blocker"
                
                print(f"🔍 DEBUG: Mentor response received:")
                print(f"   - User: {username} ({user})")
                print(f"   - Response: {mentor_response}")
                print(f"   - Request Type: {request_type}")
                
                # Store mentor response in Coda
                success = False
                if self.coda and self.coda.mentor_table_id:
                    try:
                        success = self.coda.add_mentor_check(
                            user_id=user,
                            mentor_response=mentor_response,
                            request_type=request_type,
                            username=username
                        )
                        if success:
                            print(f"✅ Mentor response stored in Coda for {username}")
                    except Exception as e:
                        print(f"❌ Error storing mentor response in Coda: {e}")
                
                if not success:
                    print("❌ Failed to store mentor response in Coda")
                
                # Handle based on mentor response
                if mentor_response == "Yes":
                    if request_type == "blocker":
                        self.send_help_followup(
                            user_id=user,
                            standup_ts=message_ts,
                            user_name=username,
                            channel=channel_id
                        )
                        response_text = "Great! Let's get you the help you need. Please fill out the details above."
                    elif request_type == "kr":
                        # Check if a search term was provided
                        search_term = None
                        if hasattr(self, 'pending_kr_search'):
                            search_term = self.pending_kr_search.get(user)
                        if search_term:
                            # Show KR search results
                            matches = self.coda.search_kr_table(search_term)
                            if matches:
                                result_lines = []
                                for m in matches:
                                    kr_name = m.get('c-yQ1M6UqTSj', 'N/A')
                                    owner = m.get('c-efR-vVo_3w', 'N/A')
                                    status = m.get('c-cC29Yow8Gr', 'N/A')
                                    definition_of_done = m.get('c-P_mQJLObL0', '')
                                    link = m.get('link', None)
                                    explanation = generate_kr_explanation(kr_name, owner, status, definition_of_done)
                                    line = f"*KR*: {kr_name}\n*Owner*: {owner}\n*Status*: {status}\n*Definition of Done*: {definition_of_done}\n*AI Explanation*: {explanation}"
                                    if link:
                                        line += f"\n<Link|{link}>"
                                    result_lines.append(line)
                                result_text = '\n\n'.join(result_lines)
                            else:
                                result_text = f'No matching KRs found for "{search_term}".'
                            self.client.chat_postMessage(
                                channel=channel_id,
                                thread_ts=message_ts,
                                text=result_text
                            )
                            self.pending_kr_search[user] = None
                            response_text = None  # Already sent results
                        else:
                            # No search term provided, prompt for KR
                            self.client.chat_postMessage(
                                channel=channel_id,
                                thread_ts=message_ts,
                                text="What KR would you like to search for? Please type `/kr [search term]` or `!kr [search term]`."
                            )
                            response_text = None  # Already sent prompt
                    else:
                        response_text = "Great! Let's proceed with your request."
                else:
                    # Use the new function for 'No' response
                    self.handle_mentor_no_response(user, channel_id, message_ts)
                    return {"response_action": "clear"}, 200
                if response_text:
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=response_text
                    )
                return {"response_action": "clear"}, 200
            
            # Handle blocker form submission
            elif action_id == 'submit_blocker_details':
                # Extract form data from the payload
                state = payload.get('state', {})
                values = state.get('values', {})
                
                # Get blocker details from form
                blocker_description = values.get('blocker_description', {}).get('blocker_description_input', {}).get('value', '')
                kr_name = values.get('kr_name', {}).get('kr_name_input', {}).get('value', '')
                urgency = values.get('urgency', {}).get('urgency_input', {}).get('selected_option', {}).get('value', '')
                notes = values.get('notes', {}).get('notes_input', {}).get('value', '')
                
                # Store in Coda (primary) and MongoDB (fallback)
                success = False
                
                print(f"🔍 DEBUG: Attempting to store blocker details:")
                print(f"   - User: {username} ({user})")
                print(f"   - Description: {blocker_description}")
                print(f"   - KR: {kr_name}")
                print(f"   - Urgency: {urgency}")
                print(f"   - Notes: {notes}")
                print(f"   - Coda available: {self.coda is not None}")
                print(f"   - Blocker table ID: {getattr(self.coda, 'blocker_table_id', 'NOT SET') if self.coda else 'NO CODA'}")
                
                # Try Coda first
                if self.coda and self.coda.blocker_table_id:
                    try:
                        success = self.coda.add_blocker(
                            user_id=user,
                            blocker_description=blocker_description,
                            kr_name=kr_name,
                            urgency=urgency,
                            notes=notes,
                            username=username
                        )
                        if success:
                            print(f"✅ Blocker details stored in Coda for {username}")
                        else:
                            print(f"❌ Coda.add_blocker returned False for {username}")
                    except Exception as e:
                        print(f"❌ Error storing blocker in Coda: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"❌ Cannot store in Coda - missing configuration")
                    if not self.coda:
                        print(f"   - Coda service not available")
                    if not getattr(self.coda, 'blocker_table_id', None):
                        print(f"   - Blocker table ID not configured (CODA_TABLE_ID2)")
                

                        
                # Send confirmation and escalate
                if success:
                    # Send confirmation to user
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"✅ Thanks <@{user}>! Your blocker details have been recorded and escalated to the team."
                    )
                    
                    # Escalate with detailed information
                    self.escalate_blocker_with_details(user, username, blocker_description, kr_name, urgency, notes)
                else:
                    # Send error message
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"❌ Sorry <@{user}>, there was an error saving your blocker details. Please try again or contact the team directly."
                    )
                
                return {"response_action": "clear"}, 200
            
            # Handle role selector dropdown
            elif action_id == 'role_selector':
                # Parse the selected value: action_type_role_user_mention
                selected_value = action_data.get('selected_option', {}).get('value', '')
                if selected_value:
                    parts = selected_value.split('_', 2)  # Split into max 3 parts
                    if len(parts) >= 2:
                        action_type = parts[0]
                        role = parts[1]
                        user_mention = parts[2] if len(parts) > 2 else None
                        
                        print(f"🔍 DEBUG: Role selector selected:")
                        print(f"   - Action: {action_type}")
                        print(f"   - Role: {role}")
                        print(f"   - User: {user_mention}")
                        
                        # Execute the role action
                        if action_type == 'add' and user_mention:
                            self._add_user_role(user_mention, role, channel_id)
                        elif action_type == 'remove' and user_mention:
                            self._remove_user_role(user_mention, role, channel_id)
                        elif action_type == 'users':
                            self._list_users_by_role(role, channel_id)
                        
                        # Update the message to show the action was completed
                        self.client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=message_ts,
                            text=f"✅ Role action completed: {action_type} {role}"
                        )
                
                return {"response_action": "clear"}, 200
            
            # Handle follow-up buttons
            elif action_id in ['escalate_help', 'monitor_issue']:
                trigger_id = payload.get('trigger_id')
                
                if action_id == 'escalate_help':
                    # Open a modal with the blocker form
                    try:
                        modal_view = {
                            "type": "modal",
                            "callback_id": "blocker_form",
                            "title": {
                                "type": "plain_text",
                                "text": "Report Blocker",
                                "emoji": True
                            },
                            "submit": {
                                "type": "plain_text",
                                "text": "Submit",
                                "emoji": True
                            },
                            "close": {
                                "type": "plain_text",
                                "text": "Cancel",
                                "emoji": True
                            },
                            "blocks": [
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": f"<@{user}>, I see you need help! 🚨\n\n"
                                               "Let me help you get unblocked. Please provide the following information:"
                                    }
                                },
                                {
                                    "type": "input",
                                    "block_id": "blocker_description",
                                    "label": {
                                        "type": "plain_text",
                                        "text": "What's blocking you?",
                                        "emoji": True
                                    },
                                    "element": {
                                        "type": "plain_text_input",
                                        "action_id": "blocker_description_input",
                                        "placeholder": {
                                            "type": "plain_text",
                                            "text": "Describe the blocker in detail..."
                                        },
                                        "multiline": True
                                    }
                                },
                                {
                                    "type": "input",
                                    "block_id": "kr_name",
                                    "label": {
                                        "type": "plain_text",
                                        "text": "Key Result (KR) Name",
                                        "emoji": True
                                    },
                                    "element": {
                                        "type": "plain_text_input",
                                        "action_id": "kr_name_input",
                                        "placeholder": {
                                            "type": "plain_text",
                                            "text": "e.g., KR1: Increase user engagement"
                                        }
                                    }
                                },
                                {
                                    "type": "input",
                                    "block_id": "urgency",
                                    "label": {
                                        "type": "plain_text",
                                        "text": "Urgency Level",
                                        "emoji": True
                                    },
                                    "element": {
                                        "type": "static_select",
                                        "action_id": "urgency_input",
                                        "placeholder": {
                                            "type": "plain_text",
                                            "text": "Select urgency level"
                                        },
                                        "options": [
                                            {
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "Low - Can wait a few days"
                                                },
                                                "value": "Low"
                                            },
                                            {
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "Medium - Need help this week"
                                                },
                                                "value": "Medium"
                                            },
                                            {
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "High - Blocking progress now"
                                                },
                                                "value": "High"
                                            },
                                            {
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "Critical - Blocking team/delivery"
                                                },
                                                "value": "Critical"
                                            }
                                        ]
                                    }
                                },
                                {
                                    "type": "input",
                                    "block_id": "notes",
                                    "label": {
                                        "type": "plain_text",
                                        "text": "Additional Notes (Optional)",
                                        "emoji": True
                                    },
                                    "element": {
                                        "type": "plain_text_input",
                                        "action_id": "notes_input",
                                        "placeholder": {
                                            "type": "plain_text",
                                            "text": "Any additional context or details..."
                                        },
                                        "multiline": True
                                    },
                                    "optional": True
                                }
                            ]
                        }
                        
                        # Open the modal
                        response = self.client.views_open(
                            trigger_id=trigger_id,
                            view=modal_view
                        )
                        
                        print(f"✅ Blocker modal opened for {username}")
                        
                    except SlackApiError as e:
                        print(f"Error opening blocker modal: {e.response['error']}")
                        # Fallback: send a simple message if modal fails
                        self.client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=message_ts,
                            text=f"<@{user}>, I see you need help! Please contact your mentor or team lead directly. 🚨"
                        )
                    
                    return {"response_action": "clear"}, 200
                elif action_id == 'monitor_issue':
                    # Handle "Can wait" button - acknowledge and clean up
                    try:
                        # Send acknowledgment message
                        self.client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=message_ts,
                            text=f"Got it <@{user}>, we'll keep an eye on this. Please keep your mentor informed of any updates! 🚧"
                        )
                        print(f"✅ 'Can wait' acknowledged for {username}")
                        return {"response_action": "clear"}, 200
                    except Exception as e:
                        print(f"❌ Error handling 'Can wait' button: {e}")
                        return {"response_action": "errors", "errors": ["Error processing request"]}, 500
                else:
                    print(f"❌ No user data found for {user}")
                    return {"response_action": "errors", "errors": ["No user data found"]}, 400
            
            # Handle explanation submission
            elif action_id == 'submit_explanation':
                # Extract explanation from the input
                state = payload.get('state', {})
                values = state.get('values', {})
                explanation = values.get('health_check_explanation', {}).get('explanation_input', {}).get('value', '')
                
                # Extract the original health check response from the button value
                original_response = action.split('_', 1)[1] if '_' in action else 'unknown'
                
                # Save to After_Health_Check table
                success = False
                if self.coda:
                    try:
                        # Add method to save to After_Health_Check table
                        success = self.coda.add_health_check_explanation(
                            user_id=user,
                            username=username,
                            health_check_response=original_response,
                            explanation=explanation
                        )
                        if success:
                            print(f"✅ Health check explanation stored in Coda for {username}")
                    except Exception as e:
                        print(f"❌ Error storing health check explanation in Coda: {e}")
                
                # Send confirmation
                if success:
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"✅ Thanks <@{user}>! Your explanation has been recorded."
                    )
                else:
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"❌ Sorry <@{user}>, there was an error saving your explanation. Please try again."
                    )
                
                return {"response_action": "clear"}, 200
            
            # Handle skip explanation
            elif action_id == 'skip_explanation':
                self.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text=f"👍 No problem <@{user}>! Thanks for your health check response."
                )
                return {"response_action": "clear"}, 200
            
            # Handle public chat (saves to Coda)
            elif action_id == 'public_chat':
                # Extract explanation from the input
                state = payload.get('state', {})
                values = state.get('values', {})
                explanation = values.get('health_check_explanation', {}).get('explanation_input', {}).get('value', '')
                
                # Extract the original health check response from the button value
                original_response = action.split('_', 1)[1] if '_' in action else 'unknown'
                
                # Save to After_Health_Check table
                success = False
                if self.coda:
                    try:
                        success = self.coda.add_health_check_explanation(
                            user_id=user,
                            username=username,
                            health_check_response=original_response,
                            explanation=explanation
                        )
                        if success:
                            print(f"✅ Public health check explanation stored in Coda for {username}")
                    except Exception as e:
                        print(f"❌ Error storing public health check explanation in Coda: {e}")
                
                # Send confirmation
                if success:
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"✅ Thanks <@{user}>! Your explanation has been recorded and shared with the team."
                    )
                else:
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"❌ Sorry <@{user}>, there was an error saving your explanation. Please try again."
                    )
                
                return {"response_action": "clear"}, 200
            
            # Handle private chat (doesn't save to Coda)
            elif action_id == 'private_chat':
                # Extract explanation from the input
                state = payload.get('state', {})
                values = state.get('values', {})
                explanation = values.get('health_check_explanation', {}).get('explanation_input', {}).get('value', '')
                
                # Send private response without saving to Coda
                if explanation.strip():
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"🤫 <@{user}>, I understand. Your message is private and won't be shared with the team. If you need anything, feel free to reach out anytime!"
                    )
                else:
                    self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"🤫 <@{user}>, no worries! This conversation is private. If you need anything later, just let me know."
                    )
                
                return {"response_action": "clear"}, 200
            
            # Handle "I can help!" button clicks
            elif action_id == 'offer_help':
                # Check if help has already been offered for this message
                if message_ts in self.help_offers:
                    print(f"❌ Help already offered for message {message_ts}")
                    return {"response_action": "errors", "errors": ["Help already offered"]}, 200
                
                # Extract the user who needs help from the button value
                # Button value format: "help_{user_id}"
                if action.startswith('help_'):
                    help_needed_user_id = action.replace('help_', '')
                    
                    # Mark this message as having help offered
                    self.help_offers.add(message_ts)
                    
                    # Get the helper's name
                    helper_info = self.client.users_info(user=user)
                    helper_name = helper_info['user']['real_name']
                    
                    # Get the person who needs help's name
                    try:
                        help_needed_info = self.client.users_info(user=help_needed_user_id)
                        help_needed_name = help_needed_info['user']['real_name']
                    except:
                        help_needed_name = f"<@{help_needed_user_id}>"
                    
                    # Update the message to show who offered help and current KR status
                    kr_name = self.get_kr_from_message(payload['message'])
                    
                    # Get current KR status from Coda
                    kr_status_info = "Unknown"
                    if self.coda and kr_name and kr_name != "Unknown KR":
                        try:
                            kr_details = self.coda.get_kr_details(kr_name)
                            if kr_details:
                                current_status = kr_details.get('status', 'Unknown')
                                current_helper = kr_details.get('helper', '')
                                if current_status and current_status != 'Unknown':
                                    if current_helper:
                                        kr_status_info = f"{current_status} (by {current_helper})"
                                    else:
                                        kr_status_info = current_status
                                else:
                                    kr_status_info = "In Progress"
                            else:
                                kr_status_info = "Not Found"
                        except Exception as kr_error:
                            print(f"❌ Error fetching KR status: {kr_error}")
                            kr_status_info = "Error fetching status"
                    
                    updated_blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"✅ *Blocker Resolved*\n\n<@{help_needed_user_id}> ({help_needed_name}) has been helped by <@{user}> ({helper_name})!\n\n*KR:* {kr_name}\n*Current Status:* {kr_status_info}\n\nIf you'd like to offer additional help, you can still reach out to <@{help_needed_user_id}> directly."
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "✅ Helped",
                                        "emoji": True
                                    },
                                    "value": "helped",
                                    "action_id": "helped",
                                    "style": "primary",
                                    "confirm": {
                                        "title": {
                                            "type": "plain_text",
                                            "text": "Already Helped"
                                        },
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": "This person has already been helped. The button is now disabled."
                                        },
                                        "confirm": {
                                            "type": "plain_text",
                                            "text": "OK"
                                        },
                                        "deny": {
                                            "type": "plain_text",
                                            "text": "Cancel"
                                        }
                                    }
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🔄 Check if Finished",
                                        "emoji": True
                                    },
                                    "value": f"refresh_{kr_name}",
                                    "action_id": "refresh_status"
                                }
                            ]
                        }
                    ]
                    
                    # Update the message - this should replace the entire original message
                    try:
                        print(f"🔍 DEBUG: Attempting to update message {message_ts} in channel {channel_id}")
                        print(f"🔍 DEBUG: Updated blocks: {updated_blocks}")
                        
                        update_response = self.client.chat_update(
                            channel=channel_id,
                            ts=message_ts,
                            blocks=updated_blocks,
                            text=f"✅ {help_needed_name} has been helped by {helper_name}!"
                        )
                        
                        print(f"✅ Message successfully updated: {update_response}")
                        
                        # Get KR information for display
                        kr_name = self.get_kr_from_message(payload['message'])
                        if kr_name and kr_name != "Unknown KR" and self.coda:
                            try:
                                kr_info = self.coda.get_kr_display_info(kr_name)
                                if kr_info:
                                    print(f"✅ KR '{kr_name}' information retrieved for display")
                                    # You can use kr_info here to display additional details if needed
                                else:
                                    print(f"⚠️ Failed to get KR '{kr_name}' information from Coda")
                            except Exception as kr_error:
                                print(f"❌ Error getting KR information: {kr_error}")
                        
                        # Send DM to the person who needed help
                        try:
                            dm_response = self.client.conversations_open(users=[help_needed_user_id])
                            dm_channel = dm_response['channel']['id']
                            
                            self.client.chat_postMessage(
                                channel=dm_channel,
                                text=f"🎉 Great news! <@{user}> ({helper_name}) has offered to help you with your blocker. They should be reaching out to you soon!"
                            )
                        except Exception as e:
                            print(f"❌ Could not send DM to {help_needed_user_id}: {e}")
                        
                        print(f"✅ Help offered by {helper_name} to {help_needed_name}")
                        
                    except Exception as e:
                        print(f"❌ Error updating message: {e}")
                        print(f"🔍 DEBUG: Error details: {str(e)}")
                        
                        # Try alternative approach: delete and repost
                        try:
                            print("🔍 DEBUG: Trying alternative approach - delete and repost")
                            
                            # Delete the original message
                            self.client.chat_delete(
                                channel=channel_id,
                                ts=message_ts
                            )
                            
                            # Post the updated message
                            self.client.chat_postMessage(
                                channel=channel_id,
                                blocks=updated_blocks,
                                text=f"✅ {help_needed_name} has been helped by {helper_name}!"
                            )
                            
                            print("✅ Successfully replaced message using delete/repost method")
                            
                        except Exception as delete_error:
                            print(f"❌ Delete/repost also failed: {delete_error}")
                            
                            # Final fallback: send a simple message
                            self.client.chat_postMessage(
                                channel=channel_id,
                                thread_ts=message_ts,
                                text=f"✅ <@{user}> ({helper_name}) has offered to help <@{help_needed_user_id}> ({help_needed_name})!"
                            )
                    
                    return {"response_action": "clear"}, 200
                else:
                    print(f"❌ Invalid help button value: {action}")
                    return {"response_action": "errors", "errors": ["Invalid help request"]}, 400
            
            # Handle "Helped" button (non-interactive confirmation)
            elif action_id == 'helped':
                # This button is just for show - it's already been helped
                # We could add a confirmation dialog or just ignore the click
                return {"response_action": "clear"}, 200
            
            # Handle "Mark as Completed" button
            elif action_id == 'mark_completed':
                # Extract KR name from button value (format: "complete_{kr_name}")
                if action.startswith('complete_'):
                    kr_name = action.replace('complete_', '')
                    
                    # Get KR information for display
                    if self.coda:
                        try:
                            kr_info = self.coda.get_kr_display_info(kr_name)
                            if kr_info:
                                # Display KR information without updating status
                                display_text = f"📊 *KR Information*\n\n*{kr_name}*\n"
                                display_text += f"• **Owner:** {kr_info.get('owner', 'Unknown')}\n"
                                display_text += f"• **Status:** {kr_info.get('status', 'Unknown')}\n"
                                display_text += f"• **Progress:** {kr_info.get('progress', 'Unknown')}%\n"
                                display_text += f"• **Objective:** {kr_info.get('objective', 'Unknown')}\n"
                                display_text += f"• **Sprint:** {kr_info.get('sprint', 'Unknown')}\n"
                                display_text += f"• **Predicted Hours:** {kr_info.get('predicted_hours', 'Unknown')}\n"
                                display_text += f"• **Urgency:** {kr_info.get('urgency', 'Unknown')}\n"
                                
                                if kr_info.get('notes'):
                                    display_text += f"• **Notes:** {kr_info.get('notes', '')[:100]}...\n"
                                
                                display_blocks = [
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": display_text
                                        }
                                    }
                                ]
                                
                                try:
                                    self.client.chat_update(
                                        channel=channel_id,
                                        ts=message_ts,
                                        blocks=display_blocks,
                                        text=f"📊 KR Information: {kr_name}"
                                    )
                                    print(f"✅ KR '{kr_name}' information displayed")
                                except Exception as update_error:
                                    print(f"❌ Error updating display message: {update_error}")
                            else:
                                print(f"⚠️ Failed to get KR '{kr_name}' information from Coda")
                        except Exception as kr_error:
                            print(f"❌ Error getting KR information: {kr_error}")
                    
                    return {"response_action": "clear"}, 200
                else:
                    print(f"❌ Invalid completion button value: {action}")
                    return {"response_action": "errors", "errors": ["Invalid completion request"]}, 400
            
            # Handle "Refresh Status" button
            elif action_id == 'refresh_status':
                # Extract KR name from button value (format: "refresh_{kr_name}")
                if action.startswith('refresh_'):
                    safe_kr_name = action.replace('refresh_', '')
                    
                    # Get original KR name from mapping
                    kr_name = self.kr_name_mappings.get(safe_kr_name, safe_kr_name)
                    
                    # Get current KR status from Coda
                    kr_status_info = "Unknown"
                    if self.coda and kr_name and kr_name != "Unknown KR":
                        try:
                            kr_details = self.coda.get_kr_details(kr_name)
                            if kr_details:
                                current_status = kr_details.get('status', 'Unknown')
                                current_helper = kr_details.get('helper', '')
                                if current_status and current_status != 'Unknown':
                                    if current_helper:
                                        kr_status_info = f"{current_status} (by {current_helper})"
                                    else:
                                        kr_status_info = current_status
                                else:
                                    kr_status_info = "In Progress"
                            else:
                                kr_status_info = "Not Found in KR Table"
                                print(f"⚠️ KR '{kr_name}' not found in Coda table - may be a placeholder or incorrect name")
                        except Exception as kr_error:
                            print(f"❌ Error fetching KR status: {kr_error}")
                            kr_status_info = "Error fetching status"
                    
                    # Get the original message to extract user info and other details
                    try:
                        original_message = self.client.conversations_history(
                            channel=channel_id,
                            latest=message_ts,
                            limit=1,
                            inclusive=True
                        )
                        
                        if original_message['messages']:
                            original_text = original_message['messages'][0].get('text', '')
                            original_blocks = original_message['messages'][0].get('blocks', [])
                            print(f"🔍 DEBUG: Original message text: '{original_text}'")
                            print(f"🔍 DEBUG: Original message has {len(original_blocks)} blocks")
                            # Extract user info from original message
                            if 'is blocked and needs assistance' in original_text:
                                print(f"🔍 DEBUG: Found blocker message, updating with full blocker format")
                                # This is a blocker message, update it with current status
                                # Extract user info from the original text
                                import re
                                user_match = re.search(r'<@([^>]+)>', original_text)
                                user_id_from_msg = user_match.group(1) if user_match else user
                                
                                # Extract urgency from original text
                                urgency_match = re.search(r'🚨 \*Blocker Alert - ([^ ]+) ([^ ]+) Priority', original_text)
                                urgency_emoji = urgency_match.group(1) if urgency_match else '⚪'
                                urgency = urgency_match.group(2) if urgency_match else 'Unknown'
                                
                                # Extract other details from original text
                                description_match = re.search(r'\*\*Description:\*\* ([^\n]+)', original_text)
                                blocker_description = description_match.group(1) if description_match else 'Unknown'
                                
                                notes_match = re.search(r'\*\*Notes:\*\* ([^\n]+)', original_text)
                                notes = notes_match.group(1) if notes_match else 'None'
                                
                                # Get user name
                                try:
                                    user_info = self.client.users_info(user=user_id_from_msg)
                                    user_name = user_info['user']['real_name']
                                except:
                                    user_name = f"<@{user_id_from_msg}>"
                                
                                updated_blocks = [
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f"🚨 *Blocker Alert - {urgency_emoji} {urgency} Priority*\n\n"
                                                   f"<@{user_id_from_msg}> ({user_name}) is blocked and needs assistance!\n\n"
                                                   f"*Blocker Details:*\n"
                                                   f"• **Description:** {blocker_description}\n"
                                                   f"• **KR:** {kr_name}\n"
                                                   f"• **Urgency:** {urgency_emoji} {urgency}\n"
                                                   f"• **Notes:** {notes}\n"
                                                   f"• **Current KR Status:** {kr_status_info}\n\n"
                                                   f"Please reach out to help unblock this work! 💪"
                                        }
                                    },
                                    {
                                        "type": "actions",
                                        "elements": [
                                            {
                                                "type": "button",
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "I can help!",
                                                    "emoji": True
                                                },
                                                "value": f"help_{user_id_from_msg}",
                                                "action_id": "offer_help",
                                                "style": "primary"
                                            },
                                            {
                                                "type": "button",
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "📊 Check Status",
                                                    "emoji": True
                                                },
                                                "value": f"refresh_{safe_kr_name}",
                                                "action_id": "refresh_status"
                                            }
                                        ]
                                    }
                                ]
                                
                                # Check if the KR is completed and update message accordingly
                                if "completed" in kr_status_info.lower() or "done" in kr_status_info.lower():
                                    # KR is finished - show completion message but preserve blocker context
                                    completed_blocks = [
                                        {
                                            "type": "section",
                                            "text": {
                                                "type": "mrkdwn",
                                                "text": f"🎉 *KR Completed!*\n\n*{kr_name}* has been successfully completed!\n\n*Final Status:* {kr_status_info}\n\nGreat work! 🚀"
                                            }
                                        }
                                    ]
                                    
                                    self.client.chat_update(
                                        channel=channel_id,
                                        ts=message_ts,
                                        blocks=completed_blocks,
                                        text=f"🎉 {kr_name} completed!"
                                    )
                                    print(f"✅ KR '{kr_name}' detected as completed - showing completion message")
                                else:
                                    # KR is still in progress - preserve blocker alert and just update status
                                    # Keep the original blocker alert structure but update the status
                                    preserved_blocks = [
                                        {
                                            "type": "section",
                                            "text": {
                                                "type": "mrkdwn",
                                                "text": f"🚨 *Blocker Alert* - {urgency_emoji} {urgency} Priority\n<@{user_id_from_msg}> ({user_name}) is blocked and needs assistance!\n\n*Blocker Details:*\n• **Description:** {blocker_description}\n• **KR:** {kr_name}\n• **Urgency:** {urgency_emoji} {urgency}\n• **Notes:** {notes}\n• **Current KR Status:** {kr_status_info}"
                                            }
                                        },
                                        {
                                            "type": "actions",
                                            "elements": [
                                                {
                                                    "type": "button",
                                                    "text": {
                                                        "type": "plain_text",
                                                        "text": "🆘 I can help!",
                                                        "emoji": True
                                                    },
                                                    "value": f"help_{user_id_from_msg}",
                                                    "action_id": "offer_help",
                                                    "style": "primary"
                                                },
                                                {
                                                    "type": "button",
                                                    "text": {
                                                        "type": "plain_text",
                                                        "text": "📊 Check Status",
                                                        "emoji": True
                                                    },
                                                    "value": f"refresh_{safe_kr_name}",
                                                    "action_id": "refresh_status"
                                                }
                                            ]
                                        }
                                    ]
                                    
                                    self.client.chat_update(
                                        channel=channel_id,
                                        ts=message_ts,
                                        blocks=preserved_blocks,
                                        text=f"🚨 Blocker Alert: {user_name} needs help with {kr_name} - Status: {kr_status_info}"
                                    )
                                    print(f"✅ KR '{kr_name}' status refreshed while preserving blocker alert")
                            else:
                                print(f"🔍 DEBUG: Not a blocker message, using fallback status format")
                                # Fallback: just update with status info
                                status_blocks = [
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f"📊 *{kr_name}*\n*Status:* {kr_status_info}"
                                        }
                                    },
                                    {
                                        "type": "actions",
                                        "elements": [
                                            {
                                                "type": "button",
                                                "text": {
                                                    "type": "plain_text",
                                                    "text": "🔄 Refresh",
                                                    "emoji": True
                                                },
                                                "value": f"refresh_{safe_kr_name}",
                                                "action_id": "refresh_status"
                                            }
                                        ]
                                    }
                                ]
                                
                                self.client.chat_update(
                                    channel=channel_id,
                                    ts=message_ts,
                                    blocks=status_blocks,
                                    text=f"📊 {kr_name} status: {kr_status_info}"
                                )
                        else:
                            print(f"❌ Could not find original message to update")
                            # Send a simple status update message instead
                            self._send_simple_status_update(channel_id, message_ts, kr_name, kr_status_info, safe_kr_name)
                            
                    except Exception as update_error:
                        print(f"❌ Error updating status message: {update_error}")
                        # Send a simple status update message instead
                        self._send_simple_status_update(channel_id, message_ts, kr_name, kr_status_info, safe_kr_name)
                    
                    return {"response_action": "clear"}, 200
                else:
                    print(f"❌ Invalid refresh button value: {action}")
                    return {"response_action": "errors", "errors": ["Invalid refresh request"]}, 400
            
            # Handle mark resolved button (both channel and DM)
            elif action_id in ['mark_resolved', 'blocker_resolved']:
                # Handle mark resolved button click
                self.handle_mark_resolved_click(payload)
                return {"response_action": "clear"}, 200
            
            # Handle other blocker follow-up responses
            elif action_id in ['blocker_still_working', 'blocker_need_help']:
                # Handle 24-hour blocker follow-up responses
                self.handle_blocker_followup_response(user, action)
                return {"response_action": "clear"}, 200
            
            # Handle blocker claim functionality
            elif action_id == 'claim_blocker':
                # Parse the action value: claim_blocker_U0919MVQLLU_1752540423_U0919MVQLLU_alexanderchan486
                # Format: claim_blocker_{user_id}_{timestamp}_{user_id}_{user_name}
                # Need to reconstruct: blocker_{user_id}_{timestamp}
                parts = action.split('_')  # Split all parts
                if len(parts) >= 5:
                    # parts[0] = "claim"
                    # parts[1] = "blocker"
                    # parts[2] = "U0919MVQLLU" (user_id)
                    # parts[3] = "1752540423" (timestamp)
                    # parts[4] = "U0919MVQLLU" (user_id again)
                    # parts[5] = "alexanderchan486" (user_name)
                    
                    user_id = parts[2]
                    timestamp = parts[3]
                    user_name = parts[5]
                    
                    # Reconstruct the blocker_id: blocker_{user_id}_{timestamp}
                    blocker_id = f"blocker_{user_id}_{timestamp}"
                    
                    print(f"🔍 DEBUG: Parsing claim action - full action: {action}")
                    print(f"🔍 DEBUG: Parsing claim action - parts: {parts}")
                    print(f"🔍 DEBUG: Parsing claim action - reconstructed blocker_id: {blocker_id}, user_id: {user_id}, user_name: {user_name}")
                    
                    # Claim the blocker
                    self.claim_blocker(blocker_id, user, username, channel_id, message_ts)
                else:
                    print(f"❌ Invalid claim blocker action value: {action}")
                return {"response_action": "clear"}, 200
            
            # Handle view blocker details
            elif action_id == 'view_blocker_details':
                # Parse the action value: view_blocker_id
                parts = action.split('_', 1)
                if len(parts) >= 2:
                    blocker_id = parts[1]
                    self.view_blocker_details(blocker_id, channel_id, message_ts)
                else:
                    print(f"❌ Invalid view blocker action value: {action}")
                return {"response_action": "clear"}, 200
            
            # Handle update progress
            elif action_id == 'update_progress':
                # Parse the action value: progress_blocker_U0919MVQLLU_1752540700
                # Format: progress_blocker_{user_id}_{timestamp}
                parts = action.split('_', 2)
                if len(parts) >= 3:
                    # parts[0] = "progress"
                    # parts[1] = "blocker"
                    # parts[2] = "U0919MVQLLU_1752540700" (user_id_timestamp)
                    
                    # Extract user_id and timestamp from parts[2]
                    user_timestamp_parts = parts[2].split('_', 1)
                    if len(user_timestamp_parts) >= 2:
                        user_id = user_timestamp_parts[0]
                        timestamp = user_timestamp_parts[1]
                        
                        # Reconstruct the blocker_id: blocker_{user_id}_{timestamp}
                        blocker_id = f"blocker_{user_id}_{timestamp}"
                        
                        print(f"🔍 DEBUG: Parsing update progress action - full action: {action}")
                        print(f"🔍 DEBUG: Parsing update progress action - parts: {parts}")
                        print(f"🔍 DEBUG: Parsing update progress action - user_timestamp_parts: {user_timestamp_parts}")
                        print(f"🔍 DEBUG: Parsing update progress action - reconstructed blocker_id: {blocker_id}")
                        
                        # Show detailed view (same as view details)
                        self.view_blocker_details(blocker_id, channel_id, message_ts)
                    else:
                        print(f"❌ Invalid update progress action value format: {action}")
                else:
                    print(f"❌ Invalid update progress action value: {action}")
                return {"response_action": "clear"}, 200
            
            # Handle form input actions (static_select, plain_text_input, etc.)
            elif action_id in ['urgency_input', 'blocker_description_input', 'kr_name_input', 'notes_input', 'explanation_input']:
                # These are form input actions that don't need special handling
                # They are automatically handled by Slack's form system
                print(f"✅ Form input action received: {action_id}")
                return {"response_action": "clear"}, 200
            
            elif action_id == "mentor_yes":
                # Parse request_type and user_id from value
                value_parts = action.split("_", 3)
                if len(value_parts) >= 4:
                    _, _, request_type, user_id = value_parts
                    if request_type == "blocker":
                        # Open the blocker modal for submission (reuse escalate_help_request logic)
                        user_info = self.client.users_info(user=user_id)
                        user_name = user_info['user']['real_name']
                        user_data = {
                            'trigger_id': trigger_id,
                            'user_id': user_id,
                            'user_name': user_name,
                            'channel_id': channel_id,
                            'message_ts': message_ts
                        }
                        self.escalate_help_request(user_id, user_name, user_data)
                        return {"response_action": "clear"}, 200
                    # If this was a KR request, check for a pending search term
                    if request_type == "kr":
                        search_term = self.pending_kr_search.get(user_id)
                        if search_term:
                            # Show KR search results
                            matches = self.coda.search_kr_table(search_term)
                            if matches:
                                result_lines = []
                                for m in matches:
                                    kr_name = m.get('c-yQ1M6UqTSj', 'N/A')
                                    owner = m.get('c-efR-vVo_3w', 'N/A')
                                    status = m.get('c-cC29Yow8Gr', 'N/A')
                                    definition_of_done = m.get('c-P_mQJLObL0', '')
                                    link = m.get('link', None)
                                    explanation = generate_kr_explanation(kr_name, owner, status, definition_of_done)
                                    line = f"*KR*: {kr_name}\n*Owner*: {owner}\n*Status*: {status}\n*Definition of Done*: {definition_of_done}\n*AI Explanation*: {explanation}"
                                    if link:
                                        line += f"\n<Link|{link}>"
                                    result_lines.append(line)
                                result_text = '\n\n'.join(result_lines)
                            else:
                                result_text = f'No matching KRs found for "{search_term}".'
                            self.client.chat_postMessage(
                                channel=channel_id,
                                text=result_text
                            )
                            # Clear the pending search term
                            self.pending_kr_search[user_id] = None
                        else:
                            # No search term: prompt for KR
                            self.client.chat_postMessage(
                                channel=channel_id,
                                text="What KR would you like to search for? Type /kr [search term] or !kr [search term]"
                            )
                    # ... existing code for other request_types ...
            
            elif action_id == "mentor_no":
                self.handle_mentor_no_response(user, channel_id, message_ts)
                return {"response_action": "clear"}, 200
            
            else:
                print(f"❌ Unknown action_id: {action_id}")
                return {"response_action": "errors", "errors": ["Unknown action"]}, 400
                
        except Exception as e:
            print(f"❌ Error handling button click: {e}")
            return {"response_action": "errors", "errors": [str(e)]}, 500

    def get_thread_url(self, channel_id, thread_ts):
        """Generate a clickable thread URL."""
        # Convert timestamp to readable format
        ts_float = float(thread_ts)
        return f"https://slack.com/app_redirect?channel={channel_id}&message_ts={thread_ts}"
    
    def _send_simple_status_update(self, channel_id, message_ts, kr_name, kr_status_info, safe_kr_name):
        """Send a simple status update message when the original message can't be updated."""
        try:
            simple_status_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📊 *{kr_name}*\n*Status:* {kr_status_info}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🔄 Refresh",
                                "emoji": True
                            },
                            "value": f"refresh_{safe_kr_name}",
                            "action_id": "refresh_status"
                        }
                    ]
                }
            ]
            
            self.client.chat_update(
                channel=channel_id,
                ts=message_ts,
                blocks=simple_status_blocks,
                text=f"📊 {kr_name}: {kr_status_info}"
            )
            print(f"✅ KR '{kr_name}' status updated with simple message")
        except Exception as simple_error:
            print(f"❌ Error sending simple status update: {simple_error}")
    
    def get_kr_from_message(self, message):
        """Extract KR name from the blocker message."""
        try:
            # Look for KR in the message blocks
            if 'blocks' in message:
                for block in message['blocks']:
                    if block.get('type') == 'section' and 'text' in block:
                        text = block['text'].get('text', '')
                        # Look for KR pattern in the text
                        if '**KR:**' in text:
                            # Extract KR after "**KR:**"
                            kr_start = text.find('**KR:**') + 6
                            kr_end = text.find('\n', kr_start)
                            if kr_end == -1:
                                kr_end = len(text)
                            kr_name = text[kr_start:kr_end].strip()
                            return kr_name
                        elif 'KR:' in text:
                            # Extract KR after "KR:"
                            kr_start = text.find('KR:') + 3
                            kr_end = text.find('\n', kr_start)
                            if kr_end == -1:
                                kr_end = len(text)
                            kr_name = text[kr_start:kr_end].strip()
                            return kr_name
            return "Unknown KR"
        except Exception as e:
            print(f"❌ Error extracting KR from message: {e}")
            return "Unknown KR"

    def send_test_health_check(self):
        """Send a test health check message on startup."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ":wave: *Daily Health Check*\nHow are you feeling today?"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "action_id": "great",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":blush: Great",
                                    "emoji": True
                                },
                                "value": "great"
                            },
                            {
                                "type": "button",
                                "action_id": "okay",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":neutral_face: Okay",
                                    "emoji": True
                                },
                                "value": "okay"
                            },
                            {
                                "type": "button",
                                "action_id": "not_great",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":pensive: Not Great",
                                    "emoji": True
                                },
                                "value": "not_great"
                            }
                        ]
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                blocks=message["blocks"],
                text="Daily Health Check"
            )
            
            print(f"✅ Health check prompt sent successfully: {response['ts']}")
            return response['ts']
            
        except Exception as e:
            print(f"⚠️ Could not send health check prompt: {str(e)}")
            return None
            
    def send_test_standup(self):
        """Send a test standup message on startup."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Good morning team! :sun_with_face: Time for the daily standup!\nPlease reply to this thread with:\n\n1. What did you do today?\n2. Are you on track to meet your goals? (Yes/No)\n3. Do you have any blockers? (Yes/No)\n <!channel> please respond by 4:30 PM. Let's stay aligned! :speech_balloon:"
                        }
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                blocks=message["blocks"],
                text="Daily Standup"
            )
            
            print(f"✅ Standup prompt sent successfully: {response['ts']}")
            return response['ts']
            
        except Exception as e:
            print(f"⚠️ Could not send standup prompt: {str(e)}")
            return None

    def send_health_check_to_dm(self, user_id):
        """Send health check prompt to a specific user's DM."""
        try:
            print(f"🔍 DEBUG: Attempting to send health check to DM for user {user_id}")
            
            # First, try to open a DM with the user
            try:
                dm_response = self.client.conversations_open(users=[user_id])
                dm_channel = dm_response['channel']['id']
                print(f"🔍 DEBUG: Opened DM channel {dm_channel} for user {user_id}")
            except Exception as e:
                print(f"❌ Could not open DM with user {user_id}: {e}")
                return None
            
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ":wave: *Daily Health Check*\nHow are you feeling today?"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "action_id": "great",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":blush: Great",
                                    "emoji": True
                                },
                                "value": "great"
                            },
                            {
                                "type": "button",
                                "action_id": "okay",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":neutral_face: Okay",
                                    "emoji": True
                                },
                                "value": "okay"
                            },
                            {
                                "type": "button",
                                "action_id": "not_great",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":pensive: Not Great",
                                    "emoji": True
                                },
                                "value": "not_great"
                            }
                        ]
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=dm_channel,  # Use the DM channel ID
                blocks=message["blocks"],
                text="Daily Health Check"
            )
            
            print(f"✅ Health check prompt sent to DM for user {user_id}: {response['ts']}")
            return response['ts']
            
        except Exception as e:
            print(f"❌ Could not send health check prompt to DM for {user_id}: {str(e)}")
            return None

    def send_health_check_to_all_users(self, users=None):
        """Send health check prompts to all team members via DM."""
        try:
            # Check if health check has already been sent today
            if self.daily_prompts_sent['health_check']:
                print("⚠️ Health check prompts already sent today, skipping...")
                return 0
                
            # Get list of all users in the workspace if not provided
            if users is None:
                print("🔍 DEBUG: Getting list of all users for health check...")
                users_response = self.client.users_list()
                users = users_response['members']
                print(f"🔍 DEBUG: Found {len(users)} total users")
            else:
                print(f"🔍 DEBUG: Using provided user list with {len(users)} users for health check")
            
            sent_count = 0
            for user in users:
                user_id = user.get('id')
                user_name = user.get('name', 'unknown')
                
                print(f"🔍 DEBUG: Processing user {user_name} ({user_id})")
                
                # Skip bots and deleted users
                if user.get('is_bot') or user.get('deleted'):
                    print(f"🔍 DEBUG: Skipping bot/deleted user {user_name}")
                    continue
                
                # Skip the bot itself
                if user_id == 'U0912DJRNSF':  # bot user ID
                    print(f"🔍 DEBUG: Skipping bot user {user_name}")
                    continue
                
                # Skip users who are not active
                if user.get('is_restricted') or user.get('is_ultra_restricted'):
                    print(f"🔍 DEBUG: Skipping restricted user {user_name}")
                    continue
                
                # Send health check to each user's DM
                result = self.send_health_check_to_dm(user_id)
                if result:
                    sent_count += 1
                    print(f"✅ Successfully sent health check to {user_name}")
                else:
                    print(f"❌ Failed to send health check to {user_name}")
                
                # Small delay to avoid rate limiting
                time.sleep(0.5)
            
            print(f"✅ Health check prompts sent to {sent_count} users via DM")
            self.daily_prompts_sent['health_check'] = True
            return sent_count
            
        except Exception as e:
            print(f"❌ Error sending health checks to all users: {e}")
            return 0

    def reset_daily_prompts(self):
        """Reset daily prompt flags."""
        self.daily_prompts_sent = {
            'standup': False,
            'health_check': False
        }
        # Also clear follow-up tracking to ensure fresh start
        self.last_followup_sent = {}
        print("✅ Daily prompts and follow-up tracking reset")
    
    def clear_followup_tracking(self):
        """Clear the follow-up tracking to force fresh follow-ups."""
        self.last_followup_sent = {}
        print("✅ Follow-up tracking cleared")

    def send_info_message(self, channel_id, user_id, mode="user"):
        """Send an info/help message to guide users on how to interact with the bot."""
        try:
            if mode == "admin":
                message = {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "*Admin/Role Management Commands:*\n"
                                    "• `/role [user] [role]` — Assign a role to a user\n"
                                    "• `/roles` — List all roles\n"
                                    "• `/role remove [user] [role]` — Remove a role\n"
                                    "• `/role users [role]` — List users by role\n"
                                    "• `/help admin` — Show this admin help\n"
                                )
                            }
                        }
                    ]
                }
            else:
                message = {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "*User Commands:*\n"
                                    "• `/checkin` — Start your daily standup\n"
                                    "• `/health` — Send a health check prompt\n"
                                    "• `/kr [search]` — Search for a Key Result\n"
                                    "• `/blocker` — Escalate a blocker\n"
                                    "• `/help` — Show this help message\n"
                                    "\nFor more commands, try `/help admin` (admins only)."
                                )
                            }
                        }
                    ]
                }
            self.client.chat_postMessage(channel=channel_id, blocks=message["blocks"])
        except Exception as e:
            print(f"❌ Error sending info message: {e}")

    def send_standup_to_dm(self, user_id):
        """Send standup prompt to a specific user's DM."""
        try:
            print(f"🔍 DEBUG: Attempting to send standup to DM for user {user_id}")
            
            # First, try to open a DM with the user
            try:
                dm_response = self.client.conversations_open(users=[user_id])
                dm_channel = dm_response['channel']['id']
                print(f"🔍 DEBUG: Opened DM channel {dm_channel} for user {user_id}")
            except Exception as e:
                print(f"❌ Could not open DM with user {user_id}: {e}")
                return None
            
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Good morning! :sun_with_face: Time for the daily standup!\n\nPlease reply to this message with:\n\n1. **What did you do today?**\n2. **Are you on track to meet your goals?** (Yes/No)\n3. **Do you have any blockers?** (Yes/No)\n\nPlease respond by 4:30 PM. Let's stay aligned! :speech_balloon:"
                        }
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=dm_channel,
                blocks=message["blocks"],
                text="Daily Standup"
            )
            
            print(f"✅ Standup prompt sent to DM for user {user_id}: {response['ts']}")
            return response['ts']
            
        except Exception as e:
            print(f"❌ Could not send standup prompt to DM for {user_id}: {str(e)}")
            return None

    def send_standup_to_all_users(self, users=None):
        """Send standup prompts to all team members via DM."""
        try:
            # Check if standup has already been sent today
            if self.daily_prompts_sent['standup']:
                print("⚠️ Standup prompts already sent today, skipping...")
                return 0
                
            # Get list of all users in the workspace if not provided
            if users is None:
                print("🔍 DEBUG: Getting list of all users for standup...")
                users_response = self.client.users_list()
                users = users_response['members']
                print(f"🔍 DEBUG: Found {len(users)} total users")
            else:
                print(f"🔍 DEBUG: Using provided user list with {len(users)} users for standup")
            
            sent_count = 0
            for user in users:
                user_id = user.get('id')
                user_name = user.get('name', 'unknown')
                
                print(f"🔍 DEBUG: Processing user {user_name} ({user_id}) for standup")
                
                # Skip bots and deleted users
                if user.get('is_bot') or user.get('deleted'):
                    print(f"🔍 DEBUG: Skipping bot/deleted user {user_name}")
                    continue
                
                # Skip the bot itself
                if user_id == 'U0912DJRNSF':  # bot user ID
                    print(f"🔍 DEBUG: Skipping bot user {user_name}")
                    continue
                
                # Skip users who are not active
                if user.get('is_restricted') or user.get('is_ultra_restricted'):
                    print(f"🔍 DEBUG: Skipping restricted user {user_name}")
                    continue
                
                # Send standup to each user's DM
                result = self.send_standup_to_dm(user_id)
                if result:
                    sent_count += 1
                    print(f"✅ Successfully sent standup to {user_name}")
                else:
                    print(f"❌ Failed to send standup to {user_name}")
                
                # Small delay to avoid rate limiting
                time.sleep(0.5)
            
            print(f"✅ Standup prompts sent to {sent_count} users via DM")
            self.daily_prompts_sent['standup'] = True
            return sent_count
            
        except Exception as e:
            print(f"❌ Error sending standups to all users: {e}")
            return 0

    def handle_commands(self, user_id, text, channel_id):
        """Handle slash commands (/) from users. Suggest /help for unrecognized commands in DMs."""
        try:
            text_lower = text.lower().strip()
            # Only handle slash commands
            if text_lower.startswith('/'):
                command = text_lower[1:].split()[0]  # Get the command part
                return self._process_command(user_id, command, text, channel_id)
            # If user tries !help or similar, suggest using /help
            elif text_lower.startswith('!help') or text_lower.startswith('help'):
                self.client.chat_postMessage(
                    channel=channel_id,
                    text="Try /help for a list of commands."
                )
                return True
            # For any other message in a DM, suggest /help
            if channel_id and channel_id.startswith('D'):
                self.client.chat_postMessage(
                    channel=channel_id,
                    text="Try /help for a list of commands."
                )
                return True
            return False  # Not a command
        except Exception as e:
            print(f"❌ Error handling command: {e}")
            return False
    
    def _process_command(self, user_id, command, full_text, channel_id):
        """Process individual commands."""
        try:
            # Get user info for name
            user_info = self.client.users_info(user=user_id)
            user_name = user_info['user']['real_name']
            
            if command in ['checkin', 'standup', 'status']:
                print(f"🔍 DEBUG: Processing checkin command from {user_name}")
                # Send standup prompt to the user
                self.send_standup_to_dm(user_id)
                return True
                
            elif command in ['blocked', 'help', 'stuck']:
                print(f"🔍 DEBUG: Processing blocked/help command from {user_name}")
                # Send mentor check first
                self.send_mentor_check(
                    user_id=user_id,
                    standup_ts=full_text,  # Use full text as timestamp placeholder
                    user_name=user_name,
                    request_type="blocker",
                    channel=channel_id
                )
                return True
                
            elif command in ['kr', 'keyresult', 'keyresults']:
                print(f"🔍 DEBUG: Processing KR search command from {user_name}")
                # Extract search term (everything after the command)
                parts = full_text.strip().split(' ', 1)
                search_term = parts[1].strip() if len(parts) > 1 else ""
                if search_term:
                    # Direct KR search - no mentor check needed for specific searches
                    matches = self.coda.search_kr_table(search_term)
                    if matches:
                        result_lines = []
                        for m in matches:
                            kr_name = m.get('c-yQ1M6UqTSj', 'N/A')
                            owner = m.get('c-efR-vVo_3w', 'N/A')
                            status = m.get('c-cC29Yow8Gr', 'N/A')
                            definition_of_done = m.get('c-P_mQJLObL0', '')
                            link = m.get('link', None)
                            explanation = generate_kr_explanation(kr_name, owner, status, definition_of_done)
                            line = f"*KR*: {kr_name}\n*Owner*: {owner}\n*Status*: {status}\n*Definition of Done*: {definition_of_done}\n*AI Explanation*: {explanation}"
                            if link:
                                line += f"\n<Link|{link}>"
                            result_lines.append(line)
                        result_text = '\n\n'.join(result_lines)
                    else:
                        result_text = f'No matching KRs found for "{search_term}".'
                    self.client.chat_postMessage(
                        channel=channel_id,
                        text=result_text
                    )
                else:
                    # No search term provided - send mentor check for KR clarification request
                    self.send_mentor_check(
                        user_id=user_id,
                        standup_ts=full_text,  # Use full text as timestamp placeholder
                        user_name=user_name,
                        request_type="kr",
                        channel=channel_id
                    )
                return True
                
            elif command in ['help', 'commands', 'info']:
                print(f"🔍 DEBUG: Processing help command from {user_name}")
                # Check for admin help
                if full_text.strip().lower() in ['/help admin', '!help admin', 'help admin', 'commands admin', 'info admin']:
                    if self.has_role(user_id, 'admin'):
                        self.send_info_message(channel_id, user_id, mode="admin")
                    else:
                        self.client.chat_postMessage(
                            channel=channel_id,
                            text="❌ You need admin privileges to view admin/role management commands."
                        )
                    return True
                # Otherwise, show user help
                self.send_info_message(channel_id, user_id, mode="user")
                return True
                
            elif command in ['health', 'mood', 'feeling']:
                print(f"🔍 DEBUG: Processing health check command from {user_name}")
                # Send health check prompt
                self.send_health_check_to_dm(user_id)
                return True
                
            elif command in ['role', 'roles']:
                print(f"🔍 DEBUG: Processing role command from {user_name}")
                # Handle role management
                return self._handle_role_command(user_id, full_text, channel_id)
            else:
                # Unknown command - send help
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"Unknown command: `{command}`\n\nType `/help` or `!help` to see available commands."
                )
                return True
                
        except Exception as e:
            print(f"❌ Error processing command {command}: {e}")
            return False

    def _handle_role_command(self, user_id, full_text, channel_id):
        """Handle role management commands."""
        try:
            # Check if user has admin role
            if not self.has_role(user_id, 'admin'):
                self.client.chat_postMessage(
                    channel=channel_id,
                    text="❌ You need admin privileges to manage roles."
                )
                return True
            
            parts = full_text.split()
            if len(parts) < 2:
                # Show role help
                help_text = """*Role Management Commands:*
• `/rolelist` - List all roles and users
• `/role add @user role` - Add role to user
• `/role remove @user role` - Remove role from user
• `/role users role` - List users with specific role
• `/role channels` - List role-based channels

*Available Roles:* pm, lead, developer, designer, qa, devops, sm, admin"""
                self.client.chat_postMessage(channel=channel_id, text=help_text)
                return True
            
            subcommand = parts[1].lower()
            
            if subcommand == 'list':
                return self._list_all_roles(channel_id)
            elif subcommand == 'add' and len(parts) >= 4:
                return self._add_user_role(parts[2], parts[3], channel_id)
            elif subcommand == 'add' and len(parts) == 3:
                # Show interactive role selector when user types "/role add @user"
                return self._show_interactive_role_selector(channel_id, parts[2], 'add')
            elif subcommand == 'remove' and len(parts) >= 4:
                return self._remove_user_role(parts[2], parts[3], channel_id)
            elif subcommand == 'remove' and len(parts) == 3:
                # Show interactive role selector when user types "/role remove @user"
                return self._show_interactive_role_selector(channel_id, parts[2], 'remove')
            elif subcommand == 'users' and len(parts) >= 3:
                return self._list_users_by_role(parts[2], channel_id)
            elif subcommand == 'users' and len(parts) == 2:
                # Show interactive role selector when user types "/role users"
                return self._show_interactive_role_selector(channel_id, None, 'users')
            elif subcommand == 'channels':
                return self._list_role_channels(channel_id)
            else:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text="❌ Invalid role command. Use `/role` for help."
                )
                return True
                
        except Exception as e:
            print(f"❌ Error handling role command: {e}")
            return False
    
    def _list_all_roles(self, channel_id):
        """List all roles and users."""
        try:
            role_text = "*Current Role Assignments:*\n\n"
            
            for user_id, roles in self.user_roles.items():
                if roles:  # Only show users with roles
                    try:
                        user_info = self.client.users_info(user=user_id)
                        user_name = user_info['user']['real_name']
                        role_text += f"• <@{user_id}> ({user_name}): {', '.join(roles)}\n"
                    except:
                        role_text += f"• <@{user_id}>: {', '.join(roles)}\n"
            
            if not any(self.user_roles.values()):
                role_text += "No role assignments found."
            
            self.client.chat_postMessage(channel=channel_id, text=role_text)
            return True
        except Exception as e:
            print(f"❌ Error listing roles: {e}")
            return False
    
    def _add_user_role(self, user_mention, role, channel_id):
        """Add a role to a user."""
        try:
            # Extract user ID from mention - handle both @username and <@USER_ID> formats
            user_id = None
            
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                # Slack format: <@USER_ID>
                user_id = user_mention[2:-1]  # Remove <@ and >
                if '|' in user_id:
                    user_id = user_id.split('|')[0]  # Handle bot mentions
            elif user_mention.startswith('@'):
                # Username format: @username
                username = user_mention[1:]  # Remove @
                # Try to find user by username
                try:
                    users_response = self.client.users_list()
                    for user in users_response['members']:
                        if user.get('name') == username or user.get('real_name', '').lower().replace(' ', '') == username.lower().replace(' ', ''):
                            user_id = user['id']
                            break
                    
                    if not user_id:
                        self.client.chat_postMessage(
                            channel=channel_id,
                            text=f"❌ User '@{username}' not found. Please use the exact username or mention them with @."
                        )
                        return True
                except Exception as e:
                    print(f"❌ Error looking up user by username: {e}")
                    self.client.chat_postMessage(
                        channel=channel_id,
                        text="❌ Error looking up user. Please try using their full Slack mention."
                    )
                    return True
            else:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text="❌ Please mention a user with @username or use their Slack mention"
                )
                return True
            
            # Validate role
            valid_roles = ['pm', 'lead', 'developer', 'designer', 'qa', 'devops', 'sm', 'admin']
            if role.lower() not in valid_roles:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"❌ Invalid role. Valid roles: {', '.join(valid_roles)}"
                )
                return True
            
            # Add role
            if user_id not in self.user_roles:
                self.user_roles[user_id] = []
            
            if role.lower() not in self.user_roles[user_id]:
                self.user_roles[user_id].append(role.lower())
                
                try:
                    user_info = self.client.users_info(user=user_id)
                    user_name = user_info['user']['real_name']
                    self.client.chat_postMessage(
                        channel=channel_id,
                        text=f"✅ Added role '{role}' to {user_name} (<@{user_id}>)"
                    )
                except:
                    self.client.chat_postMessage(
                        channel=channel_id,
                        text=f"✅ Added role '{role}' to <@{user_id}>"
                    )
            else:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"⚠️ User already has role '{role}'"
                )
            
            return True
        except Exception as e:
            print(f"❌ Error adding user role: {e}")
            return False
    
    def _remove_user_role(self, user_mention, role, channel_id):
        """Remove a role from a user."""
        try:
            # Extract user ID from mention - handle both @username and <@USER_ID> formats
            user_id = None
            
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                # Slack format: <@USER_ID>
                user_id = user_mention[2:-1]  # Remove <@ and >
                if '|' in user_id:
                    user_id = user_id.split('|')[0]  # Handle bot mentions
            elif user_mention.startswith('@'):
                # Username format: @username
                username = user_mention[1:]  # Remove @
                # Try to find user by username
                try:
                    users_response = self.client.users_list()
                    for user in users_response['members']:
                        if user.get('name') == username or user.get('real_name', '').lower().replace(' ', '') == username.lower().replace(' ', ''):
                            user_id = user['id']
                            break
                    
                    if not user_id:
                        self.client.chat_postMessage(
                            channel=channel_id,
                            text=f"❌ User '@{username}' not found. Please use the exact username or mention them with @."
                        )
                        return True
                except Exception as e:
                    print(f"❌ Error looking up user by username: {e}")
                    self.client.chat_postMessage(
                        channel=channel_id,
                        text="❌ Error looking up user. Please try using their full Slack mention."
                    )
                    return True
            else:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text="❌ Please mention a user with @username or use their Slack mention"
                )
                return True
            
            # Remove role
            if user_id in self.user_roles and role.lower() in self.user_roles[user_id]:
                self.user_roles[user_id].remove(role.lower())
                
                # Remove user if no roles left
                if not self.user_roles[user_id]:
                    del self.user_roles[user_id]
                
                try:
                    user_info = self.client.users_info(user=user_id)
                    user_name = user_info['user']['real_name']
                    self.client.chat_postMessage(
                        channel=channel_id,
                        text=f"✅ Removed role '{role}' from {user_name} (<@{user_id}>)"
                    )
                except:
                    self.client.chat_postMessage(
                        channel=channel_id,
                        text=f"✅ Removed role '{role}' from <@{user_id}>"
                    )
            else:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"⚠️ User doesn't have role '{role}'"
                )
            
            return True
        except Exception as e:
            print(f"❌ Error removing user role: {e}")
            return False
    
    def _list_users_by_role(self, role, channel_id):
        """List users with a specific role."""
        try:
            users = self.get_users_by_role(role.lower())
            
            if users:
                user_list = []
                for user_id in users:
                    try:
                        user_info = self.client.users_info(user=user_id)
                        user_name = user_info['user']['real_name']
                        user_list.append(f"• <@{user_id}> ({user_name})")
                    except:
                        user_list.append(f"• <@{user_id}>")
                
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"*Users with role '{role}':*\n" + "\n".join(user_list)
                )
            else:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"No users found with role '{role}'"
                )
            
            return True
        except Exception as e:
            print(f"❌ Error listing users by role: {e}")
            return False
    
    def _list_role_channels(self, channel_id):
        """List role-based channel mappings."""
        try:
            channel_text = "*Role-Based Channel Mappings:*\n\n"
            
            for role, channel in self.role_channels.items():
                channel_text += f"• {role.title()}: #{channel}\n"
            
            self.client.chat_postMessage(channel=channel_id, text=channel_text)
            return True
        except Exception as e:
            print(f"❌ Error listing role channels: {e}")
            return False
    
    def _show_role_suggestions(self, channel_id):
        """Show available roles for autocomplete."""
        try:
            valid_roles = ['pm', 'lead', 'developer', 'designer', 'qa', 'devops', 'sm', 'admin']
            
            suggestions_text = "*Available Roles:*\n\n"
            for role in valid_roles:
                # Show current users with this role
                users_with_role = self.get_users_by_role(role)
                if users_with_role:
                    user_names = []
                    for user_id in users_with_role:
                        try:
                            user_info = self.client.users_info(user=user_id)
                            user_names.append(user_info['user']['real_name'])
                        except:
                            user_names.append(f"<@{user_id}>")
                    suggestions_text += f"• `{role}` - Currently assigned to: {', '.join(user_names)}\n"
                else:
                    suggestions_text += f"• `{role}` - No users assigned\n"
            
            suggestions_text += "\n*Usage Examples:*\n"
            suggestions_text += "• `/role add @username pm` - Add PM role\n"
            suggestions_text += "• `/role remove @username lead` - Remove lead role\n"
            suggestions_text += "• `/role users developer` - List all developers\n"
            
            self.client.chat_postMessage(channel=channel_id, text=suggestions_text)
            return True
        except Exception as e:
            print(f"❌ Error showing role suggestions: {e}")
            return False
    
    def _show_interactive_role_selector(self, channel_id, user_mention, action_type):
        """Show interactive dropdown to select roles."""
        try:
            valid_roles = ['pm', 'lead', 'developer', 'designer', 'qa', 'devops', 'sm', 'admin']
            
            # Create dropdown options
            options = []
            for role in valid_roles:
                # Show current users with this role
                users_with_role = self.get_users_by_role(role)
                if users_with_role:
                    user_names = []
                    for user_id in users_with_role:
                        try:
                            user_info = self.client.users_info(user=user_id)
                            user_names.append(user_info['user']['real_name'])
                        except:
                            user_names.append(f"<@{user_id}>")
                    label = f"{role.title()} ({', '.join(user_names)})"
                else:
                    label = f"{role.title()} (No users assigned)"
                
                options.append({
                    "text": {
                        "type": "plain_text",
                        "text": label,
                        "emoji": True
                    },
                    "value": f"{action_type}_{role}_{user_mention or 'none'}"
                })
            
            # Create message based on action type
            if action_type == 'add':
                title = f"Select role to add to {user_mention}:"
            elif action_type == 'remove':
                title = f"Select role to remove from {user_mention}:"
            else:  # users
                title = "Select role to list users:"
            
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{title}*"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "static_select",
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "Choose a role...",
                                    "emoji": True
                                },
                                "options": options,
                                "action_id": "role_selector"
                            }
                        ]
                    }
                ]
            }
            
            self.client.chat_postMessage(
                channel=channel_id,
                blocks=message["blocks"],
                text=f"Role selector: {title}"
            )
            return True
        except Exception as e:
            print(f"❌ Error showing interactive role selector: {e}")
            return False

    def track_blocker_for_followup(self, user_id, user_name, blocker_description, kr_name, urgency, notes, escalation_ts, channel_id=None, message_ts=None):
        """Track a blocker for automatic 24-hour follow-up, now with channel/message for deletion."""
        try:
            ts_int = int(float(escalation_ts))
            blocker_id = f"blocker_{user_id}_{ts_int}"
            blocker_info = {
                'blocker_id': blocker_id,
                'user_id': user_id,
                'user_name': user_name,
                'blocker_description': blocker_description,
                'kr_name': kr_name,
                'urgency': urgency,
                'notes': notes,
                'escalation_ts': escalation_ts,
                'escalation_time': datetime.fromtimestamp(float(escalation_ts)),
                'status': 'open',
                'followup_sent': False,
                'resolved': False,
                'channel_id': channel_id,
                'message_ts': message_ts
            }
            if not hasattr(self, 'tracked_blockers'):
                self.tracked_blockers = {}
            self.tracked_blockers[blocker_id] = blocker_info
            print(f"✅ Blocker tracked for follow-up: {blocker_id}")
            print(f"   User: {user_name}")
            print(f"   KR: {kr_name}")
            print(f"   Escalation time: {blocker_info['escalation_time']}")
            print(f"   Channel: {channel_id}, Message TS: {message_ts}")
            return blocker_id
        except Exception as e:
            print(f"❌ Error tracking blocker for follow-up: {e}")
            return None

    def check_blocker_followups(self):
        try:
            if not hasattr(self, 'last_followup_sent'):
                self.last_followup_sent = {}
            if not hasattr(self, 'tracked_blockers'):
                print("🔍 DEBUG: No tracked_blockers attribute found")
            else:
                print(f"🔍 DEBUG: Checking {len(self.tracked_blockers)} tracked blockers")
                now = datetime.now()
                blockers_to_followup = []
                for blocker_id, blocker_info in self.tracked_blockers.items():
                    print(f"🔍 DEBUG: Checking blocker {blocker_id}")
                    if blocker_info.get('resolved', False) or blocker_info.get('followup_sent', False):
                        print(f"🔍 DEBUG: Blocker {blocker_id} already resolved or followup sent")
                        continue
                    # 24-hour follow-up logic
                    if (now - blocker_info['escalation_time']).total_seconds() >= self.BLOCKER_FOLLOWUP_DELAY_HOURS * 3600:
                        blockers_to_followup.append(blocker_info)
                print(f"🔍 DEBUG: Found {len(blockers_to_followup)} blockers needing follow-up")
                for blocker_info in blockers_to_followup:
                    user_id = blocker_info['user_id']
                    if user_id in self.last_followup_sent:
                        last_sent = self.last_followup_sent[user_id]
                        time_since_last = now - last_sent
                        # Prevent duplicate follow-ups within the delay window
                        if time_since_last.total_seconds() < self.BLOCKER_FOLLOWUP_DELAY_HOURS * 3600:
                            continue
                    print(f"🔍 DEBUG: Sending follow-up for blocker {blocker_info['blocker_id']}")
                    self.send_blocker_followup(blocker_info)
                    blocker_info['followup_sent'] = True
                    self.last_followup_sent[user_id] = now
        except Exception as e:
            print(f"Error in check_blocker_followups: {e}")

    def send_blocker_followup(self, blocker_info):
        """Send 24-hour follow-up message for a blocker."""
        try:
            user_id = blocker_info['user_id']
            user_name = blocker_info['user_name']
            blocker_description = blocker_info['blocker_description']
            kr_name = blocker_info['kr_name']
            urgency = blocker_info['urgency']
            notes = blocker_info['notes']
            
            # Get KR details to find PM, lead, or assigned resolver
            pm_lead_resolver = self.get_kr_assignees(kr_name)
            
            # Format urgency with emoji
            urgency_emoji = {
                'Low': '🟢',
                'Medium': '🟡', 
                'High': '🟠',
                'Critical': '🔴'
            }.get(urgency, '⚪')
            
            # Create follow-up message
            followup_text = f"⏰ *24-Hour Blocker Follow-up*\n\n"
            followup_text += f"<@{user_id}>, it's been 24 hours since you reported this blocker:\n\n"
            followup_text += f"*Blocker Details:*\n"
            followup_text += f"• **Description:** {blocker_description}\n"
            followup_text += f"• **KR:** {kr_name}\n"
            followup_text += f"• **Urgency:** {urgency_emoji} {urgency}\n"
            followup_text += f"• **Notes:** {notes if notes else 'None'}\n\n"
            
            if pm_lead_resolver:
                followup_text += f"*Assigned Team:* {pm_lead_resolver}\n\n"
            
            followup_text += f"**Please update us on the status:**\n"
            followup_text += f"• Is this blocker still active?\n"
            followup_text += f"• Have you made progress?\n"
            followup_text += f"• Do you need additional help?\n\n"
            followup_text += f"React with:\n"
            followup_text += f"• ✅ = Resolved\n"
            followup_text += f"• 🔄 = Still working on it\n"
            followup_text += f"• 🆘 = Need more help"
            
            # Send to the person who reported the blocker
            try:
                dm_response = self.client.conversations_open(users=[user_id])
                dm_channel = dm_response['channel']['id']
                
                message = {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": followup_text
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "✅ Resolved",
                                        "emoji": True
                                    },
                                    "value": f"resolved_{blocker_info['blocker_id']}",
                                    "action_id": "blocker_resolved",
                                    "style": "primary"
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🔄 Still Working",
                                        "emoji": True
                                    },
                                    "value": f"still_working_{blocker_info['blocker_id']}",
                                    "action_id": "blocker_still_working"
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🆘 Need More Help",
                                        "emoji": True
                                    },
                                    "value": f"need_help_{blocker_info['blocker_id']}",
                                    "action_id": "blocker_need_help",
                                    "style": "danger"
                                }
                            ]
                        }
                    ]
                }
                
                response = self.client.chat_postMessage(
                    channel=dm_channel,
                    blocks=message["blocks"],
                    text=f"⏰ 24-Hour Blocker Follow-up: {kr_name}"
                )
                
                print(f"✅ 24-hour follow-up sent to {user_name} for blocker: {kr_name}")
                
                # Mark followup as sent
                blocker_info['followup_sent'] = True
                blocker_info['followup_ts'] = response['ts']
                
                # Store original channel/message for deletion in followup info
                if 'channel_id' not in blocker_info or not blocker_info['channel_id']:
                    # Try to get from active_blockers
                    ab = self.active_blockers.get(blocker_info['blocker_id']) if hasattr(self, 'active_blockers') else None
                    if ab:
                        blocker_info['channel_id'] = ab.get('channel_id')
                        blocker_info['message_ts'] = ab.get('message_ts')
            except Exception as e:
                print(f"❌ Error sending DM follow-up to {user_name}: {e}")
            
            # Also send to escalation channel to tag PMs/leads
            escalation_message = f"⏰ *24-Hour Blocker Follow-up Alert*\n\n"
            escalation_message += f"<@{user_id}> ({user_name}) reported a blocker 24 hours ago that may need attention:\n\n"
            escalation_message += f"*Blocker:* {blocker_description}\n"
            escalation_message += f"*KR:* {kr_name}\n"
            escalation_message += f"*Urgency:* {urgency_emoji} {urgency}\n\n"
            
            if pm_lead_resolver:
                escalation_message += f"*Assigned Team:* {pm_lead_resolver}\n\n"
            
            escalation_message += f"Please check in with <@{user_id}> to ensure they have the support they need."
            
            # Send to escalation channel
            escalation_channel = getattr(self.config, 'SLACK_ESCALATION_CHANNEL', 'general')
            self.client.chat_postMessage(
                channel=f"#{escalation_channel}",
                text=escalation_message
            )
            
            print(f"✅ Escalation channel notified about 24-hour follow-up for {user_name}")
            
            # Also send DM to all users with 'sm' (Scrum Master) role
            sm_users = self.get_users_by_role('sm')
            if sm_users:
                sm_message = f"⏰ *24-Hour Blocker Follow-up - Scrum Master Alert*\n\n"
                sm_message += f"<@{user_id}> ({user_name}) reported a blocker 24 hours ago:\n\n"
                sm_message += f"*Blocker:* {blocker_description}\n"
                sm_message += f"*KR:* {kr_name}\n"
                sm_message += f"*Urgency:* {urgency_emoji} {urgency}\n\n"
                sm_message += f"Please check in with <@{user_id}> to ensure they have the support they need."
                
                for sm_user_id in sm_users:
                    try:
                        self.client.chat_postMessage(
                            channel=sm_user_id,
                            text=sm_message
                        )
                        print(f"✅ 24-hour blocker follow-up sent to SM user {sm_user_id}")
                    except Exception as e:
                        print(f"❌ Error sending DM to SM user {sm_user_id}: {e}")
            else:
                print(f"⚠️ No users found with 'sm' role for blocker follow-up")
            
        except Exception as e:
            print(f"❌ Error sending blocker follow-up: {e}")

    def get_user_roles(self, user_id):
        """Get roles for a specific user."""
        return self.user_roles.get(user_id, [])
    
    def get_users_by_role(self, role):
        """Get all users with a specific role."""
        users = []
        for user_id, roles in self.user_roles.items():
            if role in roles:
                users.append(user_id)
        return users
    
    def has_role(self, user_id, role):
        """Check if a user has a specific role."""
        return role in self.user_roles.get(user_id, [])
    
    def send_role_based_message(self, role, message, channel_override=None):
        """Send a message to all users with a specific role."""
        users = self.get_users_by_role(role)
        if not users:
            print(f"⚠️ No users found with role: {role}")
            return False
        
        channel = channel_override or self.role_channels.get(role, 'general')
        
        # Send to role-specific channel if it exists
        try:
            self.client.chat_postMessage(
                channel=f"#{channel}",
                text=message
            )
            print(f"✅ Sent role-based message to {role} channel: #{channel}")
        except Exception as e:
            print(f"❌ Error sending to role channel {channel}: {e}")
            # Fallback to general channel
            try:
                self.client.chat_postMessage(
                    channel="#general",
                    text=f"*[{role.upper()}] {message}*"
                )
                print(f"✅ Sent role-based message to general channel as fallback")
            except Exception as fallback_error:
                print(f"❌ Error sending fallback message: {fallback_error}")
                return False
        
        # Also DM users with this role
        for user_id in users:
            try:
                self.client.chat_postMessage(
                    channel=user_id,
                    text=f"*[{role.upper()}] {message}*"
                )
                print(f"✅ Sent role-based DM to user {user_id}")
            except Exception as e:
                print(f"❌ Error sending DM to user {user_id}: {e}")
        
        return True
    
    def escalate_by_hierarchy(self, issue_type, message, additional_context=""):
        """Escalate an issue through the role hierarchy."""
        hierarchy = self.escalation_hierarchy.get(issue_type, ['pm'])
        
        escalation_message = f"🚨 *{issue_type.upper()} ESCALATION*\n\n{message}"
        if additional_context:
            escalation_message += f"\n\n*Additional Context:*\n{additional_context}"
        
        # Try each role in the hierarchy
        for role in hierarchy:
            users = self.get_users_by_role(role)
            if users:
                channel = self.role_channels.get(role, 'general')
                try:
                    # Tag users with this role
                    user_mentions = " ".join([f"<@{user_id}>" for user_id in users])
                    full_message = f"{escalation_message}\n\n*Escalated to:* {user_mentions}"
                    
                    self.client.chat_postMessage(
                        channel=f"#{channel}",
                        text=full_message
                    )
                    print(f"✅ Escalated {issue_type} to {role} role in #{channel}")
                    return True
                except Exception as e:
                    print(f"❌ Error escalating to {role}: {e}")
                    continue
        
        # If no roles found, send to general channel
        try:
            self.client.chat_postMessage(
                channel="#general",
                text=f"{escalation_message}\n\n*No specific role found - please review*"
            )
            print(f"✅ Escalated {issue_type} to general channel as fallback")
            return True
        except Exception as e:
            print(f"❌ Error sending fallback escalation: {e}")
            return False
    
    def get_kr_assignees(self, kr_name):
        """Get PM, lead, or assigned resolver for a KR from Coda."""
        try:
            if not self.coda or not kr_name:
                return None
            
            kr_details = self.coda.get_kr_details(kr_name)
            if not kr_details:
                return None
            
            # Look for assignee fields (adjust column names based on your Coda table)
            assignee_fields = ['helper', 'owner', 'pm', 'lead', 'assignee', 'responsible']
            assignees = []
            
            for field in assignee_fields:
                if field in kr_details and kr_details[field]:
                    assignees.append(kr_details[field])
            
            if assignees:
                return ", ".join(assignees)
            else:
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR assignees: {e}")
            return None

    def handle_mark_resolved_click(self, payload):
        """Handle mark resolved button click - opens resolution modal for channel, direct resolve for DM."""
        try:
            user = payload['user']['id']
            username = payload['user'].get('name', payload['user'].get('username', 'Unknown'))
            action = payload['actions'][0]['value']
            trigger_id = payload['trigger_id']
            channel_id = payload['channel']['id']
            
            print(f"🔍 DEBUG: Mark resolved clicked by {username} ({user})")
            print(f"🔍 DEBUG: Action value: {action}")
            print(f"🔍 DEBUG: Channel ID: {channel_id}")
            
            # Parse the action value to extract blocker ID
            # Format: "resolve_{blocker_id}" or "resolved_{user_id}_{kr_name}_{description}"
            if action.startswith('resolve_'):
                # Channel format: "resolve_blocker_U0919MVQLLU_1752543450"
                parts = action.split('_', 1)  # Split into max 2 parts
                if len(parts) < 2:
                    print(f"❌ Invalid action value format: {action}")
                    return
                blocker_id = parts[1]
            elif action.startswith('resolved_'):
                # DM format: "resolved_U0919MVQLLU_asdasdessesesese_asasdadsese"
                parts = action.split('_', 3)  # Split into 4 parts
                if len(parts) < 4:
                    print(f"❌ Invalid DM action value format: {action}")
                    return
                user_id = parts[1]
                kr_name = parts[2]
                blocker_description = parts[3]
                
                # Create a synthetic blocker_id for DM format
                blocker_id = f"dm_{user_id}_{kr_name}_{blocker_description}"
                print(f"🔍 DEBUG: Parsed DM format blocker: {blocker_id}")
            else:
                print(f"❌ Unknown action value format: {action}")
                return
            
            # Get blocker info from active_blockers or create from DM format
            if action.startswith('resolved_'):
                # DM format - extract info from action value
                parts = action.split('_', 3)
                blocked_user_id = parts[1]
                kr_name = parts[2]
                blocker_description = parts[3]
                
                # Create minimal blocker_info for DM format
                blocker_info = {
                    'user_id': blocked_user_id,
                    'user_name': username,  # Use the resolver's name
                    'kr_name': kr_name,
                    'blocker_description': blocker_description,
                    'urgency': 'Unknown',
                    'notes': '',
                    'source': 'dm_resolution'
                }
                print(f"🔍 DEBUG: Created blocker_info for DM resolution: {blocker_id}")
            else:
                # Channel format - get from active_blockers
                if not hasattr(self, 'active_blockers') or blocker_id not in self.active_blockers:
                    print(f"❌ Blocker {blocker_id} not found in active blockers")
                    return
                
                blocker_info = self.active_blockers[blocker_id]
                blocked_user_id = blocker_info['user_id']
                kr_name = blocker_info['kr_name']
                blocker_description = blocker_info['blocker_description']
            
            print(f"🔍 DEBUG: Parsed values:")
            print(f"   - Blocked user ID: {blocked_user_id}")
            print(f"   - KR Name: {kr_name}")
            print(f"   - Blocker Description: {blocker_description}")
            
            # Always open resolution modal for both DM and channel
            print(f"🔍 DEBUG: Opening resolution modal")
            
            # Create resolution modal
            modal_view = {
                "type": "modal",
                "callback_id": "resolution_modal",
                "title": {
                    "type": "plain_text",
                    "text": "Mark Blocker Resolved",
                    "emoji": True
                },
                "submit": {
                    "type": "plain_text",
                    "text": "Resolve",
                    "emoji": True
                },
                "close": {
                    "type": "plain_text",
                    "text": "Cancel",
                    "emoji": True
                },
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Resolving Blocker*\n\n**KR:** {kr_name}\n**Description:** {blocker_description}\n\nPlease provide resolution details:"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "resolution_notes",
                        "label": {
                            "type": "plain_text",
                            "text": "Resolution Notes",
                            "emoji": True
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "resolution_notes_input",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "How was this blocker resolved? What was the solution?"
                            },
                            "multiline": True
                        },
                        "optional": True
                    },
                    {
                        "type": "input",
                        "block_id": "hidden_data",
                        "label": {
                            "type": "plain_text",
                            "text": "Hidden Data (internal)",
                            "emoji": True
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "hidden_data_input",
                            "initial_value": blocker_id
                        }
                    }
                ]
            }
            
            # Open the modal
            response = self.client.views_open(
                trigger_id=trigger_id,
                view=modal_view
            )
            
            print(f"✅ Resolution modal opened for {username}")
            
        except Exception as e:
            print(f"❌ Error handling mark resolved click: {e}")
            import traceback
            traceback.print_exc()

    def _resolve_blocker_directly(self, blocker_id, blocked_user_id, kr_name, blocker_description, 
                                resolver_id, resolver_name, resolution_notes, channel_id, message_ts, blocker_info=None):
        """Directly resolve a blocker without modal (for DM responses)."""
        try:
            print(f"🔍 DEBUG: Directly resolving blocker: {blocker_id}")
            
            # Log the blocker resolution to Coda
            success = True
            if self.coda:
                try:
                    # Log resolution to Blocker Resolution table
                    coda_success = self.coda.resolve_blocker(
                        user_id=blocked_user_id,
                        kr_name=kr_name,
                        blocker_description=blocker_description,
                        resolved_by=resolver_name,
                        resolution_notes=resolution_notes,
                        slack_client=self.client,
                        user_name=blocker_info.get('user_name', blocked_user_id) if blocker_info else blocked_user_id
                    )
                    if coda_success:
                        print(f"✅ Blocker resolution logged in Coda by {resolver_name}")
                    else:
                        print("⚠️ Failed to log blocker resolution in Coda, but continuing...")
                        
                except Exception as e:
                    print(f"⚠️ Error logging blocker resolution in Coda: {e}")
                    print("⚠️ Continuing with resolution process...")
                    import traceback
                    traceback.print_exc()
            else:
                print("⚠️ Coda not available, skipping Coda logging")
            
            # Mark as resolved in tracked blockers (if exists)
            if hasattr(self, 'tracked_blockers'):
                for tracked_id, tracked_info in self.tracked_blockers.items():
                    if (tracked_info['user_id'] == blocked_user_id and 
                        tracked_info['kr_name'] == kr_name and
                        tracked_info['blocker_description'] == blocker_description):
                        tracked_info['resolved'] = True
                        tracked_info['resolution_time'] = datetime.now()
                        tracked_info['resolved_by'] = resolver_name
                        tracked_info['resolution_notes'] = resolution_notes
                        print(f"✅ Blocker marked as resolved in tracked blockers: {tracked_id}")
                        break
            
            # Mark as resolved in active blockers (new system)
            if hasattr(self, 'active_blockers'):
                if blocker_id in self.active_blockers:
                    # Mark as resolved
                    self.active_blockers[blocker_id]['resolved'] = True
                    self.active_blockers[blocker_id]['resolved_by'] = resolver_name
                    self.active_blockers[blocker_id]['resolved_at'] = time.time()
                    self.active_blockers[blocker_id]['resolution_notes'] = resolution_notes
                    print(f"✅ Blocker marked as resolved in active blockers: {blocker_id}")
                else:
                    print(f"❌ Blocker {blocker_id} not found in active blockers")
            
            # Send confirmation messages
            if success:
                # Send confirmation to resolver
                try:
                    self.client.chat_postMessage(
                        channel=resolver_id,
                        text=f"🎉 Successfully marked blocker as resolved!\n\n**KR:** {kr_name}\n**Description:** {blocker_description}\n**Resolution Notes:** {resolution_notes}"
                    )
                    print(f"✅ Confirmation sent to resolver {resolver_name}")
                except Exception as e:
                    print(f"❌ Error sending confirmation to resolver: {e}")
                
                # Send notification to blocked user
                try:
                    dm_response = self.client.conversations_open(users=[blocked_user_id])
                    dm_channel = dm_response['channel']['id']
                    self.client.chat_postMessage(
                        channel=dm_channel,
                        text=f"✅ Your blocker has been resolved by {resolver_name}!\n\n**KR:** {kr_name}\n**Description:** {blocker_description}\n**Resolution Notes:** {resolution_notes}"
                    )
                except Exception as e:
                    print(f"❌ Error sending notification to blocked user: {e}")
                
                # Delete the blocker message from the channel and update details
                print(f"🔍 DEBUG: Attempting to delete blocker message")
                print(f"🔍 DEBUG: Channel ID: {channel_id}")
                print(f"🔍 DEBUG: Message TS: {message_ts}")
                
                # If we don't have channel_id, try to get it from config
                if not channel_id:
                    leads_channel = getattr(self.config, 'SLACK_LEADS_CHANNEL', 'leads')
                    print(f"🔍 DEBUG: No channel_id found, using leads channel from config: {leads_channel}")
                    # Note: We can't delete without message_ts, so we'll just send a completion message
                    if not message_ts:
                        print(f"❌ No message_ts available, cannot delete message")
                        # Send completion message to leads channel
                        completion_message = f"✅ *Blocker Resolved*\n\n"
                        completion_message += f"**KR:** {kr_name}\n"
                        completion_message += f"**Description:** {blocker_description}\n"
                        completion_message += f"**Resolved by:** <@{resolver_id}> ({resolver_name})\n"
                        completion_message += f"**Resolution Notes:** {resolution_notes}\n"
                        completion_message += f"**Resolved at:** {time.strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        try:
                            self.client.chat_postMessage(
                                channel=f"#{leads_channel}",
                                text=completion_message
                            )
                            print(f"✅ Sent completion summary to leads channel #{leads_channel}")
                        except Exception as e:
                            print(f"❌ Error sending completion summary: {e}")
                
                if channel_id and message_ts:
                    try:
                        # Delete the original blocker message
                        self.client.chat_delete(channel=channel_id, ts=message_ts)
                        print(f"✅ Deleted blocker message from channel {channel_id}")
                        
                        # Send a completion summary to the channel
                        completion_message = f"✅ *Blocker Resolved*\n\n"
                        completion_message += f"**KR:** {kr_name}\n"
                        completion_message += f"**Description:** {blocker_description}\n"
                        completion_message += f"**Resolved by:** <@{resolver_id}> ({resolver_name})\n"
                        completion_message += f"**Resolution Notes:** {resolution_notes}\n"
                        completion_message += f"**Resolved at:** {time.strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        self.client.chat_postMessage(
                            channel=channel_id,
                            text=completion_message
                        )
                        print(f"✅ Sent completion summary to channel {channel_id}")
                    except Exception as e:
                        print(f"❌ Error deleting message or sending completion: {e}")
                
                # Delete any tracked reminder messages
                reminder_key = f"{blocked_user_id}_{kr_name}_{blocker_description}"
                if hasattr(self, 'tracked_reminder_messages') and reminder_key in self.tracked_reminder_messages:
                    try:
                        reminder_info = self.tracked_reminder_messages[reminder_key]
                        self.client.chat_delete(
                            channel=reminder_info['channel_id'], 
                            ts=reminder_info['message_ts']
                        )
                        del self.tracked_reminder_messages[reminder_key]
                        print(f"✅ Deleted tracked reminder message for {reminder_key}")
                    except Exception as e:
                        print(f"⚠️ No tracked reminder message found for key: {reminder_key}")
                
                print(f"✅ Direct blocker resolution completed successfully")
            
        except Exception as e:
            print(f"❌ Error in direct blocker resolution: {e}")
            import traceback
            traceback.print_exc()

    def handle_blocker_followup_response(self, user_id, action_value):
        """Handle responses to 24-hour blocker follow-up."""
        try:
            # Parse the action value to get blocker ID and response type
            # Format is: "resolved_blocker_U0919MVQLLU_1752260354" or "still_working_blocker_U0919MVQLLU_1752260354"
            # OR: "resolved_U0919MVQLLU_kr_name_description" (from Coda check)
            if action_value.startswith('resolved_'):
                response_type = 'resolved'
                # Check if this is the new format from Coda check
                if action_value.count('_') >= 4:
                    # New format: "resolved_U0919MVQLLU_kr_name_description"
                    parts = action_value.split('_', 3)
                    user_id = parts[1]
                    kr_name = parts[2]
                    blocker_description = parts[3]
                    # Create a synthetic blocker_id for lookup
                    blocker_id = f"coda_{user_id}_{kr_name}_{blocker_description}"
                    print(f"🔍 DEBUG: Parsed Coda format blocker: {blocker_id}")
                else:
                    # Old format: "resolved_blocker_U0919MVQLLU_1752260354"
                    blocker_id = action_value[9:]  # Remove "resolved_"
            elif action_value.startswith('still_working_'):
                response_type = 'still_working'
                blocker_id = action_value[14:]  # Remove "still_working_"
            elif action_value.startswith('need_help_'):
                response_type = 'need_help'
                # Check if this is the new format from Coda check
                if action_value.count('_') >= 4:
                    # New format: "need_help_U0919MVQLLU_kr_name_description"
                    parts = action_value.split('_', 3)
                    user_id = parts[1]
                    kr_name = parts[2]
                    blocker_description = parts[3]
                    # Create a synthetic blocker_id for lookup
                    blocker_id = f"coda_{user_id}_{kr_name}_{blocker_description}"
                    print(f"🔍 DEBUG: Parsed Coda format blocker: {blocker_id}")
                else:
                    # Old format: "need_help_blocker_U0919MVQLLU_1752260354"
                    blocker_id = action_value[10:]  # Remove "need_help_"
            else:
                print(f"❌ Unknown response type in action value: {action_value}")
                return
            
            # Try to find blocker in both active_blockers and tracked_blockers
            blocker_info = None
            blocker_source = None
            
            # First check active_blockers (new escalation system)
            if hasattr(self, 'active_blockers') and blocker_id in self.active_blockers:
                blocker_info = self.active_blockers[blocker_id]
                blocker_source = 'active_blockers'
                print(f"✅ Found blocker in active_blockers: {blocker_id}")
            # Then check tracked_blockers (old system)
            elif hasattr(self, 'tracked_blockers') and blocker_id in self.tracked_blockers:
                blocker_info = self.tracked_blockers[blocker_id]
                blocker_source = 'tracked_blockers'
                print(f"✅ Found blocker in tracked_blockers: {blocker_id}")
            # Check if this is a Coda format blocker (from unresolved blocker check)
            elif blocker_id.startswith('coda_'):
                # This is from the Coda unresolved blocker check
                # Extract user_id, kr_name, and description from the synthetic blocker_id
                parts = blocker_id.split('_', 3)
                if len(parts) >= 4:
                    user_id = parts[1]
                    kr_name = parts[2]
                    blocker_description = parts[3]
                    
                    # Create a minimal blocker_info for Coda blockers
                    blocker_info = {
                        'user_id': user_id,
                        'user_name': 'Unknown',  # Will be looked up
                        'kr_name': kr_name,
                        'blocker_description': blocker_description,
                        'urgency': 'Unknown',
                        'notes': '',
                        'source': 'coda_check'
                    }
                    blocker_source = 'coda_check'
                    print(f"✅ Created blocker_info for Coda check: {blocker_id}")
                else:
                    print(f"❌ Invalid Coda blocker ID format: {blocker_id}")
                    return
            else:
                print(f"❌ Blocker ID not found in any system: {blocker_id}")
                return
            
            if response_type == "resolved":
                # Mark as resolved
                blocker_info['resolved'] = True
                blocker_info['resolution_time'] = datetime.now()
                
                # Send confirmation
                self.client.chat_postMessage(
                    channel=user_id,
                    text=f"🎉 Great! I've marked your blocker as resolved. Thanks for the update!"
                )
                
                # If this is from the new escalation system or Coda check, also mark it resolved in Coda
                if blocker_source in ['active_blockers', 'coda_check'] and self.coda:
                    try:
                        # For Coda resolution, we need to pass the display name, not the user ID
                        # because the Coda table stores display names in the "Name" column
                        user_identifier = blocker_info.get('user_name', blocker_info['user_id'])
                        
                        # Call the resolve_blocker function to update Coda
                        coda_success = self.coda.resolve_blocker(
                            user_id=blocker_info['user_id'],  # Use actual user_id
                            kr_name=blocker_info['kr_name'],
                            blocker_description=blocker_info['blocker_description'],
                            resolved_by=blocker_info.get('user_name', 'Unknown'),
                            resolution_notes="Resolved via 24-hour follow-up",
                            slack_client=self.client,
                            user_name=blocker_info.get('user_name', blocker_info['user_id'])
                        )
                        if coda_success:
                            print(f"✅ Updated Coda for resolved blocker: {blocker_id}")
                        else:
                            print(f"⚠️ Failed to update Coda for blocker resolution: {blocker_id}")
                    except Exception as e:
                        print(f"⚠️ Failed to update Coda for blocker resolution: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Notify escalation channel
                escalation_channel = getattr(self.config, 'SLACK_ESCALATION_CHANNEL', 'general')
                self.client.chat_postMessage(
                    channel=f"#{escalation_channel}",
                    text=f"✅ <@{user_id}> has resolved their blocker: {blocker_info['kr_name']}"
                )
                
                # If this is from Coda check, try to delete the reminder message
                if blocker_source == 'coda_check':
                    try:
                        if hasattr(self, 'unresolved_reminder_messages'):
                            # Find and delete the reminder message
                            reminder_key = f"{blocker_info['user_id']}_{blocker_info['kr_name']}_{blocker_info['blocker_description']}"
                            if reminder_key in self.unresolved_reminder_messages:
                                reminder_info = self.unresolved_reminder_messages[reminder_key]
                                self.client.chat_delete(
                                    channel=reminder_info['channel_id'],
                                    ts=reminder_info['message_ts']
                                )
                                del self.unresolved_reminder_messages[reminder_key]
                                print(f"✅ Deleted unresolved reminder message for {reminder_key}")
                            else:
                                print(f"⚠️ No tracked reminder message found for key: {reminder_key}")
                    except Exception as e:
                        print(f"❌ Error deleting reminder message: {e}")
                
            elif response_type == "still_working":
                # Acknowledge and encourage
                self.client.chat_postMessage(
                    channel=user_id,
                    text=f"👍 Thanks for the update! Keep up the good work. Let us know if you need any help!"
                )
                
            elif response_type == "need_help":
                # Escalate for additional help
                # Use leads channel for new system, escalation channel for old system
                if blocker_source in ['active_blockers', 'coda_check']:
                    escalation_channel = getattr(self.config, 'SLACK_LEADS_CHANNEL', 'leads')
                else:
                    escalation_channel = getattr(self.config, 'SLACK_ESCALATION_CHANNEL', 'general')
                
                escalation_message = f"🆘 *Additional Help Requested*\n\n"
                escalation_message += f"<@{user_id}> still needs help with their blocker after 24 hours:\n\n"
                escalation_message += f"*Blocker:* {blocker_info['blocker_description']}\n"
                escalation_message += f"*KR:* {blocker_info['kr_name']}\n"
                escalation_message += f"*Urgency:* {blocker_info.get('urgency', 'Unknown')}\n\n"
                escalation_message += f"<!here> please reach out to <@{user_id}> to provide additional assistance."
                
                self.client.chat_postMessage(
                    channel=f"#{escalation_channel}",
                    text=escalation_message
                )
                
                # Confirm to user
                self.client.chat_postMessage(
                    channel=user_id,
                    text=f"🆘 I've escalated your request for additional help. Someone from the team will reach out to you soon!"
                )
            
            print(f"✅ Handled blocker follow-up response: {response_type} for {blocker_info['user_name']}")
            
        except Exception as e:
            print(f"❌ Error handling blocker follow-up response: {e}")

    def get_slack_user_list(self, cache_seconds=600):
        now = time.time()
        if self._user_list_cache and (now - self._user_list_cache_time) < cache_seconds:
            return self._user_list_cache
        users = self.client.users_list()["members"]
        self._user_list_cache = users
        self._user_list_cache_time = now
        return users
    
    def claim_blocker(self, blocker_id, claimer_id, claimer_name, channel_id, message_ts):
        """Handle claiming a blocker by a lead."""
        try:
            if not hasattr(self, 'active_blockers') or blocker_id not in self.active_blockers:
                print(f"❌ Blocker {blocker_id} not found in active blockers")
                return
            
            blocker_info = self.active_blockers[blocker_id]
            
            # Check if already claimed
            if blocker_info['status'] == 'claimed':
                print(f"❌ Blocker {blocker_id} already claimed by {blocker_info['claimed_by']}")
                return
            
            # Update blocker status
            blocker_info['status'] = 'claimed'
            blocker_info['claimed_by'] = claimer_id
            blocker_info['claimed_at'] = time.time()
            
            # Format urgency with emoji
            urgency_emoji = {
                'Low': '🟢',
                'Medium': '🟡', 
                'High': '🟠',
                'Critical': '🔴'
            }.get(blocker_info['urgency'], '⚪')
            
            # Create updated message
            updated_message = f"🚨 *BLOCKER ESCALATION - {urgency_emoji} {blocker_info['urgency']} Priority*\n\n"
            updated_message += f"<@{blocker_info['user_id']}> ({blocker_info['user_name']}) is blocked and needs assistance!\n\n"
            updated_message += f"*Blocker Details:*\n"
            updated_message += f"• **Description:** {blocker_info['blocker_description']}\n"
            updated_message += f"• **KR:** {blocker_info['kr_name']}\n"
            updated_message += f"• **Urgency:** {urgency_emoji} {blocker_info['urgency']}\n"
            updated_message += f"• **Notes:** {blocker_info['notes'] if blocker_info['notes'] else 'None'}\n\n"
            updated_message += f"*Status:* ✅ Claimed by <@{claimer_id}> ({claimer_name})"
            
            # Create updated message blocks
            updated_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": updated_message
                    }
                },
                {
                    "type": "actions",
                    "block_id": f"progress_blocker_{blocker_id}",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📝 Update Progress",
                                "emoji": True
                            },
                            "value": f"progress_{blocker_id}",
                            "action_id": "update_progress",
                            "style": "primary"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Mark Resolved",
                                "emoji": True
                            },
                            "value": f"resolve_{blocker_id}",
                            "action_id": "mark_resolved",
                            "style": "primary"
                        }
                    ]
                }
            ]
            
            # Update the message
            self.client.chat_update(
                channel=channel_id,
                ts=message_ts,
                blocks=updated_blocks,
                text=f"🚨 Blocker claimed by {claimer_name}: {blocker_info['kr_name']}"
            )
            
            # Notify the original user that someone is helping
            try:
                self.client.chat_postMessage(
                    channel=blocker_info['user_id'],
                    text=f"🎉 Great news! <@{claimer_id}> ({claimer_name}) has claimed your blocker and is working on it. They'll reach out to you soon!"
                )
            except Exception as e:
                print(f"❌ Error notifying user about claim: {e}")
            
            print(f"✅ Blocker {blocker_id} claimed by {claimer_name}")
            
        except Exception as e:
            print(f"❌ Error claiming blocker: {e}")
    
    def open_progress_update_modal(self, blocker_id, user_id, username, channel_id, message_ts, trigger_id):
        """Open a modal for updating blocker progress."""
        try:
            if not hasattr(self, 'active_blockers') or blocker_id not in self.active_blockers:
                print(f"❌ Blocker {blocker_id} not found in active blockers")
                return
            
            blocker_info = self.active_blockers[blocker_id]
            
            # Create modal view for progress update
            modal_view = {
                "type": "modal",
                "callback_id": "progress_update_modal",
                "private_metadata": f"{blocker_id}_{channel_id}_{message_ts}",
                "title": {
                    "type": "plain_text",
                    "text": "Update Blocker Progress",
                    "emoji": True
                },
                "submit": {
                    "type": "plain_text",
                    "text": "Update",
                    "emoji": True
                },
                "close": {
                    "type": "plain_text",
                    "text": "Cancel",
                    "emoji": True
                },
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Updating progress for blocker: *{blocker_info['blocker_description']}*"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "progress_update_input",
                        "label": {
                            "type": "plain_text",
                            "text": "Progress Update",
                            "emoji": True
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "progress_update_text",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Describe the progress made on this blocker..."
                            }
                        }
                    }
                ]
            }
            
            # Open the modal
            response = self.client.views_open(
                trigger_id=trigger_id,
                view=modal_view
            )
            
            print(f"✅ Progress update modal opened for blocker {blocker_id}")
            
        except Exception as e:
            print(f"❌ Error opening progress update modal: {e}")

    def handle_progress_update_modal_submission(self, payload):
        """Handle progress update modal submission."""
        try:
            import time
            
            # Extract data from payload
            user_id = payload['user']['id']
            user_name = payload['user']['name']
            view = payload['view']
            private_metadata = view.get('private_metadata', '')
            
            # Parse private metadata: blocker_id_channel_id_message_ts
            metadata_parts = private_metadata.split('_', 2)
            if len(metadata_parts) >= 3:
                blocker_id = metadata_parts[0]
                channel_id = metadata_parts[1]
                message_ts = metadata_parts[2]
            else:
                print(f"❌ Invalid private metadata format: {private_metadata}")
                return {"response_action": "errors", "errors": ["Invalid metadata"]}, 400
            
            # Get progress update text
            progress_text = view['state']['values']['progress_update_input']['progress_update_text']['value']
            
            if not progress_text.strip():
                return {"response_action": "errors", "errors": ["Progress update cannot be empty"]}, 400
            
            # Update blocker with progress
            if not hasattr(self, 'active_blockers') or blocker_id not in self.active_blockers:
                print(f"❌ Blocker {blocker_id} not found in active blockers")
                return {"response_action": "errors", "errors": ["Blocker not found"]}, 400
            
            blocker_info = self.active_blockers[blocker_id]
            
            # Add progress update to blocker info
            if 'progress_updates' not in blocker_info:
                blocker_info['progress_updates'] = []
            
            progress_update = {
                'user_id': user_id,
                'user_name': user_name,
                'text': progress_text,
                'timestamp': time.time()
            }
            
            blocker_info['progress_updates'].append(progress_update)
            
            # Update the original message to show progress
            self.update_blocker_message_with_progress(blocker_id, channel_id, message_ts)
            
            # Notify the original user about the progress update
            try:
                notification_message = f"📈 *Progress Update*\n\n<@{user_id}> has updated the progress on your blocker:\n\n*Blocker:* {blocker_info['blocker_description']}\n*Progress:* {progress_text}"
                
                self.client.chat_postMessage(
                    channel=blocker_info['user_id'],
                    text=notification_message
                )
                print(f"✅ Progress update notification sent to {blocker_info['user_name']}")
            except Exception as e:
                print(f"⚠️ Could not send progress notification: {e}")
            
            print(f"✅ Progress update added for blocker {blocker_id}")
            return {"response_action": "clear"}, 200
            
        except Exception as e:
            print(f"❌ Error handling progress update modal submission: {e}")
            return {"response_action": "errors", "errors": [str(e)]}, 500

    def update_blocker_message_with_progress(self, blocker_id, channel_id, message_ts):
        """Update the original blocker message to show latest progress."""
        try:
            if not hasattr(self, 'active_blockers') or blocker_id not in self.active_blockers:
                print(f"❌ Blocker {blocker_id} not found in active blockers")
                return
            
            blocker_info = self.active_blockers[blocker_id]
            
            # Format urgency with emoji
            urgency_emoji = {
                'Low': '🟢',
                'Medium': '🟡', 
                'High': '🟠',
                'Critical': '🔴'
            }.get(blocker_info['urgency'], '⚪')
            
            # Create updated message
            status_emoji = "✅" if blocker_info['claimed_by'] else "⏳"
            status_text = f"Claimed by <@{blocker_info['claimed_by']}>" if blocker_info['claimed_by'] else "Unclaimed - Available for leads to claim"
            
            updated_message = f"🚨 *BLOCKER ESCALATION - {urgency_emoji} {blocker_info['urgency']} Priority*\n\n"
            updated_message += f"<@{blocker_info['user_id']}> ({blocker_info['user_name']}) is blocked and needs assistance!\n\n"
            updated_message += f"*Blocker Details:*\n"
            updated_message += f"• **Description:** {blocker_info['blocker_description']}\n"
            updated_message += f"• **KR:** {blocker_info['kr_name']}\n"
            updated_message += f"• **Urgency:** {urgency_emoji} {blocker_info['urgency']}\n"
            updated_message += f"• **Notes:** {blocker_info['notes'] if blocker_info['notes'] else 'None'}\n\n"
            updated_message += f"*Status:* {status_emoji} {status_text}"
            
            # Fetch and add Coda progress
            coda_progress = self.get_kr_progress_from_coda(blocker_info['kr_name'])
            if coda_progress:
                updated_message += f"\n\n*📊 KR Progress from Coda:*\n{coda_progress}"
            
            # Add latest progress update if available
            if blocker_info['progress_updates']:
                latest_update = blocker_info['progress_updates'][-1]
                updated_message += f"\n\n*Latest Progress Update:*\n{latest_update['text']} (by <@{latest_update['user_id']}>)"
            
            # Create updated blocks with appropriate buttons
            if blocker_info['claimed_by']:
                # Show progress update and mark resolved buttons
                updated_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": updated_message
                        }
                    },
                    {
                        "type": "actions",
                        "block_id": f"progress_actions_{blocker_id}",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📈 Update Progress",
                                    "emoji": True
                                },
                                "value": f"update_progress_{blocker_id}",
                                "action_id": "update_progress"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ Mark Resolved",
                                    "emoji": True
                                },
                                "value": f"resolve_{blocker_id}",
                                "action_id": "mark_resolved",
                                "style": "primary"
                            }
                        ]
                    }
                ]
            else:
                # Show claim and view details buttons
                updated_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": updated_message
                        }
                    },
                    {
                        "type": "actions",
                        "block_id": f"claim_blocker_{blocker_id}",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🎯 Claim Blocker",
                                    "emoji": True
                                },
                                "value": f"claim_{blocker_id}_{blocker_info['user_id']}_{blocker_info['user_name']}",
                                "action_id": "claim_blocker",
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📋 View Details",
                                    "emoji": True
                                },
                                "value": f"view_{blocker_id}",
                                "action_id": "view_blocker_details"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ Mark Resolved",
                                    "emoji": True
                                },
                                "value": f"resolve_{blocker_id}",
                                "action_id": "mark_resolved",
                                "style": "primary"
                            }
                        ]
                    }
                ]
            
            # Update the message
            self.client.chat_update(
                channel=channel_id,
                ts=message_ts,
                blocks=updated_blocks,
                text=f"🚨 Blocker Alert: {blocker_info['user_name']} needs help with {blocker_info['kr_name']}"
            )
            
            print(f"✅ Blocker message updated with progress for {blocker_id}")
            
        except Exception as e:
            print(f"❌ Error updating blocker message with progress: {e}")

    def get_kr_progress_from_coda(self, kr_name):
        """Fetch KR progress from CODA_TABLE_ID4."""
        try:
            if not self.coda:
                print("❌ Coda service not available")
                return None
            
            # Get KR progress from CODA_TABLE_ID4
            kr_info = self.coda.get_kr_display_info(kr_name)
            if kr_info and kr_info.get('progress'):
                return kr_info['progress']
            else:
                print(f"❌ No progress found for KR '{kr_name}' in Coda")
                return None
                
        except Exception as e:
            print(f"❌ Error fetching KR progress from Coda: {e}")
            return None

    def view_blocker_details(self, blocker_id, channel_id, message_ts):
        """Show detailed information about a blocker in a thread or update existing thread."""
        try:
            if not hasattr(self, 'active_blockers') or blocker_id not in self.active_blockers:
                print(f"❌ Blocker {blocker_id} not found in active blockers")
                return
            
            blocker_info = self.active_blockers[blocker_id]
            
            # Format urgency with emoji
            urgency_emoji = {
                'Low': '🟢',
                'Medium': '🟡', 
                'High': '🟠',
                'Critical': '🔴'
            }.get(blocker_info['urgency'], '⚪')
            
            # Create detailed view message
            details_message = f"📋 *Detailed Blocker Information*\n\n"
            details_message += f"*Reporter:* <@{blocker_info['user_id']}> ({blocker_info['user_name']})\n"
            details_message += f"*Status:* {blocker_info['status'].title()}\n"
            details_message += f"*Description:* {blocker_info['blocker_description']}\n"
            details_message += f"*KR:* {blocker_info['kr_name']}\n"
            details_message += f"*Urgency:* {urgency_emoji} {blocker_info['urgency']}\n"
            details_message += f"*Notes:* {blocker_info['notes'] if blocker_info['notes'] else 'None'}\n"
            details_message += f"*Current KR Status:* {blocker_info['kr_status_info']}\n"
            
            if blocker_info['claimed_by']:
                details_message += f"*Claimed by:* <@{blocker_info['claimed_by']}>\n"
                details_message += f"*Claimed at:* {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(blocker_info['claimed_at']))}\n"
            
            # Fetch progress from CODA_TABLE_ID4
            coda_progress = self.get_kr_progress_from_coda(blocker_info['kr_name'])
            if coda_progress:
                details_message += f"\n*📊 KR Progress from Coda:*\n{coda_progress}\n"
            
            if blocker_info['progress_updates']:
                details_message += f"\n*Progress Updates:*\n"
                for i, update in enumerate(blocker_info['progress_updates'], 1):
                    details_message += f"{i}. {update['text']} (by <@{update['user_id']}> at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(update['timestamp']))})\n"
            
            # Check if we already have a thread message for this blocker
            thread_ts = None
            if 'thread_ts' in blocker_info and blocker_info['thread_ts']:
                thread_ts = blocker_info['thread_ts']
                print(f"🔍 DEBUG: Found existing thread for blocker {blocker_id}: {thread_ts}")
            
            if thread_ts:
                # Update existing thread message
                try:
                    self.client.chat_update(
                        channel=channel_id,
                        ts=thread_ts,
                        text=details_message
                    )
                    print(f"✅ Updated existing thread message for blocker {blocker_id}")
                except Exception as e:
                    print(f"❌ Error updating thread message: {e}")
                    # If update fails, create a new thread message
                    thread_ts = None
            
            if not thread_ts:
                # Create new thread message
                try:
                    response = self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=details_message
                    )
                    # Store the thread timestamp for future updates
                    blocker_info['thread_ts'] = response['ts']
                    print(f"✅ Created new thread message for blocker {blocker_id}: {response['ts']}")
                except Exception as e:
                    print(f"❌ Error creating thread message: {e}")
            
        except Exception as e:
            print(f"❌ Error viewing blocker details: {e}")

    def get_accessible_channels(self):
        """Get list of channels the bot has access to."""
        try:
            response = self.client.conversations_list(types="public_channel,private_channel")
            if response['ok']:
                channels = response['channels']
                accessible_channels = []
                for channel in channels:
                    if channel.get('is_member', False):
                        accessible_channels.append(channel['name'])
                print(f"🔍 DEBUG: Bot has access to channels: {accessible_channels}")
                return accessible_channels
            else:
                print(f"❌ Error getting channels: {response.get('error', 'Unknown error')}")
                return []
        except Exception as e:
            print(f"❌ Error getting accessible channels: {e}")
            return []
    
    def send_completion_message_to_accessible_channel(self, completion_message):
        """Send completion message to the first accessible channel."""
        try:
            accessible_channels = self.get_accessible_channels()
            if not accessible_channels:
                print("❌ No accessible channels found")
                return False
            
            # Try to send to the first accessible channel
            for channel_name in accessible_channels:
                try:
                    self.client.chat_postMessage(
                        channel=f"#{channel_name}",
                        text=completion_message
                    )
                    print(f"✅ Sent completion message to #{channel_name}")
                    return True
                except Exception as e:
                    print(f"❌ Error sending to #{channel_name}: {e}")
                    continue
            
            print("❌ Could not send completion message to any accessible channel")
            return False
        except Exception as e:
            print(f"❌ Error in send_completion_message_to_accessible_channel: {e}")
            return False

    def handle_mentor_no_response(self, user_id, channel_id, message_ts):
        """Send a friendly message when the user has not yet asked their mentor."""
        self.client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=(
                f"<@{user_id}>, please reach out to your mentor first! They can often help you quickly. "
                "Once you've spoken with them, come back if you still need help! 🤝"
            )
        )

    def send_daily_blocker_digest(self):
        # sends the message but doesn't actually grab the blocker list - NEED TO FIX
        """Send a daily digest of blockers/issues from Coda to the main Slack channel, with a Mistral-generated summary."""
        try:
            if not self.coda:
                print("❌ Coda service not available, cannot send blocker digest.")
                return
            # Get today's date in YYYY-MM-DD format (EST)
            est_now = get_est_time()
            today_str = est_now.strftime('%Y-%m-%d')
            blockers = self.coda.get_blockers_by_date(today_str)
            if not blockers:
                digest_text = f"No blockers reported today ({today_str}). 🎉"
            else:
                # Generate a summary using Mistral
                summary = ""
                if self.mistral:
                    try:
                        # Compose a prompt with all blockers
                        prompt = "Here are the blockers reported today. Summarize the main issues, trends, and suggest next steps for the team.\n\n"
                        for idx, blocker in enumerate(blockers, 1):
                            prompt += (
                                f"{idx}. User: {blocker['user_id']}\n"
                                f"   KR: {blocker['kr_name']}\n"
                                f"   Description: {blocker['blocker_description']}\n"
                                f"   Urgency: {blocker['urgency']}\n"
                                f"   Notes: {blocker['notes']}\n\n"
                            )
                        summary = self.mistral.generate_help_suggestion(blocker_description=prompt)
                    except Exception as e:
                        print(f"❌ Error generating Mistral summary: {e}")
                        summary = "(AI summary unavailable)"
                else:
                    summary = "(AI summary unavailable)"
                digest_text = f"*Daily Blocker Digest for {today_str}*\n\n*AI Summary:*\n{summary}\n\n*Blocker List:*\n"
                for idx, blocker in enumerate(blockers, 1):
                    digest_text += (
                        f"*{idx}.* <@{blocker['user_id']}>\n"
                        f"• *KR:* {blocker['kr_name']}\n"
                        f"• *Description:* {blocker['blocker_description']}\n"
                        f"• *Urgency:* {blocker['urgency']}\n"
                        f"• *Notes:* {blocker['notes']}\n\n"
                    )
            self.client.chat_postMessage(
                channel=self.channel_id,
                text=digest_text
            )
            print(f"✅ Daily blocker digest sent for {today_str}")
        except Exception as e:
            print(f"❌ Error sending daily blocker digest: {e}")

    def send_daily_standup_digest(self):
        """Send a daily digest of standup responses from Coda to the main Slack channel."""
        try:
            if not self.coda:
                print("❌ Coda service not available, cannot send standup digest.")
                return
            # Get today's date in YYYY-MM-DD format (EST)
            est_now = get_est_time()
            today_str = est_now.strftime('%Y-%m-%d')
            responses = self.coda.get_responses_by_date(today_str)
            if not responses:
                digest_text = f"No standup responses reported today ({today_str})."
            else:
                digest_text = f"*Daily Standup Responses for {today_str}:*\n\n"
                for idx, resp in enumerate(responses, 1):
                    digest_text += (
                        f"*{idx}.* <@{resp['user_id']}>\n"
                        f"• *Response:* {resp['response']}\n"
                        f"• *Timestamp:* {resp['timestamp']}\n\n"
                    )
            self.client.chat_postMessage(
                channel=self.channel_id,
                text=digest_text
            )
            print(f"✅ Daily standup digest sent for {today_str}")
        except Exception as e:
            print(f"❌ Error sending daily standup digest: {e}")

def generate_kr_explanation(kr_name, owner, status, definition_of_done=None):
    """Generate a contextual explanation for a KR using Mistral AI."""
    try:
        from mistral_service import MistralService
        mistral = MistralService()
        return mistral.generate_kr_explanation(kr_name, owner, status, definition_of_done=definition_of_done)
    except ImportError:
        return f"This is a placeholder explanation for the KR '{kr_name}'. (AI integration needed)"
    except Exception as e:
        print(f"❌ Error generating KR explanation: {e}")
        return f"This is a placeholder explanation for the KR '{kr_name}'. (AI integration needed)"

# Initialize the bot at the module level so it's always available
bot = DailyStandupBot()

@app.route('/slack/events', methods=['POST'])
def handle_events():
    """Handle incoming Slack events."""
    try:
        # Get the request data
        if request.is_json:
            payload = request.get_json()
        else:
            # Handle form-encoded data
            payload = request.form.to_dict()
            if 'payload' in payload:
                payload = json.loads(payload['payload'])
        
        print("Received event:", payload)
        
        # Handle URL verification
        if payload.get('type') == 'url_verification':
            return jsonify({"challenge": payload['challenge']})
        
        # Handle slash commands (they come through events in Bolt-style apps)
        # Slash commands can come in different formats depending on the Slack app configuration
        if (payload.get('type') == 'slash_command' or 
            payload.get('command')):
            print("🔍 DEBUG: Received slash command through events endpoint")
            print(f"🔍 DEBUG: Slash command payload: {json.dumps(payload, indent=2)}")
            return handle_slash_commands()
        
        # Event deduplication - check if we've already processed this event
        if payload.get('type') == 'event_callback':
            event_id = payload.get('event_id')
            if event_id and event_id in bot.processed_events:
                print(f"⚠️ Duplicate event detected: {event_id}")
                return jsonify({"text": "OK"})
            
            # Add to processed events
            if event_id:
                bot.processed_events.add(event_id)
                # Keep only last 1000 events to prevent memory issues
                if len(bot.processed_events) > 1000:
                    bot.processed_events = set(list(bot.processed_events)[-500:])
        
        # Handle button clicks
        if payload.get('type') == 'block_actions':
            print("🔍 DEBUG: Received block_actions event")
            print(f"🔍 DEBUG: Actions: {payload.get('actions', [])}")
            try:
                result = bot.handle_button_click(payload)
                if isinstance(result, tuple):
                    response_data, status_code = result
                else:
                    response_data = result
                    status_code = 200
                return jsonify(response_data), status_code
            except Exception as e:
                print(f"❌ Error handling block_actions: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({"response_action": "errors", "errors": [str(e)]}), 500
        
        # Handle form submissions (blocker details and resolution)
        if payload.get('type') == 'view_submission':
            print("🔍 DEBUG: Received view_submission event")
            print(f"🔍 DEBUG: Callback ID: {payload.get('view', {}).get('callback_id')}")
            if payload.get('view', {}).get('callback_id') == 'blocker_form':
                print("🔍 DEBUG: Processing blocker form submission")
                try:
                    bot.handle_blocker_form_submission(payload)
                    return jsonify({"response_action": "clear"}), 200
                except Exception as e:
                    print(f"❌ Error handling view_submission: {e}")
                    return jsonify({"response_action": "errors", "errors": [str(e)]}), 500
            elif payload.get('view', {}).get('callback_id') == 'resolution_modal':
                print("🔍 DEBUG: Processing resolution modal submission")
                try:
                    result = bot.handle_resolution_modal_submission(payload)
                    if isinstance(result, tuple):
                        response_data, status_code = result
                    else:
                        response_data = result
                        status_code = 200
                    return jsonify(response_data), status_code
                except Exception as e:
                    print(f"❌ Error handling resolution modal submission: {e}")
                    import traceback
                    traceback.print_exc()
                    return jsonify({"response_action": "errors", "errors": [str(e)]}), 500
            elif payload.get('view', {}).get('callback_id') == 'progress_update_modal':
                print("🔍 DEBUG: Processing progress update modal submission")
                try:
                    result = bot.handle_progress_update_modal_submission(payload)
                    if isinstance(result, tuple):
                        response_data, status_code = result
                    else:
                        response_data = result
                        status_code = 200
                    return jsonify(response_data), status_code
                except Exception as e:
                    print(f"❌ Error handling progress update modal submission: {e}")
                    import traceback
                    traceback.print_exc()
                    return jsonify({"response_action": "errors", "errors": [str(e)]}), 500
        
        # Handle message events (standup responses)
        if payload.get('type') == 'event_callback':
            event = payload['event']
            
            print(f"🔍 DEBUG: Processing event type: {event['type']}")
            print(f"🔍 DEBUG: Full event payload: {json.dumps(event, indent=2)}")
            
            if event['type'] == 'message':
                print(f"🔍 DEBUG: Message event details:")
                print(f"   - User: {event.get('user')}")
                print(f"   - Channel: {event.get('channel')}")
                print(f"   - Text: {event.get('text', '')[:50]}...")
                print(f"   - Thread TS: {event.get('thread_ts')}")
                print(f"   - Bot ID: {event.get('bot_id')}")
                print(f"   - Subtype: {event.get('subtype')}")
                
                # Handle message_deleted events (they don't have a user field)
                if event.get('subtype') == 'message_deleted':
                    print(f"🔍 DEBUG: Message deleted event - skipping processing")
                    return jsonify({'status': 'ok'})
                
                # Skip bot messages to prevent processing our own messages
                if 'bot_id' in event or event.get('user') == 'U0912DJRNSF':  # bot user ID
                    print(f"🔍 DEBUG: Skipping bot message")
                    return jsonify({'status': 'ok'})
                
                # Check if this is a DM (channel starts with 'D')
                channel_id = event.get('channel', '')
                is_dm = channel_id.startswith('D')
                
                if is_dm:
                    print(f"🔍 DEBUG: This is a DM message")

                    # Check if this is a reply to a standup prompt first
                    thread_ts = event.get('thread_ts')
                    if thread_ts:
                        print(f"🔍 DEBUG: Processing as standup response (in thread)")
                        # This is a reply in a DM (standup response)
                        bot.handle_standup_response(
                            user_id=event['user'],
                            message_ts=event['ts'],
                            thread_ts=thread_ts,
                            text=event['text'],
                            channel_id=event.get('channel')
                        )
                        return jsonify({'status': 'standup_response_processed'})

                    # Then check if this is a command (slash or exclamation)
                    text = event.get('text', '').strip()
                    if bot.handle_commands(event['user'], text, event.get('channel')):
                        print(f"🔍 DEBUG: Command processed successfully")
                        return jsonify({'status': 'command_processed'})

                    # Legacy support: KR search with 'kr (assignment name)' - Check this SECOND
                    text_lower = text.lower()
                    if text_lower.startswith('kr '):
                        print(f"🔍 DEBUG: Detected legacy KR search request")
                        search_term = text.strip()[3:]
                        if search_term.strip():
                            # Direct KR search - no mentor check needed for specific searches
                            matches = bot.coda.search_kr_table(search_term)
                            if matches:
                                result_lines = []
                                for m in matches:
                                    kr_name = m.get('c-yQ1M6UqTSj', 'N/A')
                                    owner = m.get('c-efR-vVo_3w', 'N/A')
                                    status = m.get('c-cC29Yow8Gr', 'N/A')
                                    definition_of_done = m.get('c-P_mQJLObL0', '')
                                    # If you have a link field, add it here (e.g., m.get('link', ''))
                                    link = m.get('link', None)
                                    # Generate contextual explanation using AI (now with definition of done)
                                    explanation = generate_kr_explanation(kr_name, owner, status, definition_of_done)
                                    line = f"*KR*: {kr_name}\n*Owner*: {owner}\n*Status*: {status}\n*Definition of Done*: {definition_of_done}\n*AI Explanation*: {explanation}"
                                    if link:
                                        line += f"\n<Link|{link}>"
                                    result_lines.append(line)
                                result_text = '\n\n'.join(result_lines)
                            else:
                                result_text = f'No matching KRs found for "{search_term}".'
                            bot.client.chat_postMessage(
                                channel=event.get('channel'),
                                text=result_text
                            )
                            return jsonify({'status': 'kr_search_done'})
                        else:
                            # No search term provided - send mentor check for KR clarification request
                            user_info = bot.client.users_info(user=event['user'])
                            user_name = user_info['user']['real_name']
                            bot.send_mentor_check(
                                user_id=event['user'],
                                standup_ts=event['ts'],
                                user_name=user_name,
                                request_type="kr",
                                channel=event.get('channel')
                            )
                            return jsonify({'status': 'mentor_check_sent'})

                    # Legacy support: Check for blocker phrases (will trigger for any message containing these words)
                    if any(phrase in text_lower for phrase in ["i'm blocked", "im blocked", "need help", "blocked", "help me"]):
                        print(f"🔍 DEBUG: Detected legacy blocker/help phrase in DM, sending mentor check.")
                        # Get user info for name
                        user_info = bot.client.users_info(user=event['user'])
                        user_name = user_info['user']['real_name']
                        bot.send_mentor_check(
                            user_id=event['user'],
                            standup_ts=event['ts'],
                            user_name=user_name,
                            request_type="blocker",
                            channel=event.get('channel')
                        )
                        return jsonify({'status': 'mentor_check_sent'})

                    # This section is now handled above - remove duplicate logic
                    pass
                else:
                    print(f"🔍 DEBUG: Not a DM message, ignoring")
            elif event['type'] == 'message.im':
                print(f"🔍 DEBUG: Direct message event received!")
                print(f"🔍 DEBUG: Message IM event details:")
                print(f"   - User: {event.get('user')}")
                print(f"   - Channel: {event.get('channel')}")
                print(f"   - Text: {event.get('text', '')[:50]}...")
                print(f"   - Thread TS: {event.get('thread_ts')}")
                
                # Skip bot messages
                if 'bot_id' in event or event.get('user') == 'U0912DJRNSF':
                    print(f"🔍 DEBUG: Skipping bot message in DM")
                    return jsonify({'status': 'ok'})
                
                # First, check if this is a command (slash or exclamation)
                text = event.get('text', '').strip()
                if bot.handle_commands(event['user'], text, event.get('channel')):
                    print(f"🔍 DEBUG: Command processed successfully in message.im")
                    return jsonify({'status': 'command_processed'})
                
                # This section is now handled above - remove duplicate logic
                pass
            elif event['type'] == 'reaction_added':
                print(f"🔍 DEBUG: Processing reaction event")
                # Handle reactions
                if event['item']['type'] == 'message':
                    # Check if this is a reaction to the main standup message
                    standup_ts = event['item']['ts']
                    if standup_ts in bot.active_standups:
                        # Quick reaction to standup
                        bot.handle_quick_reaction(
                            user_id=event['user'],
                            standup_ts=standup_ts,
                            reaction=event['reaction']
                        )
                    else:
                        # Reaction to follow-up message
                        bot.handle_reaction(
                            user_id=event['user'],
                            message_ts=event['item']['ts'],
                            reaction=event['reaction']
                        )
            else:
                print(f"🔍 DEBUG: Event type {event['type']} not handled")
        
        return jsonify({"text": "OK"})
        
    except Exception as e:
        print(f"Error handling event: {str(e)}")
        return jsonify({"text": "Error processing event"}), 500

@app.route('/slack/command', methods=['POST'])
def handle_slash_commands():
    """Handle Slack slash commands."""
    try:
        # Get form data from Slack
        command = request.form.get('command', '')
        text = request.form.get('text', '').strip()
        user_id = request.form.get('user_id', '')
        channel_id = request.form.get('channel_id', '')
        response_url = request.form.get('response_url', '')
        
        print(f"🔍 DEBUG: Received slash command: {command} with text: '{text}' from user: {user_id}")
        print(f"🔍 DEBUG: Channel ID: {channel_id}")
        print(f"🔍 DEBUG: Response URL: {response_url}")
        
        # Validate required fields
        if not command or not user_id:
            print(f"❌ Missing required fields: command={command}, user_id={user_id}")
            return jsonify({
                "response_type": "ephemeral",
                "text": "Invalid command format. Please try again."
            }), 400
        
        # Handle /kr command
        if command == '/kr':
            try:
                import threading
                def process_kr_command():
                    try:
                        time.sleep(1.0)
                        try:
                            user_info = bot.client.users_info(user=user_id)
                            user_name = user_info['user']['real_name']
                        except Exception as e:
                            print(f"❌ Error getting user info: {e}")
                            user_name = f"User {user_id}"
                        # Always trigger mentor check, pass search_term if present
                        bot.send_mentor_check(
                            user_id=user_id,
                            standup_ts=None,  # No thread for slash commands
                            user_name=user_name,
                            request_type="kr",
                            channel=user_id,
                            search_term=text if text else None  # Pass search term if present
                        )
                    except Exception as e:
                        print(f"❌ Error in background KR processing: {e}")
                thread = threading.Thread(target=process_kr_command)
                thread.daemon = True
                thread.start()
                response_text = "Processing KR request... Check your DM."
                try:
                    return jsonify({
                        "response_type": "ephemeral",
                        "text": response_text
                    })
                except Exception as e:
                    print(f"❌ Error in KR command handler: {e}")
                    return jsonify({
                        "response_type": "ephemeral",
                        "text": f"❌ Error processing KR command: {str(e)}"
                    })
            except Exception as e:
                print(f"❌ Error in KR command handler: {e}")
                return jsonify({
                    "response_type": "ephemeral",
                    "text": f"❌ Error processing KR command: {str(e)}"
                })
        
        # Handle other slash commands
        elif command == '/checkin':
            # Respond immediately and process in background to avoid timeout
            try:
                import threading
                def process_checkin_command():
                    try:
                        # Add a small delay to avoid rate limiting
                        time.sleep(1.0)  # Increased delay for free workspace
                        # Send standup with error handling
                        try:
                            bot.send_standup_to_dm(user_id)
                            print(f"✅ Standup prompt sent successfully to {user_id}")
                        except Exception as e:
                            print(f"❌ Error sending standup prompt: {e}")
                            # Don't try to send error message to avoid cascading failures
                    except Exception as e:
                        print(f"❌ Error in background checkin processing: {e}")
                        # Don't try to send error message to avoid cascading failures
                thread = threading.Thread(target=process_checkin_command)
                thread.daemon = True
                thread.start()
                return jsonify({
                    "response_type": "ephemeral",
                    "text": "Processing checkin request... Check your DM for the standup prompt."
                })
            except Exception as e:
                print(f"❌ Error in checkin command handler: {e}")
                return jsonify({
                    "response_type": "ephemeral",
                    "text": f"❌ Error processing checkin command: {str(e)}"
                })
        
        elif command == '/blocked':
            # Respond immediately and process in background to avoid timeout
            try:
                import threading
                def process_blocked_command():
                    try:
                        # Add a small delay to avoid rate limiting
                        time.sleep(1.0)  # Increased delay for free workspace
                        # Get user info with error handling
                        try:
                            user_info = bot.client.users_info(user=user_id)
                            user_name = user_info['user']['real_name']
                        except Exception as e:
                            print(f"❌ Error getting user info: {e}")
                            user_name = f"User {user_id}"
                        # Send mentor check directly to the user's DM
                        try:
                            print(f"🔍 DEBUG: Attempting to send mentor check to user DM: {user_id}")
                            result = bot.send_mentor_check(
                user_id=user_id,
                standup_ts=None,  # No thread for slash commands
                user_name=user_name,
                request_type="blocker",
                                channel=user_id  # Send directly to user's DM
                            )
                            if result is None or result is False:
                                print(f"❌ Mentor check returned None/False - likely failed")
                                # Don't send fallback - let the mentor check handle it
                        except Exception as e:
                            print(f"❌ Error sending mentor check to DM: {e}")
                            import traceback
                            traceback.print_exc()
                            # Don't send fallback - let the mentor check handle it
                                
                    except Exception as e:
                        print(f"❌ Error in background blocked processing: {e}")
                        # Don't try to send error message to avoid cascading failures
                
                thread = threading.Thread(target=process_blocked_command)
                thread.daemon = True
                thread.start()
                
                return jsonify({
                    "response_type": "ephemeral",
                    "text": "Processing blocker request... Check your DM for the mentor check message."
                })
            except Exception as e:
                print(f"❌ Error in blocked command handler: {e}")
                return jsonify({
                    "response_type": "ephemeral",
                    "text": f"❌ Error processing blocked command: {str(e)}"
                })
        
        elif command == '/health':
            # Respond immediately and process in background to avoid timeout
            try:
                import threading
                def process_health_command():
                    try:
                        # Add a small delay to avoid rate limiting
                        time.sleep(1.0)  # Increased delay for free workspace
                        # Send health check with error handling
                        try:
                            bot.send_health_check_to_dm(user_id)
                            print(f"✅ Health check prompt sent successfully to {user_id}")
                        except Exception as e:
                            print(f"❌ Error sending health check prompt: {e}")
                            # Don't try to send error message to avoid cascading failures
                    except Exception as e:
                        print(f"❌ Error in background health processing: {e}")
                        # Don't try to send error message to avoid cascading failures
                thread = threading.Thread(target=process_health_command)
                thread.daemon = True
                thread.start()
                return jsonify({
                    "response_type": "ephemeral",
                    "text": "Processing health check request... Check your DM for the health check prompt."
                })
            except Exception as e:
                print(f"❌ Error in health command handler: {e}")
                return jsonify({
                    "response_type": "ephemeral",
                    "text": f"❌ Error processing health command: {str(e)}"
                })
        
        elif command == '/role':
            # Handle role management commands - respond immediately to avoid timeout
            try:
                # Check if user has admin role first
                if not bot.has_role(user_id, 'admin'):
                    return jsonify({
                        "response_type": "ephemeral",
                        "text": "❌ You need admin privileges to manage roles."
                    })
                
                # If no text provided, show help immediately
                if not text.strip():
                    help_text = """*Role Management Commands:*
• `/rolelist` - List all roles and users
• `/role add @user role` - Add role to user
• `/role remove @user role` - Remove role from user
• `/role users role` - List users with specific role
• `/role channels` - List role-based channels

*Available Roles:* pm, lead, developer, designer, qa, devops, sm, admin"""
                    return jsonify({
                        "response_type": "ephemeral",
                        "text": help_text
                    })
                
                # For commands that need processing, respond immediately and process in background
                full_text = f"role {text}"  # Combine command and text
                
                # Start background processing
                import threading
                def process_role_command():
                    try:
                        # Add a small delay to avoid rate limiting
                        time.sleep(1.0)  # Increased delay for free workspace
                        
                        # Process role command directly to the user's DM
                        try:
                            print(f"🔍 DEBUG: Processing role command to user DM: {user_id}")
                            bot._handle_role_command(user_id, full_text, user_id)  # Send to user's DM
                            print(f"✅ Role command processed successfully to DM")
                        except Exception as e:
                            print(f"❌ Error processing role command to DM: {e}")
                            import traceback
                            traceback.print_exc()
                            # Don't try to send error message to avoid cascading failures
                            
                    except Exception as e:
                        print(f"❌ Error in background role processing: {e}")
                        # Don't try to send error message to avoid cascading failures
                
                thread = threading.Thread(target=process_role_command)
                thread.daemon = True
                thread.start()
                
                response_text = "Processing role command... Check your DM for results."
                
                return jsonify({
                    "response_type": "ephemeral",
                    "text": response_text
                })
                
            except Exception as e:
                print(f"❌ Error in role command handler: {e}")
                return jsonify({
                    "response_type": "ephemeral",
                    "text": f"❌ Error processing role command: {str(e)}"
                })
        
        elif command == '/rolelist':
            # Handle rolelist command specifically - respond immediately to avoid timeout
            try:
                # Check if user has admin role first
                if not bot.has_role(user_id, 'admin'):
                    return jsonify({
                        "response_type": "ephemeral",
                        "text": "❌ You need admin privileges to manage roles."
                    })
                
                # Start background processing
                import threading
                def process_rolelist():
                    try:
                        # Add a small delay to avoid rate limiting
                        time.sleep(1.0)  # Increased delay for free workspace
                        
                        # List roles directly to the user's DM
                        try:
                            print(f"🔍 DEBUG: Listing roles to user DM: {user_id}")
                            bot._list_all_roles(user_id)  # Send to user's DM
                            print(f"✅ Role list processed successfully to DM")
                        except Exception as e:
                            print(f"❌ Error listing roles to DM: {e}")
                            import traceback
                            traceback.print_exc()
                            # Don't try to send error message to avoid cascading failures
                            
                    except Exception as e:
                        print(f"❌ Error in background rolelist processing: {e}")
                        # Don't try to send error message to avoid cascading failures
                
                thread = threading.Thread(target=process_rolelist)
                thread.daemon = True
                thread.start()
                
                response_text = "Processing role list... Check your DM for results."
                
                return jsonify({
                    "response_type": "ephemeral",
                    "text": response_text
                })
                
            except Exception as e:
                print(f"❌ Error in rolelist command handler: {e}")
                return jsonify({
                    "response_type": "ephemeral",
                    "text": f"❌ Error processing rolelist command: {str(e)}"
                })
        
        elif command == '/help':
            # Respond immediately and process in background to avoid timeout
            try:
                import threading
                def process_help_command():
                    try:
                        # Add a small delay to avoid rate limiting
                        time.sleep(1.0)  # Increased delay for free workspace
                        # Send help info directly to the user's DM
                        try:
                            print(f"🔍 DEBUG: Sending help info to user DM: {user_id}")
                            if text.strip().lower() == 'admin':
                                if bot.has_role(user_id, 'admin'):
                                    bot.send_info_message(user_id, user_id, mode="admin")
                                else:
                                    bot.client.chat_postMessage(
                                        channel=user_id,
                                        text="❌ You need admin privileges to view admin/role management commands."
                                    )
                            else:
                                bot.send_info_message(user_id, user_id, mode="user")
                            print(f"✅ Help information sent successfully to DM")
                        except Exception as e:
                            print(f"❌ Error sending help information to DM: {e}")
                            import traceback
                            traceback.print_exc()
                    except Exception as e:
                        print(f"❌ Error in background help processing: {e}")
                thread = threading.Thread(target=process_help_command)
                thread.daemon = True
                thread.start()
                response_text = "Processing help request... Check your DM for help information."
                return jsonify({
                    "response_type": "ephemeral",
                    "text": response_text
                })
            except Exception as e:
                print(f"❌ Error in help command handler: {e}")
                return jsonify({
                    "response_type": "ephemeral",
                    "text": f"❌ Error processing help command: {str(e)}"
                })
        
        else:
            return jsonify({
                "response_type": "ephemeral",
                "text": f"Unknown command: {command}. Use /help to see available commands."
            })
            
    except Exception as e:
        print(f"❌ Error handling slash command: {e}")
        return jsonify({
            "response_type": "ephemeral",
            "text": "Sorry, there was an error processing your command. Please try again."
        }), 500

if __name__ == "__main__":
    import os
    import threading
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not getattr(BotConfig, 'FLASK_DEBUG', False):
        # Bot is already initialized at module level
        # Start scheduler in a background thread
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(3600)  # Check every hour instead of every minute
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        print("🤖 Daily Standup Bot Starting...")
        print(f"📅 Standup time: {bot.config.STANDUP_TIME}")
        print(f"📺 Channel: {bot.channel_id}")
        print(f"🚨 Escalation channel: #{bot.config.SLACK_ESCALATION_CHANNEL}")
        print(f"⏰ Reminder time: {bot.config.REMINDER_TIME}")
        print("🔄 Hybrid workflow: Reactions + Thread replies")
        # Removed: Send initial prompts on startup
        # Removed: bot.send_standup_to_all_users(users)
        # Removed: Health check send
        print("🚀 Bot is running... (Press Ctrl+C to stop)")
        app.run(
            host=BotConfig.FLASK_HOST,
            port=BotConfig.FLASK_PORT,
            debug=False
        ) 