import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv('.env')  # Explicitly load from .env file
import time
import schedule
import re
import json
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from flask import Flask, request, jsonify
from src.config import BotConfig
from coda_service import CodaService
import requests

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
        self.config = BotConfig.get_config_dict()
        
        # Validate configuration
        required_keys = ['slack_bot_token', 'slack_channel_id']
        missing_keys = [key for key in required_keys if key not in self.config]
        if missing_keys:
            raise ValueError(f"Missing required configuration keys: {missing_keys}")
        
        # Initialize Slack client
        self.client = WebClient(token=self.config['slack_bot_token'])
        self.channel_id = self.config['slack_channel_id']
        
        # Initialize Coda service (primary storage)
        print("📊 Initializing Coda connection...")
        try:
            self.coda = CodaService()
            if self.coda.api_token:
                print("✅ Coda connection successful")
                # List KR table columns for debugging (don't fail if this errors)
                try:
                    if self.coda:
                        self.coda.list_kr_table_columns()
                except Exception as debug_error:
                    print(f"⚠️ Debug logging failed (non-critical): {debug_error}")
            else:
                print("❌ Coda connection failed - no API token")
                self.coda = None
        except Exception as e:
            print(f"❌ Error initializing Coda: {e}")
            self.coda = None
        
        # Initialize tracking dictionaries
        self.active_standups = {}
        self.user_responses = {}
        
        # Track active standups and user responses
        self.health_check_responses = set()  # Track users who have responded to health checks
        self.standup_responses = set()  # Track users who have submitted standup responses today
        
        # Event deduplication
        self.processed_events = set()  # Track processed event IDs to prevent duplicates
        
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
        schedule.every().day.at(self.config['standup_time']).do(self.send_standup_to_all_users)
        schedule.every().day.at(self.config['reminder_time']).do(self.check_missing_responses)
        # Schedule daily health check to all users via DM
        schedule.every().day.at("09:00").do(self.send_health_check_to_all_users)
        
    def send_daily_standup(self):
        """Send the daily standup prompt message with hybrid interaction options."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🌞 *Good morning team! Time for the daily standup!*\n\n"
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
                                   f"<!channel> please respond by {self.config['response_deadline']}. Let's stay aligned! 💬"
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
        """Escalate blocker with detailed information to general channel."""
        try:
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
            
            # AI suggestions removed as requested
            ai_suggestions = ""
            
            # Sanitize KR name for button value (remove special characters that might cause issues)
            safe_kr_name = kr_name.replace(':', '_').replace(' ', '_').replace('-', '_')[:50]  # Limit length
            
            # Store mapping for later retrieval
            self.kr_name_mappings[safe_kr_name] = kr_name
            
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🚨 *Blocker Alert - {urgency_emoji} {urgency} Priority*\n\n"
                                   f"<@{user_id}> ({user_name}) is blocked and needs assistance!\n\n"
                                   f"*Blocker Details:*\n"
                                   f"• **Description:** {blocker_description}\n"
                                   f"• **KR:** {kr_name}\n"
                                   f"• **Urgency:** {urgency_emoji} {urgency}\n"
                                   f"• **Notes:** {notes if notes else 'None'}\n"
                                   f"• **Current KR Status:** {kr_status_info}{ai_suggestions}\n\n"
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
                                "value": f"help_{user_id}",
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
            }
            
            # Send to general channel (or specific escalation channel)
            escalation_channel = self.config.get('escalation_channel', 'general')
            response = self.client.chat_postMessage(
                channel=f"#{escalation_channel}",
                blocks=message["blocks"],
                text=f"🚨 Blocker Alert: {user_name} needs help with {kr_name}"
            )
            
            print(f"✅ Detailed blocker escalation sent to general channel for {user_name}")
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
                channel=f"#{self.config.get('escalation_channel', 'leads')}",
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
                                    # KR is finished - show completion message
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
                                    # KR is still in progress - show updated status
                                    self.client.chat_update(
                                        channel=channel_id,
                                        ts=message_ts,
                                        blocks=updated_blocks,
                                        text=f"🚨 Blocker Alert: {user_name} needs help with {kr_name} - Status: {kr_status_info}"
                                    )
                                    print(f"✅ KR '{kr_name}' status refreshed in original message")
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
            
            # Handle form input actions (static_select, plain_text_input, etc.)
            elif action_id in ['urgency_input', 'blocker_description_input', 'kr_name_input', 'notes_input', 'explanation_input']:
                # These are form input actions that don't need special handling
                # They are automatically handled by Slack's form system
                print(f"✅ Form input action received: {action_id}")
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
        """Reset daily prompt flags at midnight."""
        self.daily_prompts_sent['standup'] = False
        self.daily_prompts_sent['health_check'] = False
        self.standup_responses.clear()  # Reset standup responses for new day
        print("🔄 Daily prompt flags and standup responses reset for new day")

    def send_info_message(self, channel_id, user_id):
        """Send an info/help message to guide users on how to interact with the bot."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"👋 Hi <@{user_id}>! I'm your team's health check and standup bot.\n\nHere's how you can interact with me:"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": "🚨 *Need Help?*\nType `blocked` or `need help` to report a blocker"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "🔍 *Search KRs*\nType `kr [assignment name]` to search for Key Results"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": "📊 *Daily Standup*\nReply to my daily standup prompts with your updates"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "💚 *Health Check*\nReply to my health check prompts to share how you're feeling"
                            }
                        ]
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "💡 *Tip: I'll send you daily prompts automatically. Just reply to them when you receive them!*"
                            }
                        ]
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=channel_id,
                blocks=message["blocks"],
                text="Bot Info - How to interact with me"
            )
            
            print(f"✅ Info message sent to user {user_id}")
            return response['ts']
            
        except Exception as e:
            print(f"❌ Error sending info message: {e}")
            return None

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

