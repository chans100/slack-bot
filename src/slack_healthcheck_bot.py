import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import schedule
import re
import json
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from flask import Flask, request, jsonify
from config import BotConfig
from mongodb_service import MongoDBService

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
        required_keys = ['slack_bot_token', 'slack_channel_id', 'mongodb_uri', 'mongodb_db_name']
        missing_keys = [key for key in required_keys if key not in self.config]
        if missing_keys:
            raise ValueError(f"Missing required configuration keys: {missing_keys}")
        
        # Initialize Slack client
        self.client = WebClient(token=self.config['slack_bot_token'])
        self.channel_id = self.config['slack_channel_id']
        
        # Initialize MongoDB with better error handling
        print("🔌 Initializing MongoDB connection...")
        try:
            self.mongodb = MongoDBService(self.config['mongodb_uri'], self.config['mongodb_db_name'])
            if self.mongodb.client is None:
                print("❌ MongoDB connection failed during initialization")
            else:
                print("✅ MongoDB connection successful")
        except Exception as e:
            print(f"❌ Error initializing MongoDB: {e}")
            self.mongodb = None
        
        # Initialize tracking dictionaries
        self.active_standups = {}
        self.user_responses = {}
        
        # Track active standups and user responses
        self.health_check_responses = set()  # Track users who have responded to health checks
        
        # Event deduplication
        self.processed_events = set()  # Track processed event IDs to prevent duplicates
        
        # Send startup test messages
        print("📤 Sending test health check message...")
        self.send_test_health_check()
        
        print("📤 Sending test standup message...")
        self.send_test_standup()
        
        # Schedule daily standup
        schedule.every().day.at(self.config['standup_time']).do(self.send_daily_standup)
        schedule.every().day.at(self.config['reminder_time']).do(self.check_missing_responses)
        
        print("🤖 Daily Standup Bot Starting...")
        print(f"📅 Standup time: {self.config['standup_time']}")
        print(f"📺 Channel: {self.channel_id}")
        print(f"🚨 Escalation channel: #{self.config.get('escalation_channel', 'leads')}")
        print(f"⏰ Reminder time: {self.config['reminder_time']}")
        print(f"🔄 Hybrid workflow: Reactions + Thread replies")
        
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
                                   "• Blockers: [any blockers or 'None']\n\n"
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
    
    def send_help_followup(self, user_id, standup_ts, user_name):
        """Send follow-up for users who need help."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"<@{user_id}>, I see you need help! 🚨\n\n"
                                   "Please reply in this thread with more details:\n"
                                   "• What's blocking you?\n"
                                   "• How urgent is this?\n"
                                   "• Who might be able to help?\n\n"
                                   "Or react to this message:\n"
                                   f"• {self.config['escalation_emoji']} = Escalate to leads now\n"
                                   f"• {self.config['monitor_emoji']} = Just keeping team informed"
                        }
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=standup_ts,
                blocks=message["blocks"],
                text=f"Help follow-up for <@{user_id}>"
            )
            
            # Store for reaction tracking
            self.user_responses[user_id] = {
                'followup_ts': response['ts'],
                'thread_ts': standup_ts,
                'type': 'help_request',
                'user_name': user_name
            }
            
        except SlackApiError as e:
            print(f"Error sending help followup: {e.response['error']}")
    
    def parse_standup_response(self, text):
        """Parse standup response text: 1st line = today, 2nd = on_track, 3rd = blockers."""
        lines = [l.strip().lower() for l in text.strip().split('\n') if l.strip()]
        parsed = {
            'today': lines[0] if len(lines) > 0 else '',
            'on_track': lines[1] if len(lines) > 1 else '',
            'blockers': lines[2] if len(lines) > 2 else ''
        }
        return parsed

    def handle_standup_response(self, user_id, message_ts, thread_ts, text):
        """Handle standup response in thread."""
        try:
            # Check if this specific message has already been processed
            try:
                if self.mongodb.check_message_processed(message_ts):
                    print(f"⚠️ Message {message_ts} already processed, skipping")
                    return
            except Exception as e:
                print(f"⚠️ Error checking message processing status: {e}")
            
            # Get user info
            user_info = self.client.users_info(user=user_id)
            user_name = user_info['user']['real_name']
            
            # Parse the response
            parsed_data = self.parse_standup_response(text)
            
            # Store in MongoDB with better error handling
            print("📝 Attempting to store standup response in MongoDB")
            try:
                if self.mongodb.collection is None:
                    print("❌ MongoDB collection is None - connection issue")
                else:
                    result = self.mongodb.store_response(user_id, user_name, text, self.channel_id, message_ts, thread_ts)
                    if result:
                        print("✅ Standup response stored in MongoDB successfully")
                    else:
                        print("❌ Failed to store response in MongoDB")
            except Exception as e:
                print(f"❌ Error storing response: {e}")
                print(f"❌ MongoDB client status: {self.mongodb.client is not None}")
                print(f"❌ MongoDB collection status: {self.mongodb.collection is not None}")
            
            # Mark this message as processed
            try:
                self.mongodb.mark_message_processed(message_ts, user_id, thread_ts)
                print("✅ Message marked as processed")
            except Exception as e:
                print(f"❌ Error marking message as processed: {e}")
            
            # Check if user needs follow-up
            needs_followup = (
                parsed_data.get('on_track', '').lower() in ['no', 'false'] or
                parsed_data.get('blockers', '').lower() in ['yes', 'true']
            )
            
            if needs_followup:
                # Check if we've already sent a followup to this user in this thread
                try:
                    if not self.mongodb.check_followup_sent(user_id, thread_ts):
                        self.send_followup_message(user_id, thread_ts, parsed_data)
                    else:
                        print(f"⚠️ Followup already sent to {user_id} in thread {thread_ts}")
                except Exception as e:
                    print(f"❌ Error checking followup status: {e}")
                    # Send followup anyway if we can't check
                    self.send_followup_message(user_id, thread_ts, parsed_data)
            else:
                # Send positive acknowledgment
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=thread_ts,
                    text=f"Great job <@{user_id}>! You're on track and have no blockers. Keep up the excellent work! 🎉"
                )
                
        except SlackApiError as e:
            print(f"Error handling standup response: {e.response['error']}")

    def send_followup_message(self, user_id, thread_ts, parsed_data):
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
                            "text": f"<@{user_id}>, thanks for the detailed update! :handshake: Since you're either not on track or facing a blocker, would you like help?\n\n*Your status:* :bar_chart:\n• On Track: {on_track_display}\n• Blockers: {blockers_display}\n\nReact with one of the following:\n• :sos: = Need help now\n• :clock4: = Can wait / just keeping team informed"
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
                                "action_id": "escalate_help",
                                "style": "danger"
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
            
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=thread_ts,
                blocks=message["blocks"],
                text=f"Follow-up for <@{user_id}> - React for help options"
            )
            
            # Store followup message in MongoDB
            try:
                self.mongodb.store_followup_sent(user_id, thread_ts, response['ts'])
                print(f"✅ Followup message saved to MongoDB: {response['ts']}")
            except Exception as e:
                print(f"❌ Error saving followup to MongoDB: {e}")
            
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
                self.escalate_help_request(user_id, user_data['user_name'], user_data)
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

    def escalate_help_request(self, user_id, user_name, user_data):
        """Escalate help request to leads channel."""
        try:
            # Send to escalation channel
            escalation_message = f"🚨 *Help Request Escalated*\n\n<@{user_id}> needs immediate assistance.\n\n*Context:*\n• Thread: {self.get_thread_url(self.channel_id, user_data['thread_ts'])}\n• User: {user_name}\n• Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            self.client.chat_postMessage(
                channel=f"#{self.config.get('escalation_channel', 'leads')}",
                text=escalation_message
            )
            
            # Acknowledge escalation
            self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=user_data['thread_ts'],
                text=f"Got it <@{user_id}>, I've escalated this to the team leads! 🚨"
            )
            
            # Clean up
            del self.user_responses[user_id]
            
        except SlackApiError as e:
            print(f"Error escalating help request: {e.response['error']}")

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
            action = payload['actions'][0]['value']
            action_id = payload['actions'][0]['action_id']
            message_ts = payload['message']['ts']
            channel_id = payload['channel']['id']
            print(f"User {username} ({user}) clicked {action}")
            
            # Handle health check buttons
            if action_id in ['great', 'okay', 'not_great']:
                # Check if user has already responded to this health check
                response_key = f"{user}_{message_ts}"
                if response_key in self.health_check_responses:
                    print(f"❌ User {username} already responded to health check")
                    return {"response_action": "errors", "errors": ["User already responded"]}, 200
                
                # Store response and mark user as responded
                self.mongodb.store_response(user, username, action, channel_id, message_ts)
                self.health_check_responses.add(response_key)
                
                # Send response in thread
                responses = {
                    'great': '😊 Great to hear you\'re doing well!',
                    'okay': '😐 Thanks for letting us know. Hope things get better!',
                    'not_great': '😔 Sorry to hear that. Is there anything we can do to help?'
                }
                response_text = responses.get(action, 'Thanks for your response!')
                thread_response = self.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text=response_text
                )
                print(f"✅ Response stored with ID: {thread_response['ts']}")
                print(f"Response sent successfully: {thread_response['ts']}")
                
                return {"response_action": "clear"}, 200
            
            # Handle follow-up buttons
            elif action_id in ['escalate_help', 'monitor_issue']:
                if user in self.user_responses:
                    user_data = self.user_responses[user]
                    user_name = user_data['user_name']
                    
                    if action_id == 'escalate_help':
                        # Try to escalate to leads channel
                        try:
                            escalation_message = f"🚨 *Help Request Escalated*\n\n<@{user}> needs immediate assistance.\n\n*Context:*\n• Thread: {self.get_thread_url(channel_id, user_data['thread_ts'])}\n• User: {user_name}\n• Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            
                            self.client.chat_postMessage(
                                channel=f"#{self.config.get('escalation_channel', 'leads')}",
                                text=escalation_message
                            )
                            print(f"✅ Escalated to leads channel for user {user}")
                        except Exception as e:
                            print(f"❌ Error sending escalation: {e}")
                        
                        # Also ping general channel
                        try:
                            general_message = f"🚨 *Team Alert: Immediate assistance needed!*\n\n<@{user}> needs help right now. Please check the standup thread and offer support if you can! :sos:"
                            self.client.chat_postMessage(
                                channel="general",
                                text=general_message
                            )
                            print(f"📢 General channel pinged for user {user}")
                        except Exception as e:
                            print(f"❌ Error pinging general channel: {e}")
                        
                        # Acknowledge escalation
                        self.client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=user_data['thread_ts'],
                            text=f"Got it <@{user}>, I've escalated this to the team leads and pinged the general channel for immediate assistance! 🚨"
                        )
                        
                    elif action_id == 'monitor_issue':
                        # Acknowledge monitoring
                        self.client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=user_data['thread_ts'],
                            text=f"Got it <@{user}>, we'll keep an eye on this. Please keep your mentor informed of any updates! 🚧"
                        )
                    
                    # Log the follow-up response
                    response_data = {
                        'user_id': user,
                        'username': user_name,
                        'action': action_id,
                        'response': 'monitor' if action_id == 'monitor_issue' else 'escalate',
                        'channel_id': channel_id,
                        'message_ts': message_ts,
                        'thread_ts': user_data['thread_ts'],
                        'timestamp': datetime.now().isoformat(),
                        'type': 'followup_response'
                    }
                    self.mongodb.store_response(user, user_name, action_id, channel_id, message_ts, user_data['thread_ts'])
                    print(f"✅ Follow-up response logged: {action_id} by {user_name}")
                    
                    # Clean up user data
                    del self.user_responses[user]
                    
                    return {"response_action": "clear"}, 200
                else:
                    print(f"❌ No user data found for {user}")
                    return {"response_action": "errors", "errors": ["No user data found"]}, 400
            
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
                            "text": "Good morning team! :sun_with_face: Time for the daily standup!\nPlease reply to this thread with:\n\n1. What did you do today?\n2. Are you on track to meet your goals? (Yes/No)\n3. Any blockers?\n <!channel> please respond by 4:30 PM. Let's stay aligned! :speech_balloon:"
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

# Initialize bot
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
        
        # Handle message events (standup responses)
        if payload.get('type') == 'event_callback':
            event = payload['event']
            
            if event['type'] == 'message' and 'thread_ts' in event:
                # Skip bot messages to prevent processing our own messages
                if 'bot_id' in event or event.get('user') == 'U0912DJRNSF':  # bot user ID
                    return jsonify({'status': 'ok'})
                
                # Check if this is a response to a followup message (not the original standup)
                thread_ts = event['thread_ts']
                is_followup_response = False
                
                # Check if this thread_ts corresponds to a followup message
                for user_id, user_data in bot.user_responses.items():
                    if user_data.get('thread_ts') == thread_ts:
                        is_followup_response = True
                        break
                
                # Only process as standup response if it's not a followup response
                if not is_followup_response:
                    # This is a reply in a thread (standup response)
                    bot.handle_standup_response(
                        user_id=event['user'],
                        message_ts=event['ts'],
                        thread_ts=event['thread_ts'],
                        text=event['text']
                    )
                else:
                    print(f"⚠️ Ignoring response to followup message from user {event['user']}")
            
            elif event['type'] == 'reaction_added':
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
        
        return jsonify({"text": "OK"})
        
    except Exception as e:
        print(f"Error handling event: {str(e)}")
        return jsonify({"text": "Error processing event"}), 500

if __name__ == "__main__":
    print("🤖 Daily Standup Bot Starting...")
    print(f"📅 Standup time: {bot.config['standup_time']}")
    print(f"📺 Channel: {bot.channel_id}")
    print(f"🚨 Escalation channel: #{bot.config.get('escalation_channel', 'leads')}")
    print(f"⏰ Reminder time: {bot.config['reminder_time']}")
    print("🔄 Hybrid workflow: Reactions + Thread replies")
    
    # Start the Flask app
    print("🚀 Bot is running... (Press Ctrl+C to stop)")
    app.run(
        host=BotConfig.FLASK_HOST,
        port=BotConfig.FLASK_PORT,
        debug=BotConfig.FLASK_DEBUG
    ) 