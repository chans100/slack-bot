import os
import time
import schedule
import re
import json
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from flask import Flask, request, jsonify
from config import BotConfig

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
        # Validate configuration
        BotConfig.validate_config()
        
        # Initialize Slack client
        self.client = WebClient(token=BotConfig.SLACK_BOT_TOKEN)
        self.channel_id = BotConfig.SLACK_CHANNEL_ID
        self.escalation_channel = BotConfig.SLACK_ESCALATION_CHANNEL
        
        # Load configuration
        self.config = BotConfig.get_config_dict()
        
        # Track active standups and responses
        self.active_standups = {}  # {message_ts: {timestamp, responses: {}}}
        self.user_responses = {}   # {user_id: {message_ts, response_data}}
        self.quick_responses = {}  # {user_id: {standup_ts, quick_status}}
        
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
        """
        Parse a standup response to extract key information.
        Returns a dict with parsed data or None if parsing fails.
        """
        text = text.lower().strip()
        
        # Extract "on track" status
        on_track_match = re.search(BotConfig.RESPONSE_PATTERNS['on_track'], text)
        on_track = on_track_match.group(1) if on_track_match else None
        
        # Extract blockers
        blockers_match = re.search(BotConfig.RESPONSE_PATTERNS['blockers'], text, re.IGNORECASE)
        blockers = blockers_match.group(1).strip() if blockers_match else None
        
        # Extract "today" work
        today_match = re.search(BotConfig.RESPONSE_PATTERNS['today_work'], text, re.IGNORECASE)
        today_work = today_match.group(1).strip() if today_match else None
        
        # Determine if there are actual blockers
        has_blockers = blockers and blockers.lower() not in BotConfig.NO_BLOCKERS_KEYWORDS
        
        return {
            'on_track': on_track,
            'has_blockers': has_blockers,
            'blockers': blockers if has_blockers else None,
            'today_work': today_work,
            'raw_text': text
        }
    
    def handle_standup_response(self, user_id, message_ts, thread_ts, text):
        """Handle a team member's detailed standup response in thread."""
        try:
            # Parse the response
            parsed = self.parse_standup_response(text)
            if not parsed:
                # Send helpful message if parsing fails
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=thread_ts,
                    text=f"<@{user_id}>, I couldn't parse your response. Please use the format:\n"
                         "• Today: [what you did]\n"
                         "• On Track: Yes/No\n"
                         "• Blockers: [any blockers or 'None']"
                )
                return
            
            # Get user info
            user_info = self.client.users_info(user=user_id)
            user_name = user_info['user']['real_name']
            
            # Store the response
            if thread_ts not in self.active_standups:
                self.active_standups[thread_ts] = {'responses': {}, 'quick_responses': {}}
            
            self.active_standups[thread_ts]['responses'][user_id] = {
                'parsed': parsed,
                'timestamp': datetime.now(),
                'user_name': user_name
            }
            
            # Determine next action based on response
            if parsed['on_track'] == 'yes' and not parsed['has_blockers']:
                # All good - acknowledge
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=thread_ts,
                    text=f"Thanks <@{user_id}>! You're on track. ✅"
                )
            else:
                # Needs follow-up - send help options
                self.send_followup_message(user_id, thread_ts, parsed)
                
        except SlackApiError as e:
            print(f"Error handling standup response: {e.response['error']}")
    
    def send_followup_message(self, user_id, thread_ts, parsed_data):
        """Send follow-up message for users with blockers or delays."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"<@{user_id}>, thanks for the detailed update! Since you're either not on track or facing a blocker, would you like help?\n\n"
                                   f"*Your status:*\n"
                                   f"• On Track: {parsed_data['on_track']}\n"
                                   f"• Blockers: {parsed_data['blockers'] or 'None'}\n\n"
                                   "React with one of the following:\n"
                                   f"• {self.config['escalation_emoji']} = Need help now\n"
                                   f"• {self.config['monitor_emoji']} = Can wait / just keeping team informed"
                        }
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=thread_ts,
                blocks=message["blocks"],
                text=f"Follow-up for <@{user_id}> - React for help options"
            )
            
            # Store the follow-up message for reaction tracking
            self.user_responses[user_id] = {
                'followup_ts': response['ts'],
                'thread_ts': thread_ts,
                'parsed_data': parsed_data,
                'type': 'detailed_followup'
            }
            
        except SlackApiError as e:
            print(f"Error sending followup message: {e.response['error']}")
    
    def handle_reaction(self, user_id, message_ts, reaction):
        """Handle reactions to follow-up messages."""
        try:
            if user_id not in self.user_responses:
                return
            
            user_data = self.user_responses[user_id]
            user_info = self.client.users_info(user=user_id)
            user_name = user_info['user']['real_name']
            
            if reaction == self.config['escalation_emoji']:
                # Escalate immediately
                if user_data.get('type') == 'help_request':
                    # Escalate help request
                    self.escalate_help_request(user_id, user_name, user_data)
                else:
                    # Escalate detailed followup
                    self.escalate_issue(user_id, user_name, user_data['parsed_data'])
                
                # Acknowledge escalation
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=user_data['thread_ts'],
                    text=f"<@{user_id}>, I've escalated your issue to the leads. They'll reach out soon! 🚨"
                )
                
            elif reaction == self.config['monitor_emoji']:
                # Acknowledge monitoring
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=user_data['thread_ts'],
                    text=f"Got it <@{user_id}>, we'll keep an eye on this. Let us know if it becomes urgent! 🚧"
                )
            
            # Clean up user data
            del self.user_responses[user_id]
            
        except SlackApiError as e:
            print(f"Error handling reaction: {e.response['error']}")
    
    def escalate_help_request(self, user_id, user_name, user_data):
        """Send escalation message for help requests."""
        try:
            escalation_text = (
                f"🚨 *Help Request Escalation* 🚨\n\n"
                f"<@{user_id}> ({user_name}) requested help via quick reaction.\n\n"
                f"⏰ Urgency: HIGH\n"
                f"📆 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"<!here> please reach out to <@{user_id}> to provide assistance."
            )
            
            self.client.chat_postMessage(
                channel=f"#{self.escalation_channel}",
                text=escalation_text
            )
            
            print(f"Escalated help request for user {user_name}")
            
        except SlackApiError as e:
            print(f"Error escalating help request: {e.response['error']}")
    
    def escalate_issue(self, user_id, user_name, parsed_data):
        """Send escalation message to leads channel."""
        try:
            escalation_text = BotConfig.ESCALATION_MESSAGE_TEMPLATE.format(
                user_id=user_id,
                user_name=user_name,
                on_track=parsed_data['on_track'],
                blockers=parsed_data['blockers'] or 'None',
                today_work=parsed_data['today_work'] or 'Not specified',
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            self.client.chat_postMessage(
                channel=f"#{self.escalation_channel}",
                text=escalation_text
            )
            
            print(f"Escalated issue for user {user_name}")
            
        except SlackApiError as e:
            print(f"Error escalating issue: {e.response['error']}")
    
    def check_missing_responses(self):
        """Check for team members who haven't responded to the latest standup."""
        try:
            # Get channel members
            channel_info = self.client.conversations_members(channel=self.channel_id)
            channel_members = channel_info['members']
            
            # Find the most recent standup
            if not self.active_standups:
                return
            
            latest_standup_ts = max(self.active_standups.keys())
            standup_data = self.active_standups[latest_standup_ts]
            
            # Find members who haven't responded (either quick or detailed)
            responded_users = set(standup_data['responses'].keys()) | set(standup_data.get('quick_responses', {}).keys())
            missing_users = [user for user in channel_members if user not in responded_users]
            
            if missing_users:
                # Send reminder
                missing_mentions = " ".join([f"<@{user}>" for user in missing_users])
                self.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=latest_standup_ts,
                    text=f"Reminder: {missing_mentions} please respond to the daily standup! ⏰\n\n"
                         "You can:\n"
                         "• React with ✅/⚠️/🚨 for quick status\n"
                         "• Reply in thread for detailed update"
                )
                
        except SlackApiError as e:
            print(f"Error checking missing responses: {e.response['error']}")

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
        
        # Handle message events (standup responses)
        if payload.get('type') == 'event_callback':
            event = payload['event']
            
            if event['type'] == 'message' and 'thread_ts' in event:
                # This is a reply in a thread (standup response)
                bot.handle_standup_response(
                    user_id=event['user'],
                    message_ts=event['ts'],
                    thread_ts=event['thread_ts'],
                    text=event['text']
                )
            
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

def run_scheduler():
    """Run the scheduled tasks."""
    # Schedule daily standup
    schedule.every().day.at(bot.config["standup_time"]).do(bot.send_daily_standup)
    
    # Schedule reminder check
    schedule.every().day.at(BotConfig.REMINDER_TIME).do(bot.check_missing_responses)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    print("🤖 Daily Standup Bot Starting...")
    print(f"📅 Standup time: {bot.config['standup_time']}")
    print(f"📺 Channel: {bot.channel_id}")
    print(f"🚨 Escalation channel: #{bot.escalation_channel}")
    print(f"⏰ Reminder time: {BotConfig.REMINDER_TIME}")
    print("🔄 Hybrid workflow: Reactions + Thread replies")
    
    # Send initial test message
    print("📤 Sending test standup message...")
    bot.send_daily_standup()
    
    # Start the scheduler in a separate thread
    import threading
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # Start the Flask app
    print("🚀 Bot is running... (Press Ctrl+C to stop)")
    app.run(
        host=BotConfig.FLASK_HOST,
        port=BotConfig.FLASK_PORT,
        debug=BotConfig.FLASK_DEBUG
    ) 