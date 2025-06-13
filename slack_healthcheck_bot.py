import os
import time
import schedule
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Load environment variables
load_dotenv()

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
            print(f"Message sent successfully: {response['ts']}")
            
        except SlackApiError as e:
            print(f"Error sending message: {e.response['error']}")

    def handle_button_click(self, payload):
        try:
            print("Received button click payload:", payload)  # Debug log
            
            # Get the user who clicked the button
            user = payload['user']['id']
            action = payload['actions'][0]['value']
            message_ts = payload['message']['ts']
            
            print(f"User {user} clicked {action}")  # Debug log
            
            # Create response message
            responses = {
                'great': '😊 Great to hear you\'re doing well!',
                'okay': '😐 Thanks for letting us know. Hope things get better!',
                'not_great': '😔 Sorry to hear that. Is there anything we can do to help?'
            }
            
            # Send a response message
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=message_ts,
                text=responses.get(action, 'Thanks for your response!')
            )
            print(f"Response sent successfully: {response['ts']}")  # Debug log
            
            # Acknowledge the action
            return jsonify({"text": "Thanks for your response!"})
            
        except SlackApiError as e:
            print(f"Error handling button click: {e.response['error']}")
            return jsonify({"text": "Sorry, something went wrong!"}), 500
        except Exception as e:
            print(f"Unexpected error: {str(e)}")  # Debug log
            return jsonify({"text": "Sorry, something went wrong!"}), 500

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
    
    print("Received event:", payload)  # Debug log
    
    # Handle URL verification
    if payload.get('type') == 'url_verification':
        return jsonify({"challenge": payload['challenge']})
    
    # Handle button clicks
    if payload.get('type') == 'block_actions':
        return bot.handle_button_click(payload)
    
    return jsonify({"text": "OK"})

def run_scheduler():
    # Schedule the healthcheck message to be sent every day at 9:00 AM
    schedule.every().day.at("09:00").do(bot.send_healthcheck_message)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    # Send initial test message
    print("Sending test message...")
    bot.send_healthcheck_message()
    
    # Start the scheduler in a separate thread
    import threading
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # Start the Flask app
    print("Bot is running... (Press Ctrl+C to stop)")
    app.run(port=3000) 