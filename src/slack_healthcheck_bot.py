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
from .scheduling import SchedulingManager
from .standup_management import StandupManager
from .health_check_management import HealthCheckManager
from .blocker_management import BlockerManager
from .role_management import RoleManager
from .command_handling import CommandHandler
from .event_handling import EventHandler
from .kr_management import KRManager
from .utilities import Utilities, get_est_time
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
        
        # Initialize managers
        self.scheduler = SchedulingManager(self)
        self.standup_manager = StandupManager(self)
        self.health_check_manager = HealthCheckManager(self)
        self.blocker_manager = BlockerManager(self)
        self.role_manager = RoleManager(self)
        self.command_handler = CommandHandler(self)
        self.event_handler = EventHandler(self)
        self.kr_manager = KRManager(self)
        self.utilities = Utilities(self)
        
        # Track responses to prevent duplicates
        self.health_check_responses = set()
        self.processed_events = set()
        
        # Initialize tracked blockers for follow-up
        self.tracked_blockers = {}
        
        # Initialize follow-up tracking to prevent duplicates
        self.last_followup_sent = {}
        
        # Initialize tracking dictionaries
        self.active_standups = {}
        self.user_responses = {}
        
        # Track active standups and user responses
        self.standup_responses = set()  # Track users who have submitted standup responses today
        
        # Track help offers to prevent duplicates
        self.help_offers = set()  # Track help offers by message_ts
        
        # Track daily prompts to ensure they only send once
        self.daily_prompts_sent = {
            'standup': False,
            'health_check': False
        }
        
        # Send initial digests
        self.scheduler.send_daily_blocker_digest()
        self.scheduler.send_daily_standup_digest()
        
        self._user_list_cache = None
        self._user_list_cache_time = 0

        # Add this at the top of the file or in the class __init__
        self.BLOCKER_FOLLOWUP_DELAY_HOURS = 24  # Change this value to adjust the follow-up delay
    
    # Delegate methods to appropriate managers
    def send_daily_standup(self):
        return self.standup_manager.send_daily_standup()
    
    def handle_quick_reaction(self, user_id, standup_ts, reaction):
        return self.standup_manager.handle_quick_reaction(user_id, standup_ts, reaction)
    
    def parse_standup_response(self, text):
        return self.standup_manager.parse_standup_response(text)
    
    def handle_standup_response(self, user_id, message_ts, thread_ts, text, channel_id=None):
        return self.standup_manager.handle_standup_response(user_id, message_ts, thread_ts, text, channel_id)
    
    def send_followup_message(self, user_id, thread_ts, parsed_data, channel_id=None, ai_analysis=""):
        return self.standup_manager.send_followup_message(user_id, thread_ts, parsed_data, channel_id, ai_analysis)
    
    def send_help_followup(self, user_id, standup_ts, user_name, channel=None):
        return self.blocker_manager.send_help_followup(user_id, standup_ts, user_name, channel)
    
    def handle_blocker_form_submission(self, payload):
        return self.blocker_manager.handle_blocker_form_submission(payload)
    
    def escalate_blocker_with_details(self, user_id, user_name, blocker_description, kr_name, urgency, notes):
        return self.blocker_manager.escalate_blocker_with_details(user_id, user_name, blocker_description, kr_name, urgency, notes)
    
    def handle_resolution_modal_submission(self, payload):
        return self.blocker_manager.handle_resolution_modal_submission(payload)
    
    def send_health_check_to_dm(self, user_id):
        return self.health_check_manager.send_health_check_to_dm(user_id)
    
    def send_test_health_check(self):
        return self.health_check_manager.send_test_health_check()
    
    def send_standup_to_dm(self, user_id):
        return self.standup_manager.send_standup_to_dm(user_id)
    
    def handle_commands(self, user_id, text, channel_id):
        return self.command_handler.handle_commands(user_id, text, channel_id)
    
    def send_info_message(self, channel_id, user_id, mode="user"):
        return self.command_handler.send_info_message(channel_id, user_id, mode)
    
    def get_user_roles(self, user_id):
        return self.role_manager.get_user_roles(user_id)
    
    def get_users_by_role(self, role):
        return self.role_manager.get_users_by_role(role)
    
    def has_role(self, user_id, role):
        return self.role_manager.has_role(user_id, role)
    
    def send_role_based_message(self, role, message, channel_override=None):
        return self.role_manager.send_role_based_message(role, message, channel_override)
    
    def escalate_by_hierarchy(self, issue_type, message, additional_context=""):
        return self.role_manager.escalate_by_hierarchy(issue_type, message, additional_context)
    
    def get_kr_assignees(self, kr_name):
        return self.role_manager.get_kr_assignees(kr_name)
    
    def get_slack_user_list(self, cache_seconds=600):
        return self.utilities.get_slack_user_list(cache_seconds)
    
    def get_thread_url(self, channel_id, thread_ts):
        return self.utilities.get_thread_url(channel_id, thread_ts)
    
    def get_kr_from_message(self, message):
        return self.utilities.get_kr_from_message(message)
    
    def get_accessible_channels(self):
        return self.utilities.get_accessible_channels()
    
    def send_completion_message_to_accessible_channel(self, completion_message):
        return self.utilities.send_completion_message_to_accessible_channel(completion_message)
    
    def handle_mentor_no_response(self, user_id, channel_id, message_ts):
        return self.utilities.handle_mentor_no_response(user_id, channel_id, message_ts)
    
    def send_mentor_check(self, user_id, standup_ts, user_name, request_type, channel, search_term=None):
        return self.utilities.send_mentor_check(user_id, standup_ts, user_name, request_type, channel, search_term)
    
    def _send_simple_status_update(self, channel_id, message_ts, kr_name, kr_status_info, safe_kr_name):
        return self.utilities._send_simple_status_update(channel_id, message_ts, kr_name, kr_status_info, safe_kr_name)
    
    def get_kr_progress_from_coda(self, kr_name):
        return self.utilities.get_kr_progress_from_coda(kr_name)
    
    def generate_kr_explanation(self, kr_name, owner, status, definition_of_done=None):
        return self.kr_manager.generate_kr_explanation(kr_name, owner, status, definition_of_done)
    
    # Role management delegation methods
    def _handle_role_command(self, user_id, full_text, channel_id):
        return self.role_manager._handle_role_command(user_id, full_text, channel_id)
    
    def _add_user_role(self, user_mention, role, channel_id):
        return self.role_manager._add_user_role(user_mention, role, channel_id)
    
    def _remove_user_role(self, user_mention, role, channel_id):
        return self.role_manager._remove_user_role(user_mention, role, channel_id)
    
    def _list_users_by_role(self, role, channel_id):
        return self.role_manager._list_users_by_role(role, channel_id)
    
    # Blocker management delegation methods
    def track_blocker_for_followup(self, user_id, user_name, blocker_description, kr_name, urgency, notes, escalation_ts, channel_id=None, message_ts=None):
        return self.blocker_manager.track_blocker_for_followup(user_id, user_name, blocker_description, kr_name, urgency, notes, escalation_ts, channel_id, message_ts)
    
    def check_blocker_followups(self):
        return self.blocker_manager.check_blocker_followups()
    
    def send_blocker_followup(self, blocker_info):
        return self.blocker_manager.send_blocker_followup(blocker_info)
    
    # Event handling delegation methods
    def handle_reaction(self, user_id, message_ts, reaction):
        return self.event_handler.handle_reaction(user_id, message_ts, reaction)
    
    def handle_button_click(self, payload):
        return self.event_handler.handle_button_click(payload)
    
    # Scheduling delegation methods
    def reset_daily_prompts(self):
        return self.scheduler.reset_daily_prompts()
    
    def check_missing_responses(self):
        return self.scheduler.check_missing_responses()
    
    def send_standup_to_all_users(self, users=None):
        return self.scheduler.send_standup_to_all_users(users)
    
    def send_health_check_to_all_users(self, users=None):
        return self.scheduler.send_health_check_to_all_users(users)
    
    def send_daily_blocker_digest(self):
        return self.scheduler.send_daily_blocker_digest()
    
    def send_daily_standup_digest(self):
        return self.scheduler.send_daily_standup_digest()
    
    def clear_followup_tracking(self):
        return self.scheduler.clear_followup_tracking()
    
    # Legacy methods that need to be kept for compatibility
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

