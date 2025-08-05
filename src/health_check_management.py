import time
from datetime import datetime
from slack_sdk.errors import SlackApiError


class HealthCheckManager:
    """Manages health check functionality including prompts, responses, and wellness tracking."""
    
    def __init__(self, bot):
        self.bot = bot
    
    def send_health_check_to_dm(self, user_id):
        """Send health check to a specific user via DM."""
        try:
            # Open DM with user
            dm_response = self.bot.client.conversations_open(users=[user_id])
            dm_channel = dm_response['channel']['id']
            
            # Get user info
            user_info = self.bot.client.users_info(user=user_id)
            user_name = user_info['user']['real_name']
            
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"💚 *Hi {user_name}! How are you feeling today?*\n\n"
                                   "This is a quick wellness check to see how you're doing. "
                                   "Your response helps us support you better!\n\n"
                                   "Please click one of the buttons below to let us know how you're feeling:"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "😊 Great!",
                                    "emoji": True
                                },
                                "value": "great",
                                "action_id": "great",
                                "style": "primary"
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
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "💡 *This is completely private and helps us understand team wellness*"
                            }
                        ]
                    }
                ]
            }
            
            response = self.bot.client.chat_postMessage(
                channel=dm_channel,
                blocks=message["blocks"],
                text=f"Health Check for {user_name}"
            )
            
            print(f"✅ Health check sent to {user_name} ({user_id})")
            return response['ts']
            
        except SlackApiError as e:
            print(f"Error sending health check to DM: {e.response['error']}")
            return None
    
    def send_test_health_check(self):
        """Send a test health check message to the channel."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🧪 *Test Health Check*\n\nThis is a test health check message. "
                                   "Please respond to see how the health check system works!"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "😊 Great!",
                                    "emoji": True
                                },
                                "value": "great",
                                "action_id": "great",
                                "style": "primary"
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
            
            response = self.bot.client.chat_postMessage(
                channel=self.bot.channel_id,
                blocks=message["blocks"],
                text="Test Health Check"
            )
            
            print(f"✅ Test health check sent: {response['ts']}")
            return response['ts']
            
        except SlackApiError as e:
            print(f"Error sending test health check: {e.response['error']}")
            return None
    
    def handle_health_check_response(self, user_id, response_value, message_ts, channel_id):
        """Handle health check button responses."""
        try:
            # Check if user has already responded to this health check
            response_key = f"{user_id}_{message_ts}"
            if response_key in self.bot.health_check_responses:
                print(f"❌ User {user_id} already responded to health check")
                return False
            
            # Get user info
            user_info = self.bot.client.users_info(user=user_id)
            username = user_info['user']['real_name']
            
            # Store response and mark user as responded
            success = False
            
            # Try Coda first (primary storage)
            if self.bot.coda and self.bot.coda.main_table_id:
                try:
                    success = self.bot.coda.add_response(
                        user_id=user_id,
                        response=response_value,
                        username=username
                    )
                    if success:
                        print(f"✅ Health check response stored in Coda for {username}")
                except Exception as e:
                    print(f"❌ Error storing health check in Coda: {e}")
            
            if not success:
                print("❌ Failed to store health check response in Coda")
            
            self.bot.health_check_responses.add(response_key)
            
            # Send follow-up prompt asking why they feel that way
            followup_prompt_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Thanks for your response! Could you tell us a bit more about why you're feeling {response_value.replace('_', ' ')} today?"
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
                            "value": f"public_{response_value}",
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
                            "value": f"private_{response_value}",
                            "action_id": "private_chat"
                        }
                    ]
                }
            ]
            
            # Send the follow-up prompt
            self.bot.client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                blocks=followup_prompt_blocks,
                text="Tell us more about how you're feeling"
            )
            
            return True
            
        except SlackApiError as e:
            print(f"Error handling health check response: {e.response['error']}")
            return False
    
    def handle_health_check_explanation(self, user_id, explanation, response_value, channel_id, message_ts, is_public=True):
        """Handle health check explanation submission."""
        try:
            # Get user info
            user_info = self.bot.client.users_info(user=user_id)
            username = user_info['user']['real_name']
            
            # Save to After_Health_Check table if public
            success = False
            if is_public and self.bot.coda:
                try:
                    success = self.bot.coda.add_health_check_explanation(
                        user_id=user_id,
                        username=username,
                        health_check_response=response_value,
                        explanation=explanation
                    )
                    if success:
                        print(f"✅ Health check explanation stored in Coda for {username}")
                except Exception as e:
                    print(f"❌ Error storing health check explanation in Coda: {e}")
            
            # Send confirmation
            if is_public:
                if success:
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"✅ Thanks <@{user_id}>! Your explanation has been recorded and shared with the team."
                    )
                else:
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"❌ Sorry <@{user_id}>, there was an error saving your explanation. Please try again."
                    )
            else:
                # Private response
                if explanation.strip():
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"🤫 <@{user_id}>, I understand. Your message is private and won't be shared with the team. If you need anything, feel free to reach out anytime!"
                    )
                else:
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"🤫 <@{user_id}>, no worries! This conversation is private. If you need anything later, just let me know."
                    )
            
            return True
            
        except SlackApiError as e:
            print(f"Error handling health check explanation: {e.response['error']}")
            return False 