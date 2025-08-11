import os
import time
import schedule
import threading
import re
import json
from datetime import datetime, timezone, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from .coda_service import CodaService
from .config import BotConfig
from .org_metadata_service import OrgMetadataService
from .utils import logger, error_handler, input_validator, safe_executor, get_est_time
import pytz
from typing import List

class DailyStandupBot:
    """
    A comprehensive Slack bot for daily standup management with hybrid interaction workflows.
    """
    def __init__(self):
        self.config = BotConfig()
        self.client = WebClient(token=self.config.SLACK_BOT_TOKEN)
        # Fallback channel ID - used when role-based channels are not available
        self.channel_id = self.config.SLACK_CHANNEL_ID
        self.coda = None
        
        # Initialize Coda service
        try:
            from .coda_service import CodaService
            self.coda = CodaService()
            print("✅ Coda service initialized")
        except Exception as e:
            print(f"⚠️ Could not initialize Coda service: {e}")
        
        # Initialize Org Metadata service for dynamic department/SME determination
        try:
            self.org_metadata = OrgMetadataService(self.client)
            print("✅ Org Metadata service initialized")
        except Exception as e:
            print(f"⚠️ Could not initialize Org Metadata service: {e}")
            self.org_metadata = None
        
        # Set up error handler with Coda service for error logging
        global error_handler
        error_handler.coda_service = self.coda
        
        # Enhanced tracking from monolithic version
        self.health_check_responses = set()
        self.processed_events = set()
        self.tracked_blockers = {}
        self.active_blockers = {}  # Track active blockers for completion tracking
        self.last_followup_sent = {}
        self.standup_responses = set()
        self.help_offers = set()
        self.kr_name_mappings = {}
        self.daily_prompts_sent = {
            'standup': False,
            'health_check': False
        }
        self.pending_kr_search = {}
        self.BLOCKER_FOLLOWUP_DELAY_HOURS = 2/60  # 2 minutes for testing
        self.DAILY_STANDUP_TIME = "09:00"  # 9 AM
        self.DAILY_HEALTH_CHECK_TIME = "09:00"  # 9 AM
        self.LATE_CHECKIN_THRESHOLD_HOUR = 16  # 4 PM
        
        # Legacy user roles (fallback when org metadata service is unavailable)
        self.user_roles = {
            'U0919MVQLLU': ['developer', 'lead', 'admin'],
            'U0912DJRNSF': ['pm', 'admin'],
        }
        
        # Legacy role channels (fallback when org metadata service is unavailable)
        self.role_channels = {
            'pm': 'general',
            'lead': 'general',
            'developer': 'dev-team',
            'designer': 'design-team',
            'qa': 'qa-team',
            'devops': 'devops-team',
            'sm': 'general',
            'admin': 'general'
        }
        
        # Legacy escalation hierarchy (fallback when org metadata service is unavailable)
        self.escalation_hierarchy = {
            'blocker': ['developer', 'lead', 'sm', 'pm'],
            'health_check': ['pm', 'admin'],
            'standup': ['pm', 'lead'],
            'kr_issue': ['lead', 'pm']
        }
        self.user_responses = {}
        
        # Initialize user list cache
        self._user_list_cache = None
        self._user_list_cache_time = 0

    def get_user_info(self, user_id):
        """Get user info from Slack with network error handling."""
        try:
            response = self.client.users_info(user=user_id)
            return response['user']
        except SlackApiError as e:
            print(f"❌ Slack API error getting user info: {e}")
            return None
        except Exception as e:
            # Handle network connectivity issues
            if "getaddrinfo failed" in str(e) or "URLError" in str(e) or "ConnectionError" in str(e):
                print(f"❌ Network connectivity issue getting user info: {e}")
                # Return a fallback user info structure
                return {
                    'id': user_id,
                    'name': 'Unknown',
                    'profile': {
                        'display_name': 'Unknown',
                        'real_name': 'Unknown'
                    }
                }
            else:
                print(f"❌ Unexpected error getting user info: {e}")
                return None

    def get_user_name(self, user_id):
        """Get user's display name or real name with fallback handling."""
        try:
            user_info = self.get_user_info(user_id)
            if user_info:
                return user_info.get('profile', {}).get('display_name') or user_info.get('profile', {}).get('real_name') or user_info.get('name', 'Unknown')
            return 'Unknown'
        except Exception as e:
            print(f"❌ Error in get_user_name: {e}")
            return 'Unknown'

    def send_message(self, channel_id, text, blocks=None, thread_ts=None):
        """Send a message to a channel with comprehensive error handling."""
        try:
            # Validate inputs
            if not input_validator.validate_channel_id(channel_id):
                return error_handler.handle_validation_error(
                    ValueError(f"Invalid channel ID: {channel_id}"),
                    "send_message",
                    additional_data={'channel_id': channel_id}
                )
            
            # Sanitize text
            sanitized_text = input_validator.sanitize_text(text) if text else ""
            
            kwargs = {
                'channel': channel_id,
                'text': sanitized_text
            }
            if blocks:
                kwargs['blocks'] = blocks
            if thread_ts:
                if not input_validator.validate_message_ts(thread_ts):
                    return error_handler.handle_validation_error(
                        ValueError(f"Invalid thread timestamp: {thread_ts}"),
                        "send_message",
                        additional_data={'thread_ts': thread_ts}
                    )
                kwargs['thread_ts'] = thread_ts
            
            response = self.client.chat_postMessage(**kwargs)
            logger.info(f"Message sent successfully to channel {channel_id}")
            return response
            
        except SlackApiError as e:
            return error_handler.handle_api_error(
                e, "send_message", additional_data={
                    'channel_id': channel_id,
                    'text_length': len(text) if text else 0,
                    'has_blocks': bool(blocks),
                    'has_thread': bool(thread_ts)
                }
            )
        except Exception as e:
            return error_handler.handle_unexpected_error(
                e, "send_message", additional_data={
                    'channel_id': channel_id,
                    'text_length': len(text) if text else 0,
                    'has_blocks': bool(blocks),
                    'has_thread': bool(thread_ts)
                }
            )

    def send_ephemeral_message(self, channel_id, user_id, text, blocks=None):
        """Send an ephemeral message to a user."""
        try:
            kwargs = {
                'channel': channel_id,
                'user': user_id,
                'text': text
            }
            if blocks:
                kwargs['blocks'] = blocks
            
            response = self.client.chat_postEphemeral(**kwargs)
            return response
        except SlackApiError as e:
            print(f"❌ Error sending ephemeral message: {e}")
            return None

    def send_dm(self, user_id, text, blocks=None):
        """Send a direct message to a user."""
        try:
            # Try to send DM directly using the user ID as the channel
            # This approach works with just im:write scope
            dm_channel_id = user_id
            
            kwargs = {
                'channel': dm_channel_id,
                'text': text
            }
            if blocks:
                kwargs['blocks'] = blocks
                # Ensure text is not empty when blocks are provided
                if not text.strip():
                    kwargs['text'] = "Daily Standup Bot message"
            
            response = self.client.chat_postMessage(**kwargs)
            return response
            
        except SlackApiError as e:
            print(f"❌ Error sending DM: {e}")
            # If direct DM fails, try to open conversation first
            try:
                print(f"🔄 Trying to open DM conversation for {user_id}")
                dm_response = self.client.conversations_open(users=[user_id])
                dm_channel_id = dm_response['channel']['id']
                
                kwargs = {
                    'channel': dm_channel_id,
                    'text': text
                }
                if blocks:
                    kwargs['blocks'] = blocks
                    if not text.strip():
                        kwargs['text'] = "Daily Standup Bot message"
                
                response = self.client.chat_postMessage(**kwargs)
                return response
                
            except SlackApiError as conv_error:
                print(f"❌ Error opening DM conversation: {conv_error}")
                return None
        except Exception as e:
            print(f"❌ Unexpected error sending DM: {e}")
            return None

    def update_message(self, channel_id, ts, text, blocks=None, append=False):
        """Update an existing message."""
        try:
            if append:
                # Get the current message content
                try:
                    current_message = self.client.conversations_history(
                        channel=channel_id,
                        latest=ts,
                        limit=1,
                        inclusive=True
                    )
                    if current_message['messages']:
                        current_text = current_message['messages'][0].get('text', '')
                        text = current_text + text
                except Exception as e:
                    print(f"❌ Error getting current message for append: {e}")
            
            kwargs = {
                'channel': channel_id,
                'ts': ts,
                'text': text
            }
            if blocks:
                kwargs['blocks'] = blocks
            
            response = self.client.chat_update(**kwargs)
            return response
        except SlackApiError as e:
            print(f"❌ Error updating message: {e}")
            return None

    def open_modal(self, trigger_id, title, blocks, submit_text="Submit", callback_id=None, private_metadata=None):
        """Open a modal dialog."""
        try:
            modal = {
                "type": "modal",
                "title": {"type": "plain_text", "text": title},
                "blocks": blocks,
                "submit": {"type": "plain_text", "text": submit_text}
            }
            if callback_id:
                modal["callback_id"] = callback_id
            if private_metadata:
                modal["private_metadata"] = private_metadata
            
            response = self.client.views_open(trigger_id=trigger_id, view=modal)
            return response
        except SlackApiError as e:
            print(f"❌ Error opening modal: {e}")
            return None

    def update_modal(self, view_id, title, blocks, submit_text="Submit"):
        """Update an existing modal."""
        try:
            modal = {
                "type": "modal",
                "title": {"type": "plain_text", "text": title},
                "blocks": blocks,
                "submit": {"type": "plain_text", "text": submit_text}
            }
            
            response = self.client.views_update(view_id=view_id, view=modal)
            return response
        except SlackApiError as e:
            print(f"❌ Error updating modal: {e}")
            return None

    def send_mentor_check(self, user_id, standup_ts, user_name, request_type, channel, search_term=None):
        """Send a mentor check prompt to the user. If search_term is provided, store it for use after mentor check."""
        try:
            print(f"🔍 DEBUG: send_mentor_check called for user {user_name} ({user_id})")
            print(f"🔍 DEBUG: Request type: {request_type}, Search term: {search_term}")
            
            # Store the search term in a temporary dict for the user (for follow-up after mentor check)
            if not hasattr(self, 'pending_kr_search'):
                self.pending_kr_search = {}
            if request_type == "kr":
                self.pending_kr_search[user_id] = search_term if search_term else None
                print(f"🔍 DEBUG: Stored search term '{search_term}' for user {user_id}")
            
            # Create the mentor check message with buttons
            if request_type == "kr":
                mentor_text = f"@{user_name}, before we proceed with your KR request, I need to ask:\n:thinking_face: Have you reached out to your mentor yet?"
            elif request_type == "blocker":
                mentor_text = f"@{user_name}, before we proceed with your blocker report, I need to ask:\n:thinking_face: Have you reached out to your mentor yet?"
            else:
                mentor_text = f"@{user_name}, before we proceed, I need to ask:\n:thinking_face: Have you reached out to your mentor yet?"
            
            mentor_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": mentor_text
                    }
                },
                {
                    "type": "actions",
                    "block_id": "mentor_check_buttons",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Yes"},
                            "value": f"mentor_yes_{request_type}_{user_id}",
                            "action_id": "mentor_yes",
                            "style": "primary"
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
            
            print(f"🔍 DEBUG: Sending mentor check to channel: {channel}")
            print(f"🔍 DEBUG: Blocks: {mentor_blocks}")
            
            # Send as DM for privacy, but now we handle DM button clicks properly
            result = self.send_dm(user_id, mentor_text, blocks=mentor_blocks)
            print(f"🔍 DEBUG: send_dm result: {result}")
            
            print(f"✅ DEBUG: Mentor check sent successfully to {user_name}")
            return result
            
        except Exception as e:
            print(f"❌ Error sending mentor check: {e}")
            import traceback
            traceback.print_exc()
            return None

    def send_help_followup(self, user_id, standup_ts, user_name, channel_id=None):
        """Send enhanced blocker follow-up with structured questions."""
        try:
            # Send a simple message with a button to open the modal
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<@{user_id}>, I see you need help! 🚨\n\nLet me help you get unblocked. Please provide the following information:"
                    }
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

            # If channel_id is a user ID (DM), send directly to DM
            if channel_id and channel_id.startswith('U'):
                self.send_dm(user_id, "", blocks=blocks)
                print(f"Enhanced blocker follow-up sent to DM for {user_name} ({user_id})")
                return "dm_sent"
            else:
                # Send to channel with thread
                response = self.client.chat_postMessage(
                    channel=channel_id or self.channel_id,
                    thread_ts=standup_ts,
                    blocks=blocks,
                    text=f"<@{user_id}>, I see you need help! Please click the button to submit blocker details."
                )
                print(f"Enhanced blocker follow-up sent to {user_name} ({user_id})")
                return response['ts']

        except SlackApiError as e:
            print(f"Error sending enhanced blocker follow-up: {e.response['error']}")
            return None

    def escalate_blocker_with_details(self, user_id, user_name, blocker_description, kr_name, urgency, notes):
        """Escalate blocker with detailed information using dynamic org metadata."""
        try:
            import time
            
            # Create unique blocker ID for tracking
            blocker_id = f"blocker_{user_id}_{int(time.time())}"
            
            # Use org metadata service to determine appropriate escalation
            topic = f"{blocker_description} {kr_name}"
            department = 'engineering'  # Default fallback
            sme = 'backend'  # Default fallback
            
            if self.org_metadata:
                try:
                    # Get department/SME analysis for the blocker
                    topic_analysis = self.org_metadata.get_department_sme_for_topic(topic, user_id)
                    department = topic_analysis.get('department', 'engineering')
                    sme = topic_analysis.get('sme', 'backend')
                    print(f"🔍 Dynamic analysis: Department={department}, SME={sme}")
                except Exception as e:
                    print(f"⚠️ Error in org metadata analysis: {e}")
                    # Fallback to defaults
            
            # Save to Coda and update KR status
            if self.coda:
                try:
                    # Use the new method that adds blocker and updates KR status
                    success = self.coda.add_blocker_to_kr(
                        kr_name=kr_name,
                        blocker_description=blocker_description,
                        reported_by=user_name,
                        reported_by_id=user_id,
                        urgency=urgency,
                        notes=notes
                    )
                    if success:
                        print(f"✅ Blocker saved to Coda and KR '{kr_name}' status updated to 'Blocked' for {user_name}")
                    else:
                        print(f"❌ Failed to save blocker to Coda or update KR status for {user_name}")
                        # Fallback to old method if new method fails
                        fallback_success = self.coda.add_blocker(
                            user_id=user_id,
                            blocker_description=blocker_description,
                            kr_name=kr_name,
                            urgency=urgency,
                            notes=notes,
                            username=user_name
                        )
                        if fallback_success:
                            print(f"✅ Blocker saved to Coda (fallback) for {user_name}")
                        else:
                            print(f"❌ Failed to save blocker to Coda (fallback) for {user_name}")
                except Exception as e:
                    print(f"❌ Error saving blocker to Coda: {e}")
                    # Try fallback method
                    try:
                        fallback_success = self.coda.add_blocker(
                            user_id=user_id,
                            blocker_description=blocker_description,
                            kr_name=kr_name,
                            urgency=urgency,
                            notes=notes,
                            username=user_name
                        )
                        if fallback_success:
                            print(f"✅ Blocker saved to Coda (fallback) for {user_name}")
                    except Exception as fallback_error:
                        print(f"❌ Fallback method also failed: {fallback_error}")
            else:
                print(f"⚠️ Coda service not available - blocker not saved to database")
            
            # Get leads and PMs
            leads = self.get_users_by_role('lead')
            pms = self.get_users_by_role('pm')
            all_escalation_users = list(set(leads + pms))
            
            if not all_escalation_users:
                all_escalation_users = [user_id]  # Fallback to original user
            
            # Format urgency with emoji
            urgency_emoji = {
                'Low': '🟢',
                'Medium': '🟡', 
                'High': '🟠',
                'Critical': '🔴'
            }.get(urgency, '⚪')
            
            # Create escalation message with department/SME context
            escalation_text = f"🚨 *BLOCKER ESCALATION - {urgency_emoji} {urgency} Priority*\n\n"
            escalation_text += f"<@{user_id}> ({user_name}) is blocked and needs assistance!\n\n"
            escalation_text += f"*Blocker Details:*\n"
            escalation_text += f"• **Description:** {blocker_description}\n"
            escalation_text += f"• **KR:** {kr_name}\n"
            escalation_text += f"• **Urgency:** {urgency_emoji} {urgency}\n"
            escalation_text += f"• **Notes:** {notes if notes else 'None'}\n\n"
            escalation_text += f"*Status:* ⏳ Unclaimed - Available for leads to claim"
            
            # Create blocks with claim functionality - only Claim and View Progress buttons
            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": escalation_text}
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
                            "value": f"view_details_{blocker_id}_{kr_name}",
                            "action_id": "view_details"
                        }
                    ]
                }
            ]
            
            # Send to escalation channel
            escalation_channel = f"#{self.config.SLACK_ESCALATION_CHANNEL}" if self.config.SLACK_ESCALATION_CHANNEL else self.channel_id
            print(f"🔍 DEBUG: Sending blocker escalation to channel: {escalation_channel}")
            
            try:
                response = self.client.chat_postMessage(
                    channel=escalation_channel,
                    blocks=blocks,
                    text=f"🚨 Blocker Alert: {user_name} needs help with {kr_name}"
                )
                print(f"✅ Blocker escalation sent to {escalation_channel} for {user_name}")
            except Exception as e:
                print(f"❌ Error sending to escalation channel, falling back to general: {e}")
                # Fallback to general channel
                response = self.client.chat_postMessage(
                    channel="#general",
                    blocks=blocks,
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
                'escalation_ts': response['ts'],
                'channel': self.config.SLACK_ESCALATION_CHANNEL,
                'channel_id': response.get('channel'),
                'message_ts': response['ts'],
                'status': 'unclaimed',
                'claimed_by': None,
                'claimed_at': None,
                'progress_updates': [],
                'department': department,
                'sme': sme,
                'details_reply_ts': None  # Will be set when first view details message is sent
            }
            if not hasattr(self, 'active_blockers'):
                self.active_blockers = {}
            self.active_blockers[blocker_id] = blocker_info
            
            # Track for follow-up
            self.track_blocker_for_followup(
                user_id, user_name, blocker_description, kr_name, 
                urgency, notes, response['ts'], response.get('channel'), response['ts']
            )
            
            return response['ts']
        except Exception as e:
            print(f"Error escalating blocker: {e}")
            return None

    def track_blocker_for_followup(self, user_id, user_name, blocker_description, kr_name, urgency, notes, escalation_ts, channel_id=None, message_ts=None):
        """Track a blocker for automatic 24-hour follow-up."""
        try:
            blocker_id = f"{user_id}_{kr_name}_{escalation_ts}"
            self.tracked_blockers[blocker_id] = {
                'user_id': user_id,
                'user_name': user_name,
                'blocker_description': blocker_description,
                'kr_name': kr_name,
                'urgency': urgency,
                'notes': notes,
                'escalation_ts': escalation_ts,
                'channel_id': channel_id,
                'message_ts': message_ts,
                'created_at': datetime.now(),
                'followup_sent': False
            }
            print(f"Tracked blocker {blocker_id} for follow-up")
        except Exception as e:
            print(f"Error tracking blocker: {e}")

    def check_blocker_followups(self):
        """Check for blockers that need follow-up and load unresolved blockers from Coda."""
        try:
            current_time = datetime.now()
            print(f"🔍 Checking blocker followups at {current_time.strftime('%H:%M:%S')} - {len(self.tracked_blockers)} tracked blockers")
            
            # Load unresolved blockers from Coda to ensure we don't miss any
            if self.coda:
                try:
                    print("🔍 Loading unresolved blockers from Coda...")
                    unresolved_blockers = self.coda.get_unresolved_blockers()
                    
                    for blocker in unresolved_blockers:
                        # Create a unique blocker ID for tracking
                        blocker_id = f"{blocker.get('user_id', 'unknown')}_{blocker.get('kr_name', 'unknown')}_{blocker.get('created_at', 'unknown')}"
                        
                        # Only track if not already tracked
                        if blocker_id not in self.tracked_blockers:
                            # Convert Coda timestamp to datetime if it's a string
                            created_at = blocker.get('created_at')
                            
                            if isinstance(created_at, str):
                                try:
                                    # Handle ISO format with timezone info
                                    if created_at.endswith('Z'):
                                        created_at = created_at.replace('Z', '+00:00')
                                    created_at = datetime.fromisoformat(created_at)
                                    
                                    # Convert UTC to local time
                                    import pytz
                                    utc_tz = pytz.UTC
                                    local_tz = pytz.timezone('US/Eastern')  # Adjust to your timezone
                                    
                                    # Make timezone-aware if it's not already
                                    if created_at.tzinfo is None:
                                        created_at = utc_tz.localize(created_at)
                                    
                                    # Convert to local time
                                    created_at = created_at.astimezone(local_tz)
                                    
                                except Exception as parse_error:
                                    print(f"⚠️ Error parsing datetime '{created_at}': {parse_error}")
                                    created_at = current_time - timedelta(hours=25)  # Default to 25 hours ago
                            elif created_at is None:
                                created_at = current_time - timedelta(hours=25)  # Default to 25 hours ago
                            
                            # Ensure both datetimes are timezone-naive for comparison
                            if created_at.tzinfo is not None:
                                created_at = created_at.replace(tzinfo=None)
                            
                            # Track this blocker for followup - use correct field names from Coda
                            self.tracked_blockers[blocker_id] = {
                                'user_id': blocker.get('user_id', 'unknown'),
                                'user_name': blocker.get('name', 'Unknown User'),
                                'kr_name': blocker.get('kr_name', 'Unknown KR'),
                                'blocker_description': blocker.get('blocker_description', 'Unknown blocker'),
                                'urgency': blocker.get('urgency', 'medium'),
                                'notes': blocker.get('notes', ''),
                                'created_at': created_at,
                                'followup_sent': False,
                                'channel_id': None,
                                'status': 'unresolved'
                            }
                            print(f"📝 Loaded unresolved blocker: {blocker.get('name', 'Unknown')} - {blocker.get('kr_name', 'Unknown KR')}")
                    
                    print(f"✅ Loaded {len(unresolved_blockers)} unresolved blockers from Coda")
                except Exception as e:
                    print(f"❌ Error loading unresolved blockers from Coda: {e}")
            
            # Check for blockers that need follow-up
            followup_count = 0
            current_time_naive = current_time.replace(tzinfo=None)
            
            for blocker_id, blocker_info in self.tracked_blockers.items():
                if blocker_info['followup_sent']:
                    continue
                
                # Ensure blocker datetime is timezone-naive for comparison
                blocker_created = blocker_info['created_at']
                
                if blocker_created.tzinfo is not None:
                    blocker_created = blocker_created.replace(tzinfo=None)
                
                time_diff = current_time_naive - blocker_created
                hours_old = time_diff.total_seconds() / 3600
                
                print(f"🔍 Blocker {blocker_info['user_name']} - {blocker_info['kr_name']} is {hours_old:.1f} hours old")
                
                if hours_old >= self.BLOCKER_FOLLOWUP_DELAY_HOURS:
                    print(f"⏰ Sending 24-hour followup for blocker: {blocker_info['user_name']} - {blocker_info['kr_name']}")
                    self.send_blocker_followup(blocker_info)
                    blocker_info['followup_sent'] = True
                    followup_count += 1
            
            if followup_count > 0:
                print(f"✅ Sent {followup_count} blocker followup(s)")
            else:
                print(f"✅ No blockers need followup at this time")
                
        except Exception as e:
            print(f"❌ Error checking blocker followups: {e}")

    def send_blocker_followup(self, blocker_info):
        """Send 24-hour follow-up message for a blocker."""
        try:
            user_id = blocker_info['user_id']
            user_name = blocker_info['user_name']
            kr_name = blocker_info['kr_name']
            channel_id = blocker_info['channel_id'] or self.channel_id
            
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⏰ *24-Hour Blocker Follow-up*\n\nHi <@{user_id}>, it's been 24 hours since you reported a blocker for *{kr_name}*. How's it going?"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Resolved"},
                            "action_id": "blocker_resolved",
                            "value": f"{user_id}_{kr_name}",
                            "style": "primary"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Still Blocked"},
                            "action_id": "blocker_still_blocked",
                            "value": f"{user_id}_{kr_name}"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Need More Help"},
                            "action_id": "blocker_need_help",
                            "value": f"{user_id}_{kr_name}"
                        }
                    ]
                }
            ]
            
            # Try to send as DM first
            dm_result = self.send_dm(user_id, "", blocks=blocks)
            
            if dm_result is None:
                # DM failed, send to escalation channel as fallback
                print(f"⚠️ DM failed for {user_name}, sending to escalation channel as fallback")
                fallback_text = f"⏰ *24-Hour Blocker Follow-up*\n\n<@{user_id}>, it's been 24 hours since you reported a blocker for *{kr_name}*. How's it going?"
                
                try:
                    escalation_channel = f"#{self.config.SLACK_ESCALATION_CHANNEL}" if self.config.SLACK_ESCALATION_CHANNEL else self.channel_id
                    self.client.chat_postMessage(
                        channel=escalation_channel,
                        text=fallback_text,
                        blocks=blocks
                    )
                    print(f"✅ Sent blocker followup to escalation channel for {user_name}")
                except Exception as fallback_error:
                    print(f"❌ Fallback to escalation channel also failed: {fallback_error}")
                    # Last resort: send to general channel
                    try:
                        self.client.chat_postMessage(
                            channel="#general",
                            text=fallback_text,
                            blocks=blocks
                        )
                        print(f"✅ Sent blocker followup to #general for {user_name}")
                    except Exception as general_error:
                        print(f"❌ All fallback methods failed: {general_error}")
            else:
                print(f"✅ Sent blocker followup to {user_name}")
                
        except Exception as e:
            print(f"❌ Error sending blocker followup: {e}")

    def get_user_roles(self, user_id):
        """Get roles for a specific user using dynamic org metadata."""
        if self.org_metadata:
            try:
                user_info = self.org_metadata.get_user_department_and_sme(user_id)
                # Convert department/SME to legacy role format for compatibility
                roles = []
                if user_info.get('department'):
                    roles.append(user_info['department'])
                if user_info.get('sme'):
                    roles.append(user_info['sme'])
                
                # Add leadership roles based on title
                title = user_info.get('user_info', {}).get('title', '').lower()
                if any(role in title for role in ['lead', 'manager', 'director', 'vp', 'head']):
                    roles.append('lead')
                if any(role in title for role in ['ceo', 'cto', 'cfo', 'coo', 'executive']):
                    roles.append('admin')
                
                return roles
            except Exception as e:
                logger.error(f"Error getting user roles from org metadata: {e}")
        
        # Fallback to legacy hardcoded roles
        return self.user_roles.get(user_id, [])

    def get_users_by_role(self, role):
        """Get all users with a specific role using dynamic org metadata."""
        if self.org_metadata:
            try:
                # Get all users and filter by role
                response = self.client.users_list()
                users = response['members']
                
                matching_users = []
                for user in users:
                    if user.get('is_bot') or user.get('deleted'):
                        continue
                    
                    user_roles = self.get_user_roles(user['id'])
                    if role in user_roles:
                        matching_users.append(user['id'])
                
                return matching_users
            except Exception as e:
                logger.error(f"Error getting users by role from org metadata: {e}")
        
        # Fallback to legacy hardcoded roles
        users = []
        for user_id, roles in self.user_roles.items():
            if role in roles:
                users.append(user_id)
        return users

    def has_role(self, user_id, role):
        """Check if a user has a specific role using dynamic org metadata."""
        return role in self.get_user_roles(user_id)

    def send_role_based_message(self, role, message, channel_override=None):
        """Send a message to all users with a specific role."""
        try:
            users = self.get_users_by_role(role)
            channel = channel_override or self.role_channels.get(role, self.channel_id)
            
            for user_id in users:
                self.send_ephemeral_message(channel, user_id, message)
            
            return len(users)
        except Exception as e:
            print(f"Error sending role-based message: {e}")
            return 0

    def escalate_by_hierarchy(self, issue_type, message, additional_context="", topic=None, user_id=None):
        """Escalate an issue through the dynamic role hierarchy using org metadata."""
        try:
            if self.org_metadata and topic:
                # Use dynamic escalation based on topic analysis
                topic_analysis = self.org_metadata.get_department_sme_for_topic(topic, user_id)
                department = topic_analysis.get('department', 'engineering')
                
                # Get escalation path based on issue type and department
                escalation_path = self.org_metadata.get_escalation_path(issue_type, department)
                
                escalation_message = f"🚨 *{issue_type.upper()} ESCALATION*\n\n{message}"
                if additional_context:
                    escalation_message += f"\n\n*Context:* {additional_context}"
                
                escalation_message += f"\n\n*Department:* {department.title()}"
                escalation_message += f"\n*Analysis:* {topic_analysis.get('rationale', '')}"
                
                # Send to escalation path
                for user_id in escalation_path:
                    channel = self.org_metadata.get_channel_for_department(department)
                    self.send_ephemeral_message(channel, user_id, escalation_message)
                
                return len(escalation_path)
            else:
                # Fallback to legacy escalation
                hierarchy = self.escalation_hierarchy.get(issue_type, [])
                escalation_message = f"🚨 *{issue_type.upper()} ESCALATION*\n\n{message}"
                if additional_context:
                    escalation_message += f"\n\n*Context:* {additional_context}"
                
                for role in hierarchy:
                    users = self.get_users_by_role(role)
                    if users:
                        channel = self.role_channels.get(role, self.channel_id)
                        for user_id in users:
                            self.send_ephemeral_message(channel, user_id, escalation_message)
                        break  # Stop at first role with users
                return len(users) if users else 0
                
        except Exception as e:
            logger.error(f"Error escalating by hierarchy: {e}")
            return 0

    def handle_mentor_no_response(self, user_id, channel_id, message_ts):
        """Send a friendly message when the user has not yet asked their mentor."""
        try:
            user_name = self.get_user_name(user_id)
            
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<@{user_id}>, no worries! It's always good to check with your mentor first. 😊"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Once you've reached out to your mentor, feel free to try your KR request again. They're there to help!"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "I've talked to my mentor now"},
                            "action_id": "mentor_ready",
                            "value": f"ready_{user_id}",
                            "style": "primary"
                        }
                    ]
                }
            ]
            
            # Send as DM instead of channel message
            self.send_dm(user_id, "", blocks=blocks)
        except Exception as e:
            print(f"Error handling mentor no response: {e}")

    def update_blocker_message_with_progress(self, blocker_id, channel_id, message_ts):
        """Update the original blocker message to show latest progress."""
        try:
            # This would typically update a message with progress information
            # For now, just log the action
            print(f"Updated blocker message with progress for {blocker_id}")
            return True
        except Exception as e:
            print(f"Error updating blocker message with progress: {e}")
            return False

    def start(self):
        """Start the bot with automatic role assignment."""
        try:
            print("🚀 Starting Daily Standup Bot...")
            
            # Auto-assign roles on startup
            print("🔄 Auto-assigning roles to users on startup...")
            self.auto_assign_roles()
            
            # Set up scheduler
            schedule.every().day.at("09:00").do(self.send_standup_to_all_users)
            schedule.every().day.at("09:00").do(self.send_health_check_to_all_users)
            schedule.every(2).minutes.do(self.check_blocker_followups)  # Every 2 minutes for testing
            
            # Start scheduler in background thread
            scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
            scheduler_thread.start()
            
            print("✅ Bot started successfully!")
            print("📅 Daily standup and health check scheduled for 9:00 AM")
            print("⏰ Blocker followup check scheduled every 2 minutes (for testing)")
            print("🤖 Auto-role assignment completed on startup")
            
        except Exception as e:
            print(f"❌ Error starting bot: {e}")
            logger.error(f"Bot startup error: {e}")

    def reset_daily_prompts(self):
        """Reset daily prompt flags."""
        self.daily_prompts_sent = {
            'standup': False,
            'health_check': False
        }
        self.standup_responses.clear()
        print("✅ Daily prompts reset")

    def _run_scheduler(self):
        """Run the scheduler loop."""
        print("🔄 Scheduler loop started")
        while True:
            try:
                schedule.run_pending()
                time.sleep(30)  # Changed from 60 seconds to 30 seconds for more responsive scheduling
            except Exception as e:
                print(f"❌ Error in scheduler loop: {e}")
                time.sleep(30)  # Also updated error recovery delay

    def send_daily_standup(self):
        """Send the daily standup prompt message with hybrid interaction options."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": " *Good morning team! Time for the daily standup!*\n\n"
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

    def send_standup_to_dm(self, user_id):
        """Send standup prompt to a specific user's DM using a modal for better UX."""
        try:
            print(f"🔍 DEBUG: Attempting to send standup modal to DM for user {user_id}")
            
            # First, try to open a DM with the user
            try:
                dm_response = self.client.conversations_open(users=[user_id])
                dm_channel = dm_response['channel']['id']
                print(f"🔍 DEBUG: Opened DM channel {dm_channel} for user {user_id}")
            except Exception as e:
                print(f"❌ Could not open DM with user {user_id}: {e}")
                return None
            
            # Send a message that opens the modal
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Good morning! :sun_with_face: Time for the daily checkin!\n\nClick the button below to open the check-in form:"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Open Check-in Form",
                                    "emoji": True
                                },
                                "value": f"open_checkin_{user_id}",
                                "action_id": "open_checkin_modal",
                                "style": "primary"
                            }
                        ]
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=dm_channel,
                blocks=message["blocks"],
                text="Daily Standup - Click to open check-in form"
            )
            
            print(f"✅ Standup prompt sent to DM for user {user_id}: {response['ts']}")
            return response['ts']
            
        except Exception as e:
            print(f"❌ Could not send standup prompt to DM for {user_id}: {str(e)}")
            return None

    def open_checkin_modal(self, trigger_id, user_id):
        """Open the check-in modal with proper formatting and validation."""
        try:
            print(f"🔍 DEBUG: Opening check-in modal for user {user_id}")
            
            # Create modal blocks with proper formatting guidance
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Daily Check-in Form* :memo:\n\nPlease fill out the following questions to complete your daily check-in:"
                    }
                },
                {
                    "type": "input",
                    "block_id": "checkin_status",
                    "label": {
                        "type": "plain_text",
                        "text": "What did you do today?",
                        "emoji": True
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "status_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Describe your accomplishments, progress, and work completed today..."
                        }
                    },
                    "hint": {
                        "type": "plain_text",
                        "text": "Be specific about tasks completed, meetings attended, and progress made"
                    }
                },
                {
                    "type": "input",
                    "block_id": "checkin_track",
                    "label": {
                        "type": "plain_text",
                        "text": "Are you on track to meet your goals?",
                        "emoji": True
                    },
                    "element": {
                        "type": "static_select",
                        "action_id": "track_input",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select your status",
                            "emoji": True
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ Yes - On track",
                                    "emoji": True
                                },
                                "value": "yes"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "❌ No - Behind schedule",
                                    "emoji": True
                                },
                                "value": "no"
                            }
                        ]
                    },
                    "hint": {
                        "type": "plain_text",
                        "text": "Select whether you're on track to meet your goals"
                    }
                },
                {
                    "type": "input",
                    "block_id": "checkin_blockers",
                    "label": {
                        "type": "plain_text",
                        "text": "Do you have any blockers?",
                        "emoji": True
                    },
                    "element": {
                        "type": "static_select",
                        "action_id": "blockers_input",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select your blocker status",
                            "emoji": True
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ No blockers",
                                    "emoji": True
                                },
                                "value": "no"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "❌ Yes - I have blockers",
                                    "emoji": True
                                },
                                "value": "yes"
                            }
                        ]
                    },
                    "hint": {
                        "type": "plain_text",
                        "text": "If you select 'Yes', you'll be prompted to report your blockers"
                    }
                },
                {
                    "type": "input",
                    "block_id": "checkin_notes",
                    "label": {
                        "type": "plain_text",
                        "text": "Additional Notes (Optional)",
                        "emoji": True
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "notes_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Any additional context, questions, or information you'd like to share..."
                        }
                    },
                    "optional": True
                }
            ]
            
            # Open the modal
            result = self.open_modal(
                trigger_id=trigger_id,
                title="Daily Check-in",
                blocks=blocks,
                submit_text="Submit Check-in",
                callback_id="checkin_submit"
            )
            
            if result:
                print(f"✅ Check-in modal opened successfully for user {user_id}")
                return True
            else:
                print(f"❌ Failed to open check-in modal for user {user_id}")
                return False
                
        except Exception as e:
            print(f"❌ Error opening check-in modal for user {user_id}: {e}")
            return False

    def send_standup_to_all_users(self, users=None):
        """Send standup prompts to all team members via DM."""
        try:
            # Removed daily prompt flag check for testing - send every 2 minutes
            # if self.daily_prompts_sent['standup']:
            #     print("⚠️ Daily standup already sent today, skipping...")
            #     return
            
            est_time = get_est_time()
            if est_time.weekday() >= 5:  # Weekend
                print("📅 Weekend detected, skipping daily standup")
                return
            
            if not users:
                users = self.get_slack_user_list()
            
            for user in users:
                if not user.get('is_bot') and not user.get('deleted'):
                    self.send_standup_to_dm(user['id'])
                    time.sleep(1)  # Rate limiting
            
            # self.daily_prompts_sent['standup'] = True  # Removed for testing
            print("✅ Standup prompts sent to all users")
        except Exception as e:
            print(f"❌ Error sending standup to all users: {e}")

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
            # Removed daily prompt flag check for testing - send every 2 minutes
            # if self.daily_prompts_sent['health_check']:
            #     print("⚠️ Health check already sent today, skipping...")
            #     return
            
            if not users:
                users = self.get_slack_user_list()
            
            for user in users:
                if not user.get('is_bot') and not user.get('deleted'):
                    self.send_health_check_to_dm(user['id'])
                    time.sleep(1)  # Rate limiting
            
            # self.daily_prompts_sent['health_check'] = True  # Removed for testing
            print("✅ Health check prompts sent to all users")
        except Exception as e:
            print(f"❌ Error sending health check to all users: {e}")

    def send_health_check(self):
        """Send health check prompt (legacy method for backward compatibility)."""
        self.send_health_check_to_all_users()

    def get_slack_user_list(self, cache_seconds=600):
        """Get list of Slack users with caching."""
        try:
            current_time = time.time()
            
            # Check if we have cached data and it's still valid
            if (self._user_list_cache and 
                self._user_list_cache_time and 
                current_time - self._user_list_cache_time < cache_seconds):
                return self._user_list_cache
            
            # Fetch fresh data
            response = self.client.users_list()
            users = response['members']
            
            # Cache the data
            self._user_list_cache = users
            self._user_list_cache_time = current_time
            
            print(f"✅ Fetched {len(users)} users from Slack")
            return users
            
        except SlackApiError as e:
            print(f"❌ Error fetching Slack users: {e}")
            return []

    def send_end_of_day_summary(self):
        """Send end of day summary."""
        try:
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🌆 *End of day summary time!*"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Please share:\\n• What you accomplished today\\n• Any blockers that remain\\n• Plans for tomorrow"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Share Summary"},
                            "action_id": "end_of_day_summary",
                            "style": "primary"
                        }
                    ]
                }
            ]
            
            self.send_message(self.channel_id, "", blocks=blocks)
            print("✅ End of day summary sent")
        except Exception as e:
            print(f"❌ Error sending end of day summary: {e}")

    # Additional methods from monolithic code
    def parse_standup_response(self, text):
        """Parse standup response text: 1st line = today, 2nd = on_track, 3rd = blockers."""
        lines = text.strip().split('\n')
        parsed = {
            'today': lines[0] if len(lines) > 0 else '',
            'on_track': lines[1] if len(lines) > 1 else '',
            'blockers': lines[2] if len(lines) > 2 else ''
        }
        return parsed

    def handle_standup_response(self, user_id, message_ts, thread_ts, text, channel_id=None):
        """Handle standup response in thread."""
        try:
            user_name = self.get_user_name(user_id)
            parsed_data = self.parse_standup_response(text)
            
            # Check if user has already submitted a standup response today
            today = datetime.now().strftime('%Y-%m-%d')
            standup_key = f"{user_id}_{today}"
            if standup_key in self.standup_responses:
                print(f"⚠️ User {user_id} has already submitted a standup response today")
                return
            
            # Save to Coda
            if self.coda:
                try:
                    # Extract data from parsed response
                    today_work = parsed_data.get('today', '')
                    on_track = parsed_data.get('on_track', '')
                    blockers = parsed_data.get('blockers', '')
                    
                    success = self.coda.add_standup_response(
                        user_id=user_id,
                        response_text=f"Today: {today_work}\nOn Track: {on_track}\nBlockers: {blockers}",
                        username=user_name
                    )
                    if success:
                        print(f"✅ Standup response saved to Coda for {user_name}")
                    else:
                        print(f"❌ Failed to save standup response to Coda for {user_name}")
                except Exception as e:
                    print(f"❌ Error saving standup response to Coda: {e}")
            else:
                print(f"⚠️ Coda service not available - standup response not saved")
            
            # Mark user as having submitted standup response today
            self.standup_responses.add(standup_key)
            print(f"✅ User {user_id} marked as having submitted standup response for {today}")
            
            # Check if user needs help
            needs_help = False
            if parsed_data.get('on_track', '').lower() == 'no':
                needs_help = True
            if parsed_data.get('blockers', '').lower() == 'yes':
                needs_help = True
            
            if needs_help:
                # Send followup message with help options (like the original)
                self.send_followup_message(user_id, thread_ts, parsed_data, channel_id)
            else:
                # Acknowledge good status
                self.send_dm(user_id, "✅ Thanks for your standup response! Keep up the great work!")
                
        except Exception as e:
            print(f"Error handling standup response: {e}")

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
            
        except Exception as e:
            print(f"Error sending followup message: {e}")

    def handle_reaction(self, user_id, message_ts, reaction):
        """Handle reactions to follow-up messages."""
        try:
            if reaction == 'sos':
                # User needs immediate help
                self.escalate_issue(user_id, self.get_user_name(user_id), {})
            elif reaction == 'clock':
                # User can wait
                self.send_message(
                    self.channel_id,
                    f"<@{user_id}>: Got it! We'll check in later. Keep us posted! 📝",
                    thread_ts=message_ts
                )
        except Exception as e:
            print(f"Error handling reaction: {e}")

    def escalate_issue(self, user_id, user_name, parsed_data):
        """Escalate issue based on parsed standup data."""
        try:
            escalation_message = f"""
🚨 *Escalation Alert* 🚨

<@{user_id}> ({user_name}) reported a blocker or delay:

*Status:*
• On Track: {parsed_data.get('on_track', 'N/A')}
• Blockers: {parsed_data.get('blockers', 'None')}
• Today's Work: {parsed_data.get('today', 'N/A')}

⏰ Urgency: HIGH
📆 Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

<!here> please reach out to <@{user_id}> to provide assistance.
""".strip()
            
            self.send_message(self.config.SLACK_ESCALATION_CHANNEL, escalation_message)
            print(f"✅ Issue escalated for user {user_name}")
            
        except Exception as e:
            print(f"Error escalating issue: {e}")

    def check_missing_responses(self):
        """Check for missing responses and send reminders."""
        try:
            # Get all users
            users = self.get_slack_user_list()
            today = datetime.now().strftime('%Y-%m-%d')
            
            for user in users:
                if not user.get('is_bot') and not user.get('deleted'):
                    user_id = user['id']
                    standup_key = f"{user_id}_{today}"
                    
                    if standup_key not in self.standup_responses:
                        # Send reminder
                        self.send_dm(user_id, f"<@{user_id}> Don't forget to respond to today's standup! 📝")
            
            print("✅ Missing response reminders sent")
        except Exception as e:
            print(f"Error checking missing responses: {e}")

    def handle_button_click(self, payload):
        """Handle button clicks."""
        try:
            action_id = payload['actions'][0]['action_id']
            user_id = payload['user']['id']
            
            if action_id == 'escalate_help':
                self.escalate_issue(user_id, self.get_user_name(user_id), {})
            elif action_id == 'monitor_issue':
                # Acknowledge that user can wait
                pass
                
        except Exception as e:
            print(f"Error handling button click: {e}")

    def get_thread_url(self, channel_id, thread_ts):
        """Generate a clickable thread URL."""
        try:
            # Get workspace info
            team_info = self.client.team_info()
            team_domain = team_info['team']['domain']
            
            # Construct URL
            url = f"https://{team_domain}.slack.com/archives/{channel_id}/p{thread_ts.replace('.', '')}"
            return url
        except Exception as e:
            print(f"Error generating thread URL: {e}")
            return None

    def _send_simple_status_update(self, channel_id, message_ts, kr_name, kr_status_info, safe_kr_name):
        """Send a simple status update message when the original message can't be updated."""
        try:
            status_text = f"✅ *{kr_name} Status Updated*\\n"
            status_text += f"*Status:* {kr_status_info.get('status', 'Unknown')}\\n"
            status_text += f"*Progress:* {kr_status_info.get('progress', 'N/A')}\\n"
            status_text += f"*Notes:* {kr_status_info.get('notes', 'N/A')}"
            
            self.send_message(channel_id, status_text, thread_ts=message_ts)
        except Exception as e:
            print(f"Error sending simple status update: {e}")

    def get_kr_from_message(self, message):
        """Extract KR name from the blocker message."""
        try:
            # Look for KR pattern in message
            kr_pattern = r'KR[:\s]*([^\n]+)'
            match = re.search(kr_pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
            return None
        except Exception as e:
            print(f"Error extracting KR from message: {e}")
            return None

    def send_test_health_check(self):
        """Send a test health check message on startup."""
        try:
            self.send_health_check_to_all_users()
            print("✅ Test health check sent")
        except Exception as e:
            print(f"Error sending test health check: {e}")

    def send_test_standup(self):
        """Send a test standup message on startup."""
        try:
            self.send_standup_to_all_users()
            print("✅ Test standup sent")
        except Exception as e:
            print(f"Error sending test standup: {e}")

    def clear_followup_tracking(self):
        """Clear the follow-up tracking to force fresh follow-ups."""
        try:
            self.last_followup_sent.clear()
            print("✅ Follow-up tracking cleared")
        except Exception as e:
            print(f"Error clearing follow-up tracking: {e}")

    def send_info_message(self, channel_id, user_id, mode="user"):
        """Send an info/help message to guide users on how to interact with the bot."""
        try:
            user_name = self.get_user_name(user_id)
            
            if mode == "user":
                message = f"<@{user_id}> Here's how to use the Daily Standup Bot:\\n\\n"
                message += "• React to standup messages with ✅ (good), ⚠️ (minor issues), or 🚨 (need help)\\n"
                message += "• Reply in threads for detailed updates\\n"
                message += "• Use `/help` for all available commands\\n"
                message += "• Use `/blocked` to report blockers\\n"
                message += "• Use `/health` for wellness checks"
            else:
                message = f"<@{user_id}> Admin mode activated. Use `/test_standup` or `/test_health` to trigger prompts."
            
            self.send_dm(user_id, message)
        except Exception as e:
            print(f"Error sending info message: {e}")

    def handle_commands(self, user_id, text, channel_id):
        """Handle slash commands (/) from users. Suggest /help for unrecognized commands in DMs."""
        try:
            # Parse command
            parts = text.strip().split(' ', 1)
            command = parts[0].lower()
            command_text = parts[1] if len(parts) > 1 else ""
            
            # Process command using the local method
            self._process_command(user_id, command, command_text, channel_id)
                
        except Exception as e:
            print(f"Error handling commands: {e}")
            self.send_ephemeral_message(channel_id, user_id, f"❌ Error processing command: {e}")

    def _process_command(self, user_id, command, full_text, channel_id):
        """Process individual commands."""
        try:
            if command == 'role':
                self._handle_role_command(user_id, full_text, channel_id)
                return True
            elif command == 'rolelist':
                self._list_all_roles(channel_id)
                return True
            elif command == 'autorole':
                self._handle_auto_role_command(user_id, full_text, channel_id)
                return True
            elif command == 'refreshroles':
                self._handle_refresh_roles_command(user_id, channel_id)
                return True
            elif command == 'newuserroles':
                self._handle_new_user_roles_command(user_id, channel_id)
                return True
            elif command == 'help':
                self._show_help(channel_id)
                return True
            else:
                self.send_ephemeral_message(channel_id, user_id, f"Unknown command: {command}")
                return False
        except Exception as e:
            print(f"❌ Error in _process_command: {e}")
            self.send_ephemeral_message(channel_id, user_id, f"❌ Error processing command: {e}")
            return False

    def _handle_auto_role_command(self, user_id, full_text, channel_id):
        """Handle auto-role assignment commands."""
        try:
            # Handle case when no text is provided (just /autorole)
            if not full_text or full_text.strip() == "":
                # Auto-assign roles to all users
                self.send_ephemeral_message(channel_id, user_id, "🔄 Starting auto-role assignment for all users...")
                self.auto_assign_roles()
                self.send_ephemeral_message(channel_id, user_id, "✅ Auto-role assignment completed!")
                return
            
            parts = full_text.split()
            
            if len(parts) >= 1:
                action = parts[0].lower()
                
                if action == 'all':
                    # Auto-assign roles to all users
                    self.send_ephemeral_message(channel_id, user_id, "🔄 Starting auto-role assignment for all users...")
                    self.auto_assign_roles()
                    self.send_ephemeral_message(channel_id, user_id, "✅ Auto-role assignment completed!")
                    
                elif action == 'refresh':
                    # Force refresh all roles
                    self.send_ephemeral_message(channel_id, user_id, "🔄 Refreshing all user roles...")
                    self.refresh_all_roles()
                    self.send_ephemeral_message(channel_id, user_id, "✅ Role refresh completed!")
                    
                elif action == 'new':
                    # Assign roles to users without roles
                    self.send_ephemeral_message(channel_id, user_id, "🔄 Assigning roles to new users...")
                    self.assign_roles_to_new_users()
                    self.send_ephemeral_message(channel_id, user_id, "✅ New user role assignment completed!")
                    
                elif action == 'user' and len(parts) >= 2:
                    # Auto-assign roles to specific user
                    user_mention = parts[1]
                    target_user_id = self._extract_user_id_from_mention(user_mention)
                    
                    if target_user_id:
                        self.send_ephemeral_message(channel_id, user_id, f"🔄 Auto-assigning roles to {user_mention}...")
                        self.auto_assign_roles(user_id=target_user_id)
                        self.send_ephemeral_message(channel_id, user_id, f"✅ Auto-role assignment completed for {user_mention}!")
                    else:
                        self.send_ephemeral_message(channel_id, user_id, f"❌ Could not find user: {user_mention}")
                        
                else:
                    self._show_auto_role_help(channel_id, user_id)
            else:
                self._show_auto_role_help(channel_id, user_id)
                
        except Exception as e:
            print(f"❌ Error in auto-role command: {e}")
            self.send_ephemeral_message(channel_id, user_id, f"❌ Error: {e}")

    def _handle_refresh_roles_command(self, user_id, channel_id):
        """Handle refresh roles command."""
        try:
            self.send_ephemeral_message(channel_id, user_id, "🔄 Refreshing all user roles...")
            self.refresh_all_roles()
            self.send_ephemeral_message(channel_id, user_id, "✅ Role refresh completed!")
        except Exception as e:
            print(f"❌ Error in refresh roles command: {e}")
            self.send_ephemeral_message(channel_id, user_id, f"❌ Error: {e}")

    def _handle_new_user_roles_command(self, user_id, channel_id):
        """Handle new user roles command."""
        try:
            self.send_ephemeral_message(channel_id, user_id, "🔄 Assigning roles to new users...")
            self.assign_roles_to_new_users()
            self.send_ephemeral_message(channel_id, user_id, "✅ New user role assignment completed!")
        except Exception as e:
            print(f"❌ Error in new user roles command: {e}")
            self.send_ephemeral_message(channel_id, user_id, f"❌ Error: {e}")

    def _show_auto_role_help(self, channel_id, user_id):
        """Show help for auto-role commands."""
        # Create autorole help blocks
        autorole_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 Auto-Role Assignment Help",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Auto-Role Commands:*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• `/autorole` — Auto-assign roles to all users based on their Slack profile\n• `/autorole refresh` — Force refresh all user roles\n• `/autorole new` — Assign roles only to users who don't have any roles\n• `/autorole user @username` — Auto-assign roles to a specific user"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*How it works:*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• Analyzes job titles, departments, and custom fields\n• Assigns roles like: sales_swe, scrum_master, operations, marketing, etc.\n• Uses your existing org metadata service for intelligent assignment\n• Supports fallback rules when metadata is unavailable"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Examples:*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• `/autorole` — Assign roles to everyone\n• `/autorole user @alex` — Assign roles to Alex specifically\n• `/autorole refresh` — Quick refresh all roles"
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
                        "text": "💡 The bot analyzes job titles, departments, and Slack profile fields to automatically assign appropriate roles"
                    }
                ]
            }
        ]
        
        self.send_ephemeral_message(channel_id, user_id, "Auto-role assignment help:", blocks=autorole_blocks)

    def _extract_user_id_from_mention(self, mention):
        """Extract user ID from a Slack mention."""
        try:
            # Remove < > and @ symbols
            user_id = mention.strip('<>@')
            return user_id
        except:
            return None

    def _show_help(self, channel_id):
        """Show general help."""
        # Create general help blocks
        help_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 Slack Bot Commands",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Role Management:*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• `/role` — Show role help and manage roles (includes auto-assignment)\n• `/rolelist` — List all available roles and users"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Daily Workflow:*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• `/checkin` — Start your daily standup\n• `/health` — Send a health check prompt\n• `/kr [search]` — Search for a Key Result\n• `/blocked` — Report a new blocker\n• `/blocker` — View your current blockers"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Admin Commands:*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• `/test_standup` — Trigger daily standup (admin only)\n• `/test_health` — Trigger health check (admin only)"
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
                        "text": "💡 Use `/role` for complete role management including automatic assignment"
                    }
                ]
            }
        ]
        
        self.send_message(channel_id, "Here are all available commands:", blocks=help_blocks)

    def _handle_role_command(self, user_id, full_text, channel_id):
        """Handle role management commands."""
        try:
            user_name = self.get_user_name(user_id)
            
            if not full_text.strip():
                # Show role help and current roles
                roles = self.get_user_roles(user_id)
                
                # Create role help blocks
                role_blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "👥 Role Management Help",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Role Commands:*"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "• `/role` — Show this help and your current roles\n• `/role auto` — Auto-assign roles to all users\n• `/role refresh` — Force refresh all roles\n• `/role new` — Assign roles to new users only\n• `/role user @username` — Assign roles to specific user\n• `/role [role_name]` — Assign yourself a role\n• `/rolelist` — List all roles and users"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Available Roles:*"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "• `sales` — Sales\n• `scrum_master` — Scrum Master\n• `operations` — Operations\n• `marketing` — Marketing\n• `human_capital` — Human Capital\n• `finance` — Finance\n• `client_service` — Client Service Delivery\n• `admin` — Administrator"
                        }
                    },
                    {
                        "type": "divider"
                    }
                ]
                
                # Add current roles section
                if roles:
                    role_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Your Current Roles:* {', '.join(roles)}"
                        }
                    })
                else:
                    role_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Your Current Roles:* None assigned"
                        }
                    })
                
                role_blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💡 Use `/role auto` to automatically assign roles based on Slack profiles"
                        }
                    ]
                })
                
                self.send_dm(user_id, "Role management help:", blocks=role_blocks)
                return True
            
            # Parse command arguments
            parts = full_text.strip().split()
            command = parts[0].lower()
            
            # Handle auto-role subcommands
            if command == 'auto':
                self.send_dm(user_id, "🔄 Starting auto-role assignment for all users...")
                self.auto_assign_roles()
                self.send_dm(user_id, "✅ Auto-role assignment completed!")
                return True
                
            elif command == 'refresh':
                self.send_dm(user_id, "🔄 Refreshing all user roles...")
                self.refresh_all_roles()
                self.send_dm(user_id, "✅ Role refresh completed!")
                return True
                
            elif command == 'new':
                self.send_dm(user_id, "🔄 Assigning roles to new users...")
                self.assign_roles_to_new_users()
                self.send_dm(user_id, "✅ New user role assignment completed!")
                return True
                
            elif command == 'user' and len(parts) >= 2:
                user_mention = parts[1]
                target_user_id = self._extract_user_id_from_mention(user_mention)
                
                if target_user_id:
                    self.send_dm(user_id, f"🔄 Auto-assigning roles to {user_mention}...")
                    self.auto_assign_roles(user_id=target_user_id)
                    self.send_dm(user_id, f"✅ Auto-role assignment completed for {user_mention}!")
                else:
                    self.send_dm(user_id, f"❌ Could not find user: {user_mention}")
                return True
            
            # Handle manual role assignment (single role name)
            elif command in self.role_channels:
                role = command
                if user_id not in self.user_roles:
                    self.user_roles[user_id] = []
                
                if role not in self.user_roles[user_id]:
                    self.user_roles[user_id].append(role)
                    self.send_dm(user_id, f"✅ @{user_name} Added role: {role}")
                else:
                    self.send_dm(user_id, f"ℹ️ @{user_name} You already have the role: {role}")
                return True
            else:
                # Invalid command - show help
                self.send_dm(user_id, f"❌ Invalid role command: {command}\n\nUse `/role` to see all available commands.")
                return False
                
        except Exception as e:
            print(f"Error handling role command: {e}")
            self.send_dm(user_id, f"❌ Error processing role command: {e}")
            return False

    def _list_all_roles(self, channel_id):
        """List all roles and users."""
        try:
            # Create role list blocks
            role_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "👥 All Roles and Users",
                        "emoji": True
                    }
                }
            ]
            
            # Get all available roles
            available_roles = ['sales', 'scrum_master', 'operations', 'marketing', 'human_capital', 'finance', 'client_service', 'admin', 'engineering']
            
            # Get all users from Slack (use cached version to avoid rate limiting)
            try:
                users = self.get_slack_user_list()
            except Exception as e:
                print(f"❌ Error getting users list: {e}")
                users = []
            
            # Build role assignments
            role_assignments = {}
            for role in available_roles:
                role_assignments[role] = []
            
            # Check each user's roles from local storage (where auto-role assignment stores them)
            print(f"🔍 Role list: Checking {len(users)} users")
            print(f"🔍 Role list: Local storage has {len(self.user_roles)} users with roles")
            
            for user in users:
                if user.get('is_bot') or user.get('deleted'):
                    continue
                
                user_id = user['id']
                # Use local storage instead of dynamic org metadata
                user_roles = self.user_roles.get(user_id, [])
                
                if user_roles:
                    print(f"🔍 Role list: User {user.get('name', user_id)} has roles: {user_roles}")
                
                for role in user_roles:
                    if role in role_assignments:
                        role_assignments[role].append(user_id)
            
            # Display roles with users
            has_any_assignments = False
            for role, user_ids in role_assignments.items():
                if user_ids:
                    has_any_assignments = True
                    # Get user names for better display
                    user_names = []
                    valid_users = []
                    for user_id in user_ids:
                        try:
                            user_name = self.get_user_name(user_id)
                            user_names.append(f"@{user_name}")
                            valid_users.append(user_id)
                        except Exception as e:
                            # Skip invalid users and log the error
                            print(f"❌ Skipping invalid user {user_id}: {e}")
                            continue
                    
                    # Only show roles that have valid users
                    if valid_users:
                        role_blocks.append({
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{role}* ({len(valid_users)} user{'s' if len(valid_users) != 1 else ''}):\n{', '.join(user_names)}"
                            }
                        })
                    else:
                        role_blocks.append({
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{role}*: No valid users assigned"
                            }
                        })
                else:
                    role_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{role}*: No users assigned"
                        }
                    })
            
            if not has_any_assignments:
                role_blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "👥 All Roles and Users",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*No roles assigned yet.*\nUse `/role auto` to automatically assign roles to users."
                        }
                    }
                ]
            
            role_blocks.append({
                "type": "divider"
            })
            
            role_blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 Use `/role auto` to automatically assign roles based on Slack profiles\n\n*Note:* Users need job titles in their Slack profiles for accurate role assignment"
                    }
                ]
            })
            
            # Use send_dm if channel_id is a user ID, otherwise use send_message
            if channel_id.startswith('U'):
                self.send_dm(channel_id, "Role list:", blocks=role_blocks)
            else:
                self.send_message(channel_id, "Role list:", blocks=role_blocks)
                
        except Exception as e:
            print(f"Error listing roles: {e}")
            # Fallback to simple text
            try:
                if channel_id.startswith('U'):
                    self.send_dm(channel_id, f"❌ Error listing roles: {e}")
                else:
                    self.send_message(channel_id, f"❌ Error listing roles: {e}")
            except:
                pass

    def _add_user_role(self, user_mention, role, channel_id):
        """Add a role to a user."""
        try:
            # Extract user ID from mention
            user_id = user_mention.strip('<>@')
            
            if user_id not in self.user_roles:
                self.user_roles[user_id] = []
            
            if role not in self.user_roles[user_id]:
                self.user_roles[user_id].append(role)
                self.send_message(channel_id, f"✅ Added role '{role}' to {user_mention}")
            else:
                self.send_message(channel_id, f"ℹ️ {user_mention} already has role '{role}'")
        except Exception as e:
            print(f"Error adding user role: {e}")

    def _remove_user_role(self, user_mention, role, channel_id):
        """Remove a role from a user."""
        try:
            # Extract user ID from mention
            user_id = user_mention.strip('<>@')
            
            if user_id in self.user_roles and role in self.user_roles[user_id]:
                self.user_roles[user_id].remove(role)
                self.send_message(channel_id, f"✅ Removed role '{role}' from {user_mention}")
            else:
                self.send_message(channel_id, f"ℹ️ {user_mention} doesn't have role '{role}'")
        except Exception as e:
            print(f"Error removing user role: {e}")

    def _list_users_by_role(self, role, channel_id):
        """List users with a specific role."""
        try:
            users_with_role = self.get_users_by_role(role)
            if users_with_role:
                user_list = ', '.join([f"<@{user_id}>" for user_id in users_with_role])
                self.send_message(channel_id, f"*Users with role '{role}':* {user_list}")
            else:
                self.send_message(channel_id, f"No users found with role '{role}'")
        except Exception as e:
            print(f"Error listing users by role: {e}")

    def _list_role_channels(self, channel_id):
        """List role-based channel mappings."""
        try:
            channel_text = "*Role Channel Mappings:*\\n"
            for role, channel in self.role_channels.items():
                channel_text += f"• {role}: #{channel}\\n"
            
            self.send_message(channel_id, channel_text)
        except Exception as e:
            print(f"Error listing role channels: {e}")

    def _show_role_suggestions(self, channel_id):
        """Show available roles for autocomplete."""
        try:
            roles = list(self.role_channels.keys())
            role_text = f"*Available roles:* {', '.join(roles)}"
            self.send_message(channel_id, role_text)
        except Exception as e:
            print(f"Error showing role suggestions: {e}")

    def _show_interactive_role_selector(self, channel_id, user_mention, action_type):
        """Show interactive dropdown to select roles."""
        try:
            roles = list(self.role_channels.keys())
            
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Select a role to {action_type} for {user_mention}:"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "static_select",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Choose a role"
                            },
                            "options": [
                                {
                                    "text": {"type": "plain_text", "text": role},
                                    "value": f"{action_type}_{role}_{user_mention}"
                                } for role in roles
                            ],
                            "action_id": "role_selector"
                        }
                    ]
                }
            ]
            
            self.send_message(channel_id, "", blocks=blocks)
        except Exception as e:
            print(f"Error showing role selector: {e}")

    def get_kr_assignees(self, kr_name):
        """Get PM, lead, or assigned resolver for a KR from Coda."""
        try:
            if not self.coda:
                return None
            
            # This would need to be implemented based on your Coda structure
            # For now, return None
            return None
        except Exception as e:
            print(f"Error getting KR assignees: {e}")
            return None

    def handle_mark_resolved_click(self, payload):
        """Handle mark resolved button click - opens resolution modal for channel, direct resolve for DM."""
        try:
            user_id = payload['user']['id']
            user_name = self.get_user_name(user_id)
            value = payload['actions'][0]['value']
            channel_id = payload['channel']['id']
            message_ts = payload['message']['ts']
            
            # Parse value: blocked_user_id_kr_name_resolver_id
            parts = value.split('_')
            if len(parts) >= 3:
                blocked_user_id = parts[0]
                kr_name = parts[1]
                resolver_id = parts[2]
                
                # For now, directly resolve
                self._resolve_blocker_directly(
                    "temp_id", blocked_user_id, kr_name, "Blocker resolved", 
                    resolver_id, user_name, "Resolved via button click", 
                    channel_id, message_ts
                )
            
        except Exception as e:
            print(f"Error handling mark resolved click: {e}")

    def _resolve_blocker_directly(self, blocker_id, blocked_user_id, kr_name, blocker_description,
                                resolver_id, resolver_name, resolution_notes, channel_id, message_ts, blocker_info=None):
        """Directly resolve a blocker without modal (for DM responses)."""
        try:
            # Update message to show resolution
            updated_text = f"✅ *Blocker for {kr_name} has been resolved by @{resolver_name}*\n\n"
            updated_text += f"*Resolved by:* @{resolver_name}\n"
            updated_text += f"*Resolution notes:* {resolution_notes}\n"
            updated_text += f"*Status:* Complete"
            
            self.update_message(channel_id, message_ts, updated_text)
            
            # Notify the blocked user via DM
            self.send_dm(blocked_user_id, f"🎉 Your blocker for {kr_name} has been resolved by @{resolver_name}!")
            
            # Update in Coda if available
            if self.coda and blocker_info:
                self.coda.mark_blocker_complete(row_id=blocker_id, resolution_notes="Resolved via direct resolution")
                
                # Send completion notification to leads channel
                try:
                    from datetime import datetime
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    completion_message = f"🎉 *Blocker Resolved* - @{resolver_name} has successfully resolved a blocker!"
                    completion_message += f"\n• *KR:* {kr_name}"
                    completion_message += f"\n• *Resolved by:* @{resolver_name}"
                    completion_message += f"\n• *Resolved at:* {current_time}"
                    completion_message += f"\n• *Resolution notes:* {resolution_notes}"
                    completion_message += f"\n• *Status:* Blocker marked complete in Coda"
                    
                    self.send_completion_message_to_accessible_channel(completion_message)
                    print(f"✅ Sent completion message to leads channel")
                except Exception as channel_error:
                    print(f"⚠️ Error sending completion message to channel: {channel_error}")
            
            print(f"✅ Blocker resolved by {resolver_name}")
            
        except Exception as e:
            print(f"Error resolving blocker directly: {e}")

    def handle_blocker_followup_response(self, user_id, action_value):
        """Handle responses to 24-hour blocker follow-up."""
        try:
            user_name = self.get_user_name(user_id)
            
            if action_value == 'blocker_resolved':
                self.send_dm(user_id, f"🎉 Great news! Thanks for letting us know, @{user_name}!")
            elif action_value == 'blocker_still_blocked':
                self.send_dm(user_id, f"<@{user_id}> Thanks for the update. Let me escalate this to get you the help you need.")
                # Escalate to next level
                self.escalate_by_hierarchy('blocker', f"User {user_name} still blocked after 24 hours", f"User ID: {user_id}")
            elif action_value == 'blocker_need_help':
                self.send_dm(user_id, f"<@{user_id}> I'll get you help right away!")
                # Immediate escalation
                self.escalate_by_hierarchy('blocker', f"User {user_name} needs immediate help", f"User ID: {user_id}")
            
        except Exception as e:
            print(f"Error handling blocker followup response: {e}")

    def claim_blocker(self, blocker_id, claimer_id, claimer_name, channel_id, message_ts):
        """Handle claiming a blocker by a lead."""
        try:
            # Update message to show claim
            updated_text = f"👤 *Blocker claimed by @{claimer_name}*\n\n"
            updated_text += f"*Claimed by:* @{claimer_name}\n"
            updated_text += f"*Status:* In Progress"
            
            self.update_message(channel_id, message_ts, updated_text)
            
            # Add claim button
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": updated_text
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Update Progress"},
                            "action_id": "update_progress",
                            "value": blocker_id
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Mark Resolved"},
                            "style": "primary",
                            "action_id": "mark_resolved",
                            "value": f"{blocker_id}_{claimer_id}"
                        }
                    ]
                }
            ]
            
            self.update_message(channel_id, message_ts, "", blocks=blocks)
            
            print(f"✅ Blocker claimed by {claimer_name}")
            
        except Exception as e:
            print(f"Error claiming blocker: {e}")

    def open_progress_update_modal(self, blocker_id, user_id, username, channel_id, message_ts, trigger_id):
        """Open a modal for updating blocker progress."""
        try:
            blocks = [
                {
                    "type": "input",
                    "block_id": "progress_input",
                    "label": {"type": "plain_text", "text": "Progress Update"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "progress_text",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "What progress have you made on this blocker?"}
                    }
                }
            ]
            
            self.open_modal(
                trigger_id=trigger_id,
                title="Update Blocker Progress",
                blocks=blocks,
                submit_text="Submit Progress",
                callback_id="progress_update_submit"
            )
            
            # Store blocker info for modal submission
            self.tracked_blockers[user_id] = blocker_id
            
        except Exception as e:
            print(f"Error opening progress update modal: {e}")

    def handle_progress_update_modal_submission(self, payload):
        """Handle progress update modal submission."""
        try:
            user_id = payload['user']['id']
            user_name = self.get_user_name(user_id)
            values = payload['view']['state']['values']
            
            # Extract progress text
            progress_text = values.get('progress_input', {}).get('progress_text', {}).get('value', '')
            blocker_id = self.tracked_blockers.get(user_id)
            
            if blocker_id:
                # Update blocker message with progress
                self.update_blocker_message_with_progress(blocker_id, payload['channel']['id'], payload['message']['ts'])
                
                # Send confirmation
                self.send_dm(user_id, f"✅ Progress update submitted for blocker!")
                
                # Clear tracked blocker
                self.tracked_blockers.pop(user_id, None)
            
        except Exception as e:
            print(f"Error handling progress update submission: {e}")

    def get_kr_progress_from_coda(self, kr_name):
        """Fetch KR progress from CODA_TABLE_ID4."""
        try:
            if not self.coda:
                return None
            
            # This would need to be implemented based on your Coda structure
            # For now, return None
            return None
        except Exception as e:
            print(f"Error getting KR progress from Coda: {e}")
            return None

    def view_blocker_details(self, blocker_id, channel_id, message_ts):
        """Show detailed information about a blocker in a thread or update existing thread."""
        try:
            # This would fetch detailed blocker info from Coda
            # For now, just acknowledge
            self.send_message(channel_id, f"📋 Blocker details for ID: {blocker_id}", thread_ts=message_ts)
        except Exception as e:
            print(f"Error viewing blocker details: {e}")

    def get_accessible_channels(self):
        """Get list of channels the bot has access to."""
        try:
            response = self.client.conversations_list(types="public_channel,private_channel")
            return response['channels']
        except SlackApiError as e:
            print(f"Error getting accessible channels: {e}")
            return []

    def send_completion_message_to_accessible_channel(self, completion_message):
        """Send completion message to the leads channel."""
        try:
            # Send to the leads channel specifically
            if hasattr(self, 'config') and hasattr(self.config, 'SLACK_ESCALATION_CHANNEL'):
                leads_channel = self.config.SLACK_ESCALATION_CHANNEL
                self.send_message(leads_channel, completion_message)
                print(f"✅ Sent completion message to leads channel: {leads_channel}")
            else:
                # Fallback to first accessible channel if leads channel not configured
                channels = self.get_accessible_channels()
                if channels:
                    self.send_message(channels[0]['id'], completion_message)
                    print(f"✅ Sent completion message to fallback channel: {channels[0]['name']}")
                else:
                    print("No accessible channels found")
        except Exception as e:
            print(f"Error sending completion message: {e}")

    def handle_blocker_completion(self, blocker_id, channel_id, message_ts, resolver_id=None, resolver_name=None):
        """Handle blocker completion - append completion confirmation and update KR status."""
        try:
            print(f"🔍 DEBUG: Starting blocker completion for ID: {blocker_id}")
            
            # Get resolver info if not provided
            if not resolver_id:
                resolver_id = "unknown"
            if not resolver_name:
                resolver_name = "Unknown User"
            
            # Mark blocker as complete in Coda
            if self.coda:
                print(f"🔍 DEBUG: Attempting to mark blocker {blocker_id} as complete in Coda")
                
                # First, get blocker details to find the KR name
                blocker_details = self.coda.get_blocker_by_id(blocker_id)
                kr_name = None
                if blocker_details:
                    kr_name = blocker_details.get("kr_name")
                    print(f"🔍 DEBUG: Found KR name for blocker: {kr_name}")
                
                # Mark blocker as complete
                success = self.coda.mark_blocker_complete(row_id=blocker_id, resolution_notes="Resolved via completion")
                if success:
                    print(f"✅ Successfully marked blocker {blocker_id} as complete in Coda")
                    
                    # Update KR status to 'Unblocked' if we have the KR name
                    if kr_name:
                        try:
                            kr_success = self.coda.resolve_blocker_from_kr(
                                kr_name=kr_name,
                                resolved_by=resolver_name,
                                resolved_by_id=resolver_id
                            )
                            if kr_success:
                                print(f"✅ Successfully updated KR '{kr_name}' status to 'Unblocked'")
                            else:
                                print(f"⚠️ Failed to update KR '{kr_name}' status, but blocker was marked complete")
                        except Exception as kr_error:
                            print(f"⚠️ Error updating KR status: {kr_error}")
                            # Continue with blocker completion even if KR update fails
                    else:
                        print(f"⚠️ Could not find KR name for blocker {blocker_id}, skipping KR status update")
                    
                    # Try to update the message, but don't fail if it doesn't work
                    try:
                        completion_text = "\n\n✅ *BLOCKER RESOLVED* - This blocker has been marked as complete."
                        if kr_name:
                            completion_text += f" KR '{kr_name}' status updated to 'Unblocked'."
                        update_result = self.update_message(channel_id, message_ts, completion_text, append=True)
                        if update_result:
                            print(f"✅ Successfully updated message with completion text")
                        else:
                            print(f"⚠️ Could not update message, but blocker was marked complete")
                    except Exception as update_error:
                        print(f"⚠️ Error updating message: {update_error}")
                    
                    # Send completion message to leads channel
                    try:
                        from datetime import datetime
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        completion_message = f"🎉 *Blocker Resolved* - @{resolver_name} has successfully resolved a blocker!"
                        if kr_name:
                            completion_message += f"\n• *KR:* {kr_name}"
                        completion_message += f"\n• *Resolved by:* @{resolver_name}"
                        completion_message += f"\n• *Resolved at:* {current_time}"
                        completion_message += f"\n• *Status:* KR status updated to 'Unblocked' in Coda"
                        
                        self.send_completion_message_to_accessible_channel(completion_message)
                        print(f"✅ Sent completion message to leads channel")
                    except Exception as channel_error:
                        print(f"⚠️ Error sending completion message to channel: {channel_error}")
                        
                else:
                    print(f"❌ Failed to mark blocker {blocker_id} as complete in Coda")
                    # Still try to update the message as a fallback
                    try:
                        completion_text = "\n\n⚠️ *BLOCKER COMPLETION ATTEMPTED* - Coda update failed, but action was taken."
                        self.update_message(channel_id, message_ts, completion_text, append=True)
                    except Exception as update_error:
                        print(f"⚠️ Error updating message: {update_error}")
            else:
                print(f"⚠️ Coda service not available, marking blocker complete locally")
                # Fallback if Coda is not available
                try:
                    completion_text = "\n\n✅ *BLOCKER RESOLVED* - This blocker has been marked as complete (local only)."
                    self.update_message(channel_id, message_ts, completion_text, append=True)
                except Exception as update_error:
                    print(f"⚠️ Error updating message: {update_error}")
                
        except Exception as e:
            print(f"❌ Error handling blocker completion: {e}")
            import traceback
            traceback.print_exc()

    def auto_assign_roles(self, user_id: str = None, force_refresh: bool = False):
        """
        Automatically assign roles to users based on their Slack profile and organizational metadata.
        
        Args:
            user_id: Specific user to assign roles to (if None, assigns to all users)
            force_refresh: Whether to force refresh even if roles already exist
        """
        try:
            if user_id:
                # Assign roles to specific user
                self._assign_roles_to_user(user_id, force_refresh)
            else:
                # Assign roles to all users
                print("🔄 Starting auto-role assignment for all users...")
                users = self.get_slack_user_list()
                
                assigned_count = 0
                for user in users:
                    if not user.get('is_bot') and not user.get('deleted'):
                        if self._assign_roles_to_user(user['id'], force_refresh):
                            assigned_count += 1
                
                print(f"✅ Auto-role assignment completed. Assigned roles to {assigned_count} users.")
                
        except Exception as e:
            print(f"❌ Error in auto-role assignment: {e}")
            logger.error(f"Auto-role assignment error: {e}")

    def _assign_roles_to_user(self, user_id: str, force_refresh: bool = False) -> bool:
        """
        Assign roles to a specific user based on their profile and metadata.
        
        Args:
            user_id: Slack user ID
            force_refresh: Whether to force refresh even if roles already exist
            
        Returns:
            True if roles were assigned/updated, False otherwise
        """
        try:
            # Get user info and determine roles
            user_info = self.get_user_info(user_id)
            if not user_info:
                print(f"❌ Could not get user info for {user_id}")
                return False
            
            # Get auto-assigned roles from org metadata
            auto_roles = self._get_auto_assigned_roles(user_id, user_info)
            
            # Always update the user's roles in the local storage for display purposes
            if auto_roles:
                self.user_roles[user_id] = auto_roles
                user_name = user_info.get('real_name', user_info.get('name', 'Unknown'))
                print(f"✅ Auto-assigned roles to {user_name} ({user_id}): {', '.join(auto_roles)}")
                return True
            else:
                # Even if no roles found, store empty list to avoid repeated processing
                self.user_roles[user_id] = []
                user_name = user_info.get('real_name', user_info.get('name', 'Unknown'))
                print(f"ℹ️ No roles found for {user_name} ({user_id})")
            return False
            
        except Exception as e:
            print(f"❌ Error assigning roles to user {user_id}: {e}")
            return False

    def _get_auto_assigned_roles(self, user_id: str, user_info: dict) -> List[str]:
        """
        Get auto-assigned roles for a user based on their profile and metadata.
        
        Args:
            user_id: Slack user ID
            user_info: User info from Slack API
            
        Returns:
            List of role names
        """
        roles = []
        
        try:
            # Get department and SME from org metadata service
            if self.org_metadata:
                print(f"🔍 Getting org metadata for user {user_id}")
                metadata = self.org_metadata.get_user_department_and_sme(user_id)
                print(f"🔍 Org metadata result: {metadata}")
                
                # Add department as role (don't duplicate with SME)
                if metadata.get('department'):
                    roles.append(metadata['department'])
                    print(f"🔍 Added department role: {metadata['department']}")
                
                # Only add SME if it's different from department
                if metadata.get('sme') and metadata.get('sme') != metadata.get('department'):
                    roles.append(metadata['sme'])
                    print(f"🔍 Added SME role: {metadata['sme']}")
                
                # Add leadership roles based on title
                title = metadata.get('user_info', {}).get('title', '').lower()
                print(f"🔍 User title: {title}")
                if any(keyword in title for keyword in ['lead', 'manager', 'director', 'vp', 'head']):
                    roles.append('lead')
                    print(f"🔍 Added leadership role: lead")
                if any(keyword in title for keyword in ['ceo', 'cto', 'cfo', 'coo', 'executive']):
                    roles.append('admin')
                    print(f"🔍 Added admin role: admin")
            
            # Fallback: analyze profile data directly
            if not roles:
                print(f"🔍 No roles from org metadata, trying profile analysis")
                roles = self._analyze_profile_for_roles(user_info)
                print(f"🔍 Profile analysis result: {roles}")
            
            # Add default roles if none found
            if not roles:
                print(f"🔍 No roles found, adding default member role")
                roles = ['member']
            
            final_roles = list(set(roles))  # Remove duplicates
            print(f"🔍 Final roles for {user_id}: {final_roles}")
            return final_roles
            
        except Exception as e:
            print(f"❌ Error getting auto-assigned roles for {user_id}: {e}")
            return ['member']  # Default fallback

    def _analyze_profile_for_roles(self, user_info: dict) -> List[str]:
        """
        Analyze user profile data to determine roles.
        
        Args:
            user_info: User info from Slack API
            
        Returns:
            List of role names
        """
        roles = []
        
        try:
            # Analyze job title
            title = user_info.get('profile', {}).get('title', '').lower()
            
            # Department-based roles - Updated for your org structure
            if any(keyword in title for keyword in ['sales engineer', 'sales swe', 'sales', 'account', 'business development', 'bd', 'revenue']):
                roles.append('sales')
            elif any(keyword in title for keyword in ['engineer', 'developer', 'dev', 'software', 'backend', 'frontend', 'fullstack', 'swe', 'software engineer']):
                roles.append('engineering')
            elif any(keyword in title for keyword in ['scrum master', 'scrum', 'agile', 'sprint', 'task assignment', 'project management']):
                roles.append('scrum_master')
            elif any(keyword in title for keyword in ['operations', 'ops', 'devops', 'infrastructure', 'platform', 'system admin']):
                roles.append('operations')
            elif any(keyword in title for keyword in ['marketing', 'growth', 'seo', 'content', 'social media', 'brand', 'digital marketing']):
                roles.append('marketing')
            elif any(keyword in title for keyword in ['hr', 'human resources', 'people', 'talent', 'recruiting', 'human capital', 'people ops']):
                roles.append('human_capital')
            elif any(keyword in title for keyword in ['finance', 'accounting', 'fp&a', 'controller', 'cfo', 'financial', 'bookkeeping']):
                roles.append('finance')
            elif any(keyword in title for keyword in ['client service', 'customer service', 'support', 'customer success', 'cs', 'help desk', 'technical support', 'client delivery']):
                roles.append('client_service')
            
            # Leadership roles
            if any(keyword in title for keyword in ['lead', 'manager', 'director', 'vp', 'head']):
                roles.append('lead')
            if any(keyword in title for keyword in ['ceo', 'cto', 'cfo', 'coo', 'executive']):
                roles.append('admin')
            
            # Analyze custom fields if available
            custom_fields = user_info.get('profile', {}).get('fields', {})
            for field_id, field_data in custom_fields.items():
                field_value = field_data.get('value', '').lower()
                
                # Department field - Updated for your org structure
                if 'department' in field_id.lower() or 'team' in field_id.lower():
                    if any(keyword in field_value for keyword in ['sales', 'sales engineer', 'sales swe']):
                        roles.append('sales')
                    elif any(keyword in field_value for keyword in ['engineering', 'dev', 'tech', 'software']):
                        roles.append('engineering')
                    elif any(keyword in field_value for keyword in ['scrum', 'agile', 'project management']):
                        roles.append('scrum_master')
                    elif any(keyword in field_value for keyword in ['operations', 'ops', 'devops', 'infrastructure']):
                        roles.append('operations')
                    elif any(keyword in field_value for keyword in ['marketing', 'digital marketing']):
                        roles.append('marketing')
                    elif any(keyword in field_value for keyword in ['hr', 'human resources', 'human capital', 'people']):
                        roles.append('human_capital')
                    elif any(keyword in field_value for keyword in ['finance', 'accounting', 'financial']):
                        roles.append('finance')
                    elif any(keyword in field_value for keyword in ['client service', 'customer service', 'support']):
                        roles.append('client_service')
            
            return list(set(roles))  # Remove duplicates
            
        except Exception as e:
            print(f"❌ Error analyzing profile for roles: {e}")
            return []

    def refresh_all_roles(self):
        """Refresh roles for all users (force update)."""
        print("🔄 Refreshing roles for all users...")
        self.auto_assign_roles(force_refresh=True)

    def assign_roles_to_new_users(self):
        """Assign roles to users who don't have any roles yet."""
        print("🔄 Assigning roles to users without roles...")
        users = self.get_slack_user_list()
        
        assigned_count = 0
        for user in users:
            if not user.get('is_bot') and not user.get('deleted'):
                user_id = user['id']
                current_roles = self.get_user_roles(user_id)
                
                if not current_roles:
                    if self._assign_roles_to_user(user_id):
                        assigned_count += 1
        
        print(f"✅ Assigned roles to {assigned_count} new users.")