# Global bot variable
bot = None

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
            response_data, status_code = bot.handle_button_click(payload)
            return jsonify(response_data), status_code
        
        # Handle form submissions (blocker details)
        if payload.get('type') == 'view_submission':
            print("🔍 DEBUG: Received view_submission event")
            print(f"🔍 DEBUG: Callback ID: {payload.get('view', {}).get('callback_id')}")
            if payload.get('view', {}).get('callback_id') == 'blocker_form':
                print("🔍 DEBUG: Processing blocker form submission")
                bot.handle_blocker_form_submission(payload)
                return jsonify({"response_action": "clear"}), 200
        
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
                
                # Skip bot messages to prevent processing our own messages
                if 'bot_id' in event or event.get('user') == 'U0912DJRNSF':  # bot user ID
                    print(f"🔍 DEBUG: Skipping bot message")
                    return jsonify({'status': 'ok'})
                
                # Check if this is a DM (channel starts with 'D')
                channel_id = event.get('channel', '')
                is_dm = channel_id.startswith('D')
                
                if is_dm:
                    print(f"🔍 DEBUG: This is a DM message")

                    # KR search: 'kr (assignment name)' - Check this FIRST and return immediately
                    text_lower = event.get('text', '').lower()
                    if text_lower.startswith('kr '):
                        print(f"🔍 DEBUG: Detected KR search request - ignoring all other prompts")
                        search_term = event.get('text', '').strip()[3:]
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

                    # Check for blocker phrases (will trigger for any message containing these words)
                    if any(phrase in text_lower for phrase in ["i'm blocked", "im blocked", "need help", "blocked", "help me"]):
                        print(f"🔍 DEBUG: Detected blocker/help phrase in DM, sending help prompt.")
                        # Get user info for name
                        user_info = bot.client.users_info(user=event['user'])
                        user_name = user_info['user']['real_name']
                        bot.send_help_followup(
                            user_id=event['user'],
                            standup_ts=event['ts'],
                            user_name=user_name,
                            channel=event.get('channel')
                        )
                        return jsonify({'status': 'help_prompt_sent'})

                    # For DMs, only process if this is a response to our standup prompt
                    # Check if this message is in a thread (reply to bot message)
                    # Note: Blocker requests are handled above and bypass this check
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
                    else:
                        print(f"🔍 DEBUG: Sending info message for casual DM")
                        # Send info message for casual messages
                        bot.send_info_message(event.get('channel'), event['user'])
                        return jsonify({'status': 'info_message_sent'})
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
                
                # For message.im events, only process if this is a response to our standup prompt
                thread_ts = event.get('thread_ts')
                if thread_ts:
                    print(f"🔍 DEBUG: Processing DM message as standup response (in thread)")
                    bot.handle_standup_response(
                        user_id=event['user'],
                        message_ts=event['ts'],
                        thread_ts=thread_ts,
                        text=event['text'],
                        channel_id=event.get('channel')
                    )
                else:
                    print(f"🔍 DEBUG: Sending info message for casual DM")
                    # Send info message for casual messages
                    bot.send_info_message(event.get('channel'), event['user'])
                    return jsonify({'status': 'info_message_sent'})
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

if __name__ == "__main__":
    import os
    import threading
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not getattr(BotConfig, 'FLASK_DEBUG', False):
        # Initialize bot only once
        bot = DailyStandupBot()
        
        # Start scheduler in a background thread
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        
        print("🤖 Daily Standup Bot Starting...")
        print(f"📅 Standup time: {bot.config['standup_time']}")
        print(f"📺 Channel: {bot.channel_id}")
        print(f"🚨 Escalation channel: #{bot.config.get('escalation_channel', 'leads')}")
        print(f"⏰ Reminder time: {bot.config['reminder_time']}")
        print("🔄 Hybrid workflow: Reactions + Thread replies")
        
        # Send initial prompts on startup
        print("📤 Sending initial prompts on startup...")
        
        # Get user list once to avoid rate limiting
        print("🔍 DEBUG: Getting list of all users for initial prompts...")
        users_response = bot.client.users_list()
        users = users_response['members']
        print(f"🔍 DEBUG: Found {len(users)} total users")
        
        # Send standup prompts
        bot.send_standup_to_all_users(users)
        
        # Add delay to avoid rate limiting
        print("⏳ Waiting 2 seconds to avoid rate limiting...")
        time.sleep(2)
        
        # Send health check prompts
        bot.send_health_check_to_all_users(users)
        
        print("🚀 Bot is running... (Press Ctrl+C to stop)")
        app.run(
            host=BotConfig.FLASK_HOST,
            port=BotConfig.FLASK_PORT,
            debug=False
        ) 