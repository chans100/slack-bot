import os
import time
import schedule
import json
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
import hmac
import hashlib
import base64
from pymongo import MongoClient
from mongodb_service import MongoDBService

# Load environment variables from .env
load_dotenv(".env")

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Slack signing secret for request verification
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")

def verify_slack_request(request):
    """Verify that the request is from Slack"""
    if not SLACK_SIGNING_SECRET:
        print("Warning: No signing secret configured, skipping verification")
        return True
    
    try:
        # Get the signature and timestamp from headers
        signature = request.headers.get('X-Slack-Signature', '')
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        
        if not signature or not timestamp:
            return False
        
        # Get the request body
        body = request.get_data()
        
        # Create the signature base string
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        
        # Create the expected signature
        expected_signature = 'v0=' + hmac.new(
            SLACK_SIGNING_SECRET.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        print(f"Error verifying request: {e}")
        return False

class SlackHealthcheckBot:
    def __init__(self):
        self.client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
        self.channel_id = os.environ.get("SLACK_CHANNEL_ID")
        self.mongodb = MongoDBService()
        self.recent_responses = {}  # Track recent responses to prevent spam
        self.bot_user_id = None  # Cache bot's own user ID
        
    def get_bot_user_id(self):
        """Get and cache the bot's own user ID"""
        if self.bot_user_id is None:
            try:
                auth_test = self.client.auth_test()
                self.bot_user_id = auth_test['user_id']
                print(f"Bot user ID: {self.bot_user_id}")
            except SlackApiError as e:
                print(f"Error getting bot user ID: {e.response['error']}")
                self.bot_user_id = "unknown"
        return self.bot_user_id

    def is_bot_message(self, event):
        """Check if a message is from the bot itself"""
        # Check if message has bot_id
        if event.get('bot_id'):
            return True
            
        # Check if message is from bot user
        if event.get('user') == self.get_bot_user_id():
            return True
            
        # Check if message contains bot-specific text patterns
        message_text = event.get('text', '').lower()
        bot_patterns = [
            'follow-up for',
            'react for help options',
            'thanks for the detailed update',
            'would you like help',
            'react with one of the following'
        ]
        
        if any(pattern in message_text for pattern in bot_patterns):
            return True
            
        # Check if message has bot_profile
        if event.get('bot_profile'):
            return True
            
        return False

    def send_healthcheck_message(self):
        try:
            # Create a message with a healthcheck prompt
            message = {
                "channel": self.channel_id,
                "text": "Daily Health Check",
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
                                "text": {
                                    "type": "plain_text",
                                    "text": ":blush: Great",
                                    "emoji": True
                                },
                                "value": "great",
                                "action_id": "great"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":neutral_face: Okay",
                                    "emoji": True
                                },
                                "value": "okay",
                                "action_id": "okay"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":pensive: Not Great",
                                    "emoji": True
                                },
                                "value": "not_great",
                                "action_id": "not_great"
                            }
                        ]
                    }
                ]
            }
            
            response = self.client.chat_postMessage(**message)
            print(f"Message sent successfully: {response['ts']}")
            return response['ts']
        except SlackApiError as e:
            print(f"Error sending message: {e.response['error']}")
            return None
    
    def send_standup_message(self):
        try:
            # Create a message with a standup prompt
            message = {
                "channel": self.channel_id,
                "text": "Daily Standup",
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
            
            response = self.client.chat_postMessage(**message)
            print(f"Standup message sent successfully: {response['ts']}")
            return response['ts']
        except SlackApiError as e:
            print(f"Error sending standup message: {e.response['error']}")
            return None
    
    def handle_button_click(self, payload):
        try:
            print("Received button click payload:", payload)  # Debug log
            
            # Get the user who clicked the button
            user = payload['user']['id']
            username = payload['user'].get('name', payload['user'].get('username', 'Unknown'))
            action = payload['actions'][0]['value']
            message_ts = payload['message']['ts']
            channel_id = payload['channel']['id']
            
            print(f"User {username} ({user}) clicked {action}")  # Debug log
            
            # Store the response in MongoDB
            self.mongodb.store_response(user, username, action, channel_id, message_ts)
            
            # ACKNOWLEDGE IMMEDIATELY (within 3 seconds)
            # Return proper Slack acknowledgment first
            response = "", 200
            
            # Then send the response message asynchronously
            def send_response_async():
                try:
                    # Create response message
                    responses = {
                        'great': '😊 Great to hear you\'re doing well!',
                        'okay': '😐 Thanks for letting us know. Hope things get better!',
                        'not_great': '😔 Sorry to hear that. Is there anything we can do to help?'
                    }
                    
                    response_text = responses.get(action, 'Thanks for your response!')
                    
                    # Send response in thread
                    thread_response = self.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=response_text
                    )
                    print(f"Response sent successfully: {thread_response['ts']}")
                except Exception as e:
                    print(f"Error sending async response: {e}")
            
            # Start async thread
            import threading
            thread = threading.Thread(target=send_response_async)
            thread.daemon = True
            thread.start()
            
            return response
        except Exception as e:
            print(f"Unexpected error: {e}")
            return "", 200
    
    def get_daily_report(self, date=None):
        """Generate and send a daily report of responses"""
        if not date:
            date = datetime.utcnow().strftime("%Y-%m-%d")
        
        if self.mongodb.db is None:
            return "MongoDB not connected"
        
        try:
            summary = self.mongodb.get_daily_summary(date)
            
            if not summary:
                return f"No responses recorded for {date}."
            
            report = f"📊 *Daily Health Check Report - {date}*\n\n"
            
            for item in summary:
                response_type = item['_id']
                count = item['count']
                users = item['users']
                
                emoji_map = {
                    'great': '😊',
                    'okay': '😐', 
                    'not_great': '😔'
                }
                
                emoji = emoji_map.get(response_type, '📝')
                user_list = ', '.join(users)
                
                report += f"{emoji} *{response_type.title()}*: {count} responses\n"
                report += f"   Users: {user_list}\n\n"
            
            return report
        except Exception as e:
            return f"Error generating report: {e}"
    
    def handle_standup_response(self, payload):
        """Handle standup responses and send follow-up if needed"""
        try:
            print("Received standup response:", payload)
            
            # Extract event data from the payload
            event = payload.get('event', {})
            
            # Get the user who responded
            user = event.get('user')
            username = event.get('user', 'Unknown')  # We'll get username later if needed
            message_ts = event.get('ts')
            channel_id = event.get('channel')
            thread_ts = event.get('thread_ts', message_ts)  # Use thread timestamp if available
            
            # Get bot's own user ID to prevent self-replies
            bot_user_id = self.get_bot_user_id()
            
            # Check if this message has already been processed
            if self.mongodb.check_message_processed(message_ts):
                print(f"Message {message_ts} already processed, ignoring")
                return "", 200
            
            # Mark this message as processed immediately to prevent duplicates
            self.mongodb.mark_message_processed(message_ts, user, thread_ts)
            
            # Ignore bot's own messages
            if user == bot_user_id:
                print(f"Ignoring bot's own message")
                return "", 200
            
            # Only respond to messages that are in a thread (replies to standup)
            if thread_ts == message_ts:
                print(f"Ignoring message from {username} - not in a thread")
                return "", 200
            
            # Only respond to messages in the standup channel
            if channel_id != self.channel_id:
                print(f"Ignoring message from {username} - not in standup channel")
                return "", 200
            
            # Ignore bot messages to prevent self-replies
            if self.is_bot_message(event):
                print(f"Ignoring bot message")
                return "", 200
            
            # Rate limiting: prevent multiple responses to same user within 30 seconds
            current_time = time.time()
            if user in self.recent_responses:
                time_diff = current_time - self.recent_responses[user]
                if time_diff < 30:  # 30 seconds
                    print(f"Ignoring message from {username} - rate limited (last response {time_diff:.1f}s ago)")
                    return "", 200
            
            # Check if user indicated they're not on track or has blockers
            not_on_track = any(phrase in message_text for phrase in ['no', 'not on track', 'behind', 'off track'])
            has_blockers = any(phrase in message_text for phrase in ['blocker', 'blocked', 'stuck', 'issue', 'problem'])
            
            print(f"Analysis for {username}: not_on_track={not_on_track}, has_blockers={has_blockers}")
            
            # Only send follow-up if they're not on track OR have blockers
            if not_on_track or has_blockers:
                # Check if we already sent a follow-up to this user in this thread
                if self.mongodb.check_followup_sent(user, thread_ts):
                    print(f"Follow-up already sent to {username} in this thread")
                    return "", 200
                
                # Create follow-up message
                follow_up_text = f"<@{user}>, thanks for the detailed update! Since you're "
                if not_on_track and has_blockers:
                    follow_up_text += "either not on track or facing a blocker"
                elif not_on_track:
                    follow_up_text += "not on track"
                else:
                    follow_up_text += "facing a blocker"
                
                follow_up_text += ", would you like help?\nYour status:\n"
                
                if not_on_track:
                    follow_up_text += "• On Track: None\n"
                if has_blockers:
                    follow_up_text += "• Blockers: None\n"
                
                follow_up_text += "\nReact with one of the following:\n"
                follow_up_text += "• :sos: = Need help now\n"
                follow_up_text += "• :clock4: = Can wait / just keeping team informed"
                
                # Send follow-up message in thread
                follow_up_response = self.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=follow_up_text
                )
                
                # Store that we sent a follow-up
                self.mongodb.store_followup_sent(user, thread_ts, follow_up_response['ts'])
                
                # Update rate limiting
                self.recent_responses[user] = current_time
                
                print(f"Follow-up sent to {username}: {follow_up_response['ts']}")
            else:
                print(f"No follow-up needed for {username} - on track and no blockers")
            
            return "", 200
            
        except Exception as e:
            print(f"Error handling standup response: {e}")
            return "", 200