# Initialize bot instance
bot = DailyStandupBot()

# Flask routes
@app.route('/slack/events', methods=['POST'])
def handle_events():
    """Handle Slack events."""
    try:
        data = request.get_json()
        
        # Handle URL verification
        if data.get('type') == 'url_verification':
            return jsonify({'challenge': data.get('challenge')})
        
        # Handle events
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            event_type = event.get('type')
            
            if event_type == 'message':
                # Handle message events
                user_id = event.get('user')
                text = event.get('text', '')
                channel_id = event.get('channel')
                message_ts = event.get('ts')
                thread_ts = event.get('thread_ts')
                
                # Skip bot messages
                if user_id == 'U0912DJRNSF':  # Bot user ID
                    return jsonify({'status': 'ok'})
                
                # Handle commands
                if text.startswith('/'):
                    bot.handle_commands(user_id, text, channel_id)
                
                # Handle standup responses in threads
                elif thread_ts and text:
                    bot.handle_standup_response(user_id, message_ts, thread_ts, text, channel_id)
            
            elif event_type == 'reaction_added':
                # Handle reaction events
                user_id = event.get('user')
                message_ts = event.get('item', {}).get('ts')
                reaction = event.get('reaction')
                
                # Skip bot reactions
                if user_id == 'U0912DJRNSF':  # Bot user ID
                    return jsonify({'status': 'ok'})
                
                # Handle quick reactions to standup messages
                if message_ts in bot.active_standups:
                    bot.handle_quick_reaction(user_id, message_ts, reaction)
                else:
                    # Handle other reactions
                    bot.handle_reaction(user_id, message_ts, reaction)
            
            elif event_type == 'app_mention':
                # Handle app mentions
                user_id = event.get('user')
                text = event.get('text', '')
                channel_id = event.get('channel')
                
                # Handle commands in mentions
                if any(cmd in text.lower() for cmd in ['/kr', '/checkin', '/blocked', '/health', '/role', '/help']):
                    bot.handle_commands(user_id, text, channel_id)
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        print(f"Error handling events: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/slack/command', methods=['POST'])
def handle_slash_commands():
    """Handle slash commands."""
    try:
        data = request.form.to_dict()
        user_id = data.get('user_id')
        text = data.get('text', '')
        channel_id = data.get('channel_id')
        
        # Handle different commands
        command = text.split()[0].lower() if text.strip() else ''
        
        if command == '/kr':
            # Process KR search command
            def process_kr_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Parse search term
                    parts = text.strip().split()
                    if len(parts) < 2:
                        bot.client.chat_postMessage(
                            channel=user_id,
                            text="❌ Usage: `/kr [search term]`"
                        )
                        return
                    
                    search_term = ' '.join(parts[1:])
                    
                    # Check if user has reached out to mentor
                    bot.send_mentor_check(user_id, None, "Unknown", "kr", user_id, search_term)
                    
                except Exception as e:
                    print(f"❌ Error in background KR processing: {e}")
            
            thread = threading.Thread(target=process_kr_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing KR search... Check your DM for results."
            
            return jsonify({
                "response_type": "ephemeral",
                "text": response_text
            })
        
        elif command == '/checkin':
            # Process checkin command
            def process_checkin_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Send standup prompt to user
                    bot.send_standup_to_dm(user_id)
                    
                except Exception as e:
                    print(f"❌ Error in background checkin processing: {e}")
            
            thread = threading.Thread(target=process_checkin_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing checkin request... Check your DM for the standup prompt."
            
            return jsonify({
                "response_type": "ephemeral",
                "text": response_text
            })
        
        elif command == '/blocked':
            # Process blocked command
            def process_blocked_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Get user info
                    user_info = bot.client.users_info(user=user_id)
                    username = user_info['user']['real_name']
                    
                    # Check if user has reached out to mentor
                    bot.send_mentor_check(user_id, None, username, "blocker", user_id)
                    
                except Exception as e:
                    print(f"❌ Error in background blocked processing: {e}")
            
            thread = threading.Thread(target=process_blocked_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing blocked request... Check your DM for the blocker form."
            
            return jsonify({
                "response_type": "ephemeral",
                "text": response_text
            })
        
        elif command == '/health':
            # Process health command
            def process_health_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Send health check to user
                    bot.send_health_check_to_dm(user_id)
                    
                except Exception as e:
                    print(f"❌ Error in background health processing: {e}")
            
            thread = threading.Thread(target=process_health_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing health check request... Check your DM for the health check."
            
            return jsonify({
                "response_type": "ephemeral",
                "text": response_text
            })
        
        elif command == '/role':
            # Process role command
            if not bot.has_role(user_id, 'admin'):
                return jsonify({
                    "response_type": "ephemeral",
                    "text": "❌ You need admin privileges to manage roles."
                })
            
            # Respond immediately and process in background to avoid timeout
            def process_role_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Handle role command
                    bot._handle_role_command(user_id, text, user_id)
                    
                except Exception as e:
                    print(f"❌ Error in background role processing: {e}")
            
            thread = threading.Thread(target=process_role_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing role command... Check your DM for results."
            
            return jsonify({
                "response_type": "ephemeral",
                "text": response_text
            })
        
        elif command == '/rolelist':
            # Process rolelist command
            if not bot.has_role(user_id, 'admin'):
                return jsonify({
                    "response_type": "ephemeral",
                    "text": "❌ You need admin privileges to view role lists."
                })
            
            # Respond immediately and process in background to avoid timeout
            def process_rolelist():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Get all users and their roles
                    all_users = bot.get_slack_user_list()
                    role_summary = {}
                    
                    for user_id in all_users:
                        try:
                            user_info = bot.client.users_info(user=user_id)
                            user_name = user_info['user']['real_name']
                            user_roles = bot.get_user_roles(user_id)
                            
                            if user_roles:
                                for role in user_roles:
                                    if role not in role_summary:
                                        role_summary[role] = []
                                    role_summary[role].append(f"• {user_name} (<@{user_id}>)")
                        except Exception as e:
                            print(f"❌ Error getting user info for {user_id}: {e}")
                            continue
                    
                    # Create summary message
                    summary_text = "📋 *Role Summary:*\n\n"
                    
                    if role_summary:
                        for role, users in sorted(role_summary.items()):
                            summary_text += f"**{role.title()}** ({len(users)} users):\n"
                            summary_text += "\n".join(users) + "\n\n"
                    else:
                        summary_text += "No users have assigned roles.\n\n"
                    
                    summary_text += "💡 Use `/role add @user role` to assign roles."
                    
                    # Send to user's DM
                    bot.client.chat_postMessage(
                        channel=user_id,
                        text=summary_text
                    )
                    
                except Exception as e:
                    print(f"❌ Error in background rolelist processing: {e}")
            
            thread = threading.Thread(target=process_rolelist)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing role list... Check your DM for results."
            
            return jsonify({
                "response_type": "ephemeral",
                "text": response_text
            })
        
        elif command == '/help':
            # Respond immediately and process in background to avoid timeout
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