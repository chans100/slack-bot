import os
import time
import schedule
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Load environment variables
load_dotenv("token.env")

app = Flask(__name__)

class SlackHealthcheckBot:
    def __init__(self):
        self.client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
        self.channel_id = os.environ.get("SLACK_CHANNEL_ID")
        
    def send_healthcheck_message(self):
        try:
            # Create a message with a healthcheck prompt
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "👋 *Daily Health Check*\nHow are you feeling today?"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "😊 Great",
                                    "emoji": True
                                },
                                "value": "great",
                                "action_id": "great"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "😐 Okay",
                                    "emoji": True
                                },
                                "value": "okay",
                                "action_id": "okay"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "😔 Not Great",
                                    "emoji": True
                                },
                                "value": "not_great",
                                "action_id": "not_great"
                            }
                        ]
                    }
                ]
            }
            
            # Send the message
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                blocks=message["blocks"],
                text="Daily Health Check"  # Adding fallback text
            )
            
        except SlackApiError as e:
            print(f"Error sending message: {e.response['error']}")

    def handle_button_click(self, payload):
        try:
            print("Received button click payload:", payload)  # Debug log
            
            # Get the user who clicked the button
            user = payload['user']['id']
            action = payload['actions'][0]['value']
            message_ts = payload['message']['ts']
            channel = payload['channel']['id']
            
            print(f"User {user} clicked {action} in channel {channel}")  # Debug log
            
            # Create response message
            responses = {
                'great': '😊 Great to hear you\'re doing well!',
                'okay': '😐 Thanks for letting us know. Hope things get better!',
                'not_great': '😔 Sorry to hear that. Is there anything we can do to help?'
            }
            
            # Send a response message
            response = self.client.chat_postMessage(
                channel=channel,
                thread_ts=message_ts,
                text=responses.get(action, 'Thanks for your response!')
            )
            
            # Acknowledge the action
            return jsonify({"text": "Thanks for your response!"})
            
        except SlackApiError as e:
            print(f"Error handling button click: {e.response['error']}")
            return jsonify({"text": "Sorry, something went wrong!"}), 500
        except Exception as e:
            print(f"Unexpected error: {str(e)}")  # Debug log
            return jsonify({"text": "Sorry, something went wrong!"}), 500

    def send_standup_message(self):
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Good morning team! 🌞 Time for the daily standup!\nPlease reply to this thread with:\n\n1. What did you do today?\n2. Are you on track to meet your goals? (Yes/No)\n3. Any blockers?\n <!channel> please respond by 4:30 PM. Let's stay aligned! 💬"
                        }
                    }
                ]  
            }
            global stdresponse; stdresponse = self.client.chat_postMessage(
                channel=self.channel_id,
                blocks=message["blocks"],
                text="Daily Standup"
            )
            print(f"Standup message sent successfully: {stdresponse['ts']}")
            return jsonify({"text": "Sorry, something went wrong!"}), 500
        except SlackApiError as e:
            print(f"Error sending standup message: {e.response['error']}")
            return jsonify({"text": "Sorry, something went wrong!"}), 500

    def handle_standup_thread_reply(self, payload):
        try:
            # Check if this is a thread reply
            if 'thread_ts' in payload:
                message_ts = payload['thread_ts']
                user = payload['user']
                text = payload['text']
                channel = payload['channel']
                
                
                # if message_ts == self.stdresponse['ts']: 
                if "On Track: Yes" in text and "Blockers: None" in text:
                    try: 
                        message = {
                            "blocks": [
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": f"🎉 Great job, <@{user}>! Keep up the good work! 🎉"
                                    }
                                }
                            ]
                        }
                        threadresponse = self.client.chat_postMessage(
                            channel=channel,
                            thread_ts=message_ts,
                            blocks=message["blocks"],
                        )
                        print(f"Thread response sent successfully: {threadresponse['thread_ts']}")
                    except SlackApiError as e:
                        print(f"Error sending thread response: {e.response['error']}")
                return jsonify({"text": "Reply received!"})
            return jsonify({"text": "Not a thread reply"})
        except Exception as e:
            print(f"Error handling thread reply: {str(e)}")
            return jsonify({"text": "Sorry, something went wrong!"}), 500

# Initialize the bot
bot = SlackHealthcheckBot()

@app.route('/slack/events', methods=['POST'])
def handle_events():
    # Get the request data
    if request.is_json:
        payload = request.get_json()
    else:
        # Handle form-encoded data
        payload = request.form.to_dict()
        if 'payload' in payload:
            import json
            payload = json.loads(payload['payload'])
        
    # Handle URL verification
    if payload.get('type') == 'url_verification':
        return jsonify({"challenge": payload['challenge']})
    
    # Handle button clicks
    if payload.get('type') == 'block_actions':
        return bot.handle_button_click(payload)
    
    # Handle actual events
    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        
        # Check if it's a message in a thread
        if event.get("type") == "message" and event.get("thread_ts") ==  stdresponse['ts']:
            return bot.handle_standup_thread_reply(event)
    
    return jsonify({"text": "OK"})

def run_scheduler():
    # Schedule the healthcheck message to be sent every day at 9:00 AM
    schedule.every().day.at("09:00").do(bot.send_healthcheck_message)
    schedule.every().day.at("16:00").do(bot.send_standup_message)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    # Start the scheduler in a separate thread
    import threading
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # Start the Flask app
    print("Bot is running... (Press Ctrl+C to stop)")
    app.run(port=3000) 