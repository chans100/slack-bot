import time
from datetime import datetime, timezone, timedelta
from slack_sdk.errors import SlackApiError


def get_est_time():
    """Get current time in EST timezone."""
    utc_now = datetime.now(timezone.utc)
    # Simple EST calculation (UTC-5)
    est_offset = timedelta(hours=5)
    est_time = utc_now - est_offset
    return est_time


class Utilities:
    """Utility functions for the Slack bot."""
    
    def __init__(self, bot):
        self.bot = bot
        self._user_list_cache = None
        self._user_list_cache_time = 0
    
    def get_slack_user_list(self, cache_seconds=600):
        """Get list of Slack users with caching."""
        try:
            current_time = time.time()
            
            # Return cached list if still valid
            if (self._user_list_cache and 
                current_time - self._user_list_cache_time < cache_seconds):
                return self._user_list_cache
            
            # Get fresh user list
            response = self.bot.client.users_list()
            if not response['ok']:
                print(f"❌ Error getting user list: {response.get('error', 'Unknown error')}")
                return []
            
            # Filter out bots and inactive users
            users = []
            for user in response['users']:
                if (not user.get('is_bot', False) and 
                    not user.get('deleted', False) and
                    not user.get('is_restricted', False)):
                    users.append(user['id'])
            
            # Update cache
            self._user_list_cache = users
            self._user_list_cache_time = current_time
            
            print(f"✅ Retrieved {len(users)} active users from Slack")
            return users
            
        except SlackApiError as e:
            print(f"❌ Slack API error getting user list: {e.response['error']}")
            return []
        except Exception as e:
            print(f"❌ Error getting user list: {e}")
            return []
    
    def get_thread_url(self, channel_id, thread_ts):
        """Generate a thread URL for a message."""
        try:
            # Extract channel name from channel ID
            channel_info = self.bot.client.conversations_info(channel=channel_id)
            if channel_info['ok']:
                channel_name = channel_info['channel']['name']
                return f"https://slack.com/app_redirect?channel={channel_name}&message_ts={thread_ts}"
            else:
                return None
        except Exception as e:
            print(f"Error generating thread URL: {e}")
            return None
    
    def get_kr_from_message(self, message):
        """Extract KR name from a message."""
        try:
            text = message.get('text', '')
            blocks = message.get('blocks', [])
            
            # Look for KR in text
            if 'KR:' in text:
                lines = text.split('\n')
                for line in lines:
                    if 'KR:' in line:
                        kr_part = line.split('KR:')[1].strip()
                        return kr_part
            
            # Look for KR in blocks
            for block in blocks:
                if block.get('type') == 'section':
                    block_text = block.get('text', {}).get('text', '')
                    if 'KR:' in block_text:
                        lines = block_text.split('\n')
                        for line in lines:
                            if 'KR:' in line:
                                kr_part = line.split('KR:')[1].strip()
                                return kr_part
            
            return "Unknown KR"
            
        except Exception as e:
            print(f"Error extracting KR from message: {e}")
            return "Unknown KR"
    
    def get_accessible_channels(self):
        """Get list of channels the bot can access."""
        try:
            response = self.bot.client.conversations_list(
                types='public_channel,private_channel',
                exclude_archived=True
            )
            
            if not response['ok']:
                print(f"❌ Error getting channels: {response.get('error', 'Unknown error')}")
                return []
            
            channels = []
            for channel in response['channels']:
                if channel.get('is_member', False):
                    channels.append(channel['name'])
            
            return channels
            
        except SlackApiError as e:
            print(f"❌ Slack API error getting channels: {e.response['error']}")
            return []
        except Exception as e:
            print(f"❌ Error getting channels: {e}")
            return []
    
    def send_completion_message_to_accessible_channel(self, completion_message):
        """Send completion message to an accessible channel."""
        try:
            accessible_channels = self.get_accessible_channels()
            
            # Try to send to general first, then any other accessible channel
            target_channels = ['general', 'leads', 'dev-team']
            
            for channel_name in target_channels:
                if channel_name in accessible_channels:
                    try:
                        self.bot.client.chat_postMessage(
                            channel=f"#{channel_name}",
                            text=completion_message
                        )
                        print(f"✅ Sent completion message to #{channel_name}")
                        return True
                    except Exception as e:
                        print(f"❌ Error sending to #{channel_name}: {e}")
                        continue
            
            # If no preferred channels work, try any accessible channel
            for channel_name in accessible_channels:
                if channel_name not in target_channels:
                    try:
                        self.bot.client.chat_postMessage(
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
        """Handle when user says they haven't reached out to mentor."""
        try:
            message = "I understand you haven't reached out to your mentor yet. "
            message += "It's important to try reaching out to them first, as they can often help resolve issues quickly. "
            message += "If you're still blocked after talking to your mentor, please come back and let me know!"
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=message
            )
            
        except SlackApiError as e:
            print(f"Error handling mentor no response: {e.response['error']}")
    
    def send_mentor_check(self, user_id, standup_ts, user_name, request_type, channel, search_term=None):
        """Send a mentor check prompt to the user."""
        try:
            # Store the search term in a temporary dict for the user (for follow-up after mentor check)
            if not hasattr(self.bot, 'pending_kr_search'):
                self.bot.pending_kr_search = {}
            if request_type == "kr":
                self.bot.pending_kr_search[user_id] = search_term if search_term else None
            
            # Send the mentor check prompt
            self.bot.client.chat_postMessage(
                channel=channel,
                text=(
                    f"@{user_name}, before we proceed with your {request_type} request, I need to ask:\n"
                    ":thinking_face: Have you reached out to your mentor yet?"
                ),
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"@{user_name}, before we proceed with your {request_type} request, I need to ask:\n:thinking_face: Have you reached out to your mentor yet?"
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
    
    def _send_simple_status_update(self, channel_id, message_ts, kr_name, kr_status_info, safe_kr_name):
        """Send a simple status update message."""
        try:
            status_message = f"📊 *KR Status Update*\n\n"
            status_message += f"**KR:** {kr_name}\n"
            status_message += f"**Current Status:** {kr_status_info}\n\n"
            status_message += f"💡 Use the buttons below to check status or mark as completed."
            
            status_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": status_message
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🔄 Refresh Status",
                                "emoji": True
                            },
                            "value": f"refresh_{safe_kr_name}",
                            "action_id": "refresh_status"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Mark Completed",
                                "emoji": True
                            },
                            "value": f"complete_{safe_kr_name}",
                            "action_id": "mark_completed"
                        }
                    ]
                }
            ]
            
            self.bot.client.chat_update(
                channel=channel_id,
                ts=message_ts,
                blocks=status_blocks,
                text=f"KR Status Update: {kr_name}"
            )
            
            print(f"✅ Status update sent for KR: {kr_name}")
            
        except SlackApiError as e:
            print(f"❌ Error sending status update: {e.response['error']}")
        except Exception as e:
            print(f"❌ Error in _send_simple_status_update: {e}")
    
    def get_kr_progress_from_coda(self, kr_name):
        """Get KR progress information from Coda."""
        try:
            if not self.bot.coda:
                return None
            
            kr_details = self.bot.coda.get_kr_details(kr_name)
            if kr_details:
                return {
                    'status': kr_details.get('status', 'Unknown'),
                    'progress': kr_details.get('progress', 0),
                    'owner': kr_details.get('owner', 'Unknown'),
                    'helper': kr_details.get('helper', ''),
                    'notes': kr_details.get('notes', '')
                }
            return None
            
        except Exception as e:
            print(f"❌ Error getting KR progress from Coda: {e}")
            return None 