# Initialize bot
bot = SlackHealthcheckBot()

# Add health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "bot": "running"}), 200

@app.route('/slack/events', methods=['POST'])
def handle_events():
    try:
        # Get the request data first
        if request.is_json:
            payload = request.get_json()
        else:
            # Handle form-encoded data
            payload = request.form.to_dict()
            if 'payload' in payload:
                import json
                payload = json.loads(payload['payload'])
        
        print("Received event:", payload)  # Debug log
        
        # Handle URL verification FIRST (before any verification)
        if payload.get('type') == 'url_verification':
            print(f"URL verification challenge: {payload['challenge']}")
            return jsonify({"challenge": payload['challenge']})
        
        # Verify the request is from Slack (for non-verification requests)
        if not verify_slack_request(request):
            return jsonify({"text": "Unauthorized"}), 401
        
        # Handle button clicks
        if payload.get('type') == 'block_actions':
            return bot.handle_button_click(payload)
        
        # Handle other events
        if payload.get('type') == 'event_callback':
            event = payload.get('event', {})
            event_type = event.get('type')
            
            if event_type == 'message':
                # Handle standup responses
                return bot.handle_standup_response(payload)
        
        return jsonify({"text": "OK"}), 200
        
    except Exception as e:
        print(f"Error handling event: {e}")
        return jsonify({"text": "Internal server error"}), 200

# API endpoints for reports
@app.route('/api/reports/daily/<date>', methods=['GET'])
def get_daily_report(date):
    """Get daily report for a specific date"""
    try:
        report = bot.get_daily_report(date)
        return jsonify({"report": report, "date": date}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/reports/today', methods=['GET'])
def get_today_report():
    """Get today's report"""
    try:
        report = bot.get_daily_report()
        return jsonify({"report": report, "date": datetime.utcnow().strftime("%Y-%m-%d")}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/responses/<date>', methods=['GET'])
def get_daily_responses(date):
    """Get all responses for a specific date"""
    try:
        responses = bot.mongodb.get_daily_responses(date)
        return jsonify({"responses": responses, "date": date}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("Sending test message...")
    bot.send_healthcheck_message()
    
    # Schedule daily messages
    schedule.every().day.at("09:00").do(bot.send_healthcheck_message)
    schedule.every().day.at("09:30").do(bot.send_standup_message)
    
    print("Bot is running... (Press Ctrl+C to stop)")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=3000, debug=False) 