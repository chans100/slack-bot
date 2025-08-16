import os
import time
import threading
import schedule
import hashlib
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from .coda_service import CodaService
from .org_metadata_service import OrgMetadataService
from .events import (
    handle_interactive_components,
    handle_slash_command,
    handle_mentor_response,
    handle_kr_continue_submit,
    handle_blocker_continue_submit,
    handle_view_details,
    handle_claim_blocker,
    handle_blocker_followup_response,
    handle_view_blockers_with_sprint,
    handle_open_view_blockers_modal
)

class DailyStandupBot:
    """Main bot class for handling daily standups and health checks."""
    
    def __init__(self, slack_token: str, app_token: str, coda_doc_id: str, coda_api_token: str):
        self.client = WebClient(token=slack_token)
        self.app_token = app_token
        self.config = type('Config', (), {
            'SLACK_ESCALATION_CHANNEL': os.getenv('SLACK_ESCALATION_CHANNEL', 'leads')
        })()
        
        # Initialize services
        self.coda = CodaService(coda_doc_id, coda_api_token) if coda_doc_id and coda_api_token else None
        self.org_metadata = OrgMetadataService()
        
        # Initialize Socket Mode client
        self.socket_client = SocketModeClient(
            app_token=app_token,
            web_client=self.client
        )
        
        # Track active blockers for follow-up
        self.active_blockers = {}
        
        # Pending data for multi-step forms
        self.kr_pending_data = {}
        self.blocker_pending_data = {}
        
        # Auto-assign roles on startup
        self._assign_roles_on_startup()
        
        print("🤖 Starting Daily Standup Bot in Socket Mode...")
    
    def _assign_roles_on_startup(self):
        """Auto-assign roles to all users on startup."""
        try:
            print("🔄 Auto-assigning roles to users on startup...")
            self._assign_roles_to_all_users()
        except Exception as e:
            print(f"❌ Error in auto-role assignment: {e}")
    
    def _assign_roles_to_all_users(self):
        """Assign roles to all users in the workspace."""
        try:
            print("🔄 Starting auto-role assignment for all users...")
            
            # Get all users
            response = self.client.users_list()
            if not response['ok']:
                print("❌ Failed to get users list")
                return
            
            users = response['users']
            assigned_count = 0
            
            for user in users:
                if user.get('is_bot') or user.get('is_app_user') or user.get('deleted'):
                    continue
                
                try:
                    user_id = user['id']
                    user_name = user.get('real_name', user.get('name', 'Unknown'))
                    
                    # Auto-assign roles
                    roles = self._get_auto_assigned_roles(user_id, user)
                    if roles:
                        print(f"✅ Auto-assigned roles to {user_name} ({user_id}): {', '.join(roles)}")
                        assigned_count += 1
                    
                    # Small delay to avoid rate limiting
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"⚠️ Error assigning roles to user {user.get('name', 'Unknown')}: {e}")
                    continue
            
            print(f"✅ Auto-role assignment completed. Assigned roles to {assigned_count} users.")
            
        except Exception as e:
            print(f"❌ Error in auto-role assignment: {e}")
            import logging
            logging.error(f"Auto-role assignment error: {e}")
    
    def _get_auto_assigned_roles(self, user_id: str, user_data: dict) -> list:
        """Auto-assign roles based on user profile and org metadata."""
        try:
            roles = []
            
            # Get user info from Slack
            user_info = self.client.users_info(user_id=user_id)
            if user_info['ok']:
                user = user_info['user']
                profile = user.get('profile', {})
                
                print(f"🔍 DEBUG: get_user_info called with user_id: {user_id}")
                print(f"🔍 DEBUG: users_info API response: {user_info}")
                
                # Extract user data
                user_data_extracted = {
                    'id': user.get('id'),
                    'name': user.get('name'),
                    'is_bot': user.get('is_bot'),
                    'updated': user.get('updated'),
                    'is_app_user': user.get('is_app_user'),
                    'team_id': user.get('team_id'),
                    'deleted': user.get('deleted'),
                    'color': user.get('color'),
                    'is_email_confirmed': user.get('is_email_confirmed'),
                    'real_name': profile.get('real_name'),
                    'tz': profile.get('tz'),
                    'tz_label': profile.get('tz_label'),
                    'tz_offset': profile.get('tz_offset'),
                    'is_admin': user.get('is_admin'),
                    'is_owner': user.get('is_owner'),
                    'is_primary_owner': user.get('is_primary_owner'),
                    'is_restricted': user.get('is_restricted'),
                    'is_ultra_restricted': user.get('is_ultra_restricted'),
                    'who_can_share_contact_card': user.get('who_can_share_contact_card'),
                    'profile': profile
                }
                
                print(f"🔍 DEBUG: Extracted user data: {user_data_extracted}")
                
                # Analyze Slack profile
                print(f"🔍 Analyzing Slack profile for user {user_id}")
                profile_title = profile.get('title', '')
                print(f"🔍 Profile analysis complete. Found roles: {roles}")
                
                # Get org metadata
                print(f"🔍 Getting org metadata for user {user_id}")
                org_result = self.org_metadata.get_user_metadata(user_id, user_data_extracted)
                print(f"🔍 Org metadata result: {org_result}")
                
                # Add department role from org metadata
                if org_result and org_result.get('department'):
                    department = org_result['department']
                    roles.append(department)
                    print(f"🔍 Added department role: {department}")
                
                # Analyze profile title for additional roles
                print(f"🔍 Metadata title: {profile_title}")
                
                # Add role-based logic here if needed
                
                print(f"🔍 Final roles for {user_id}: {roles}")
                
            return roles
            
        except Exception as e:
            print(f"❌ Error getting auto-assigned roles: {e}")
            return []
    
    def run(self):
        """Start the bot in Socket Mode."""
        try:
            print("🚀 Starting bot in Socket Mode...")
            
            # Start scheduler in background
            self._start_scheduler()
            
            # Start Socket Mode client
            print("🔌 Starting Socket Mode client...")
            self.socket_client.connect()
            
            # Keep the bot running
            while True:
                try:
                    # Process Socket Mode requests
                    request = self.socket_client.recv()
                    if request.type == SocketModeRequest.TYPE:
                        self._handle_socket_request(request)
                except Exception as e:
                    print(f"❌ Error in Socket Mode loop: {e}")
                    time.sleep(1)
                    
        except Exception as e:
            print(f"❌ Error starting Socket Mode client: {e}")
    
    def _handle_socket_request(self, request: SocketModeRequest):
        """Handle incoming Socket Mode requests."""
        try:
            if request.type == "events_api":
                # Handle events
                event = request.payload.get("event", {})
                event_type = event.get("type")
                
                if event_type == "message":
                    # Handle message events
                    pass
                    
            elif request.type == "interactive":
                # Handle interactive components (buttons, modals)
                response = handle_interactive_components(self, request.payload)
                self.socket_client.send_socket_mode_response(SocketModeResponse(request.id, response))
                
            elif request.type == "slash_commands":
                # Handle slash commands
                response = handle_slash_command(self, request.payload)
                self.socket_client.send_socket_mode_response(SocketModeResponse(request.id, response))
                
            else:
                # Acknowledge unknown request types
                self.socket_client.send_socket_mode_response(SocketModeResponse(request.id, {"text": "OK"}))
                
        except Exception as e:
            print(f"❌ Error handling Socket Mode request: {e}")
            # Send error response
            try:
                self.socket_client.send_socket_mode_response(SocketModeResponse(request.id, {"text": "Error"}))
            except:
                pass
    
    def _start_scheduler(self):
        """Start the background scheduler."""
        try:
            print("🔄 Scheduler loop started")
            
            # Schedule daily standup at 9:00 AM
            schedule.every().day.at("09:00").do(self._send_daily_standup)
            
            # Schedule health check at 9:00 AM
            schedule.every().day.at("09:00").do(self._send_health_check)
            
            # Schedule blocker followup check every minute (for testing)
            schedule.every(1).minutes.do(self._check_blocker_followups)
            
            # Start scheduler in background thread
            def run_scheduler():
                while True:
                    schedule.run_pending()
                    time.sleep(60)  # Check every minute
            
            scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
            scheduler_thread.start()
            
            print("✅ Bot started successfully!")
            print("📅 Daily standup and health check scheduled for 9:00 AM")
            print("⏰ Blocker followup check scheduled every 1 minute (for testing)")
            print("⏰ 24-hour followup delay set to 2 minutes for testing")
            print("🤖 Auto-role assignment completed on startup")
            
        except Exception as e:
            print(f"❌ Error starting scheduler: {e}")
    
    def _send_daily_standup(self):
        """Send daily standup reminder."""
        try:
            # Get all users
            response = self.client.users_list()
            if not response['ok']:
                return
            
            users = response['users']
            for user in users:
                if user.get('is_bot') or user.get('is_app_user') or user.get('deleted'):
                    continue
                
                try:
                    self.send_dm(user['id'], "📅 *Daily Standup Reminder*\n\nIt's time for your daily standup! Use `/checkin` to submit your update.")
                except Exception as e:
                    print(f"⚠️ Error sending standup reminder to {user.get('name', 'Unknown')}: {e}")
                    
        except Exception as e:
            print(f"❌ Error sending daily standup: {e}")
    
    def _send_health_check(self):
        """Send health check reminder."""
        try:
            # Get all users
            response = self.client.users_list()
            if not response['ok']:
                return
            
            users = response['users']
            for user in users:
                if user.get('is_bot') or user.get('is_app_user') or user.get('deleted'):
                    continue
                
                try:
                    self.send_health_check_reminder(user['id'])
                except Exception as e:
                    print(f"⚠️ Error sending health check to {user.get('name', 'Unknown')}: {e}")
                    
        except Exception as e:
            print(f"❌ Error sending health check: {e}")
    
    def send_health_check_reminder(self, user_id: str):
        """Send health check reminder to a specific user."""
        try:
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "💚 *How are you feeling today?*\n\nTake a moment to check in with yourself and let the team know how you're doing."
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "😊 Great", "emoji": True},
                            "action_id": "great",
                            "style": "primary"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "😐 Okay", "emoji": True},
                            "action_id": "okay"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "😕 Not great", "emoji": True},
                            "action_id": "not_great",
                            "style": "danger"
                        }
                    ]
                }
            ]
            
            self.client.chat_postMessage(
                channel=user_id,
                text="How are you feeling today?",
                blocks=blocks
            )
            
        except Exception as e:
            print(f"❌ Error sending health check reminder: {e}")
    
    def _check_blocker_followups(self):
        """Check for blockers that need follow-up."""
        try:
            current_time = datetime.now()
            print(f"🔍 Checking blocker followups at {current_time.strftime('%H:%M:%S')} - {len(self.active_blockers)} tracked blockers")
            
            # Check if it's time for follow-ups
            BLOCKER_FOLLOWUP_DELAY_HOURS = 2 / 60  # 2 minutes for testing
            print(f"🔍 DEBUG: BLOCKER_FOLLOWUP_DELAY_HOURS = {BLOCKER_FOLLOWUP_DELAY_HOURS}")
            print(f"🔍 DEBUG: Current time: {current_time}")
            print(f"🔍 DEBUG: Tracked blockers: {list(self.active_blockers.keys())}")
            
            # Load unresolved blockers from Coda
            print("🔍 Loading unresolved blockers from Coda...")
            unresolved_blockers = self.coda.get_unresolved_blockers() if self.coda else []
            
            for blocker in unresolved_blockers:
                try:
                    # Check if this blocker needs follow-up
                    created_at = blocker.get('created_at')
                    if not created_at:
                        continue
                    
                    # Parse creation time
                    if isinstance(created_at, str):
                        created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        created_time = created_at
                    
                    # Check if enough time has passed
                    time_diff = current_time - created_time
                    hours_diff = time_diff.total_seconds() / 3600
                    
                    if hours_diff >= BLOCKER_FOLLOWUP_DELAY_HOURS:
                        # Send follow-up
                        user_id = blocker.get('user_id')
                        kr_name = blocker.get('kr_name', 'Unknown KR')
                        
                        if user_id and user_id not in self.active_blockers:
                            self.send_blocker_followup(user_id, kr_name)
                            
                except Exception as e:
                    print(f"⚠️ Error processing blocker followup: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Error checking blocker followups: {e}")
    
    def send_blocker_followup(self, user_id: str, kr_name: str):
        """Send 24-hour follow-up message for a blocker."""
        try:
            # Generate unique blocker ID
            blocker_id = hashlib.md5(f"{user_id}_{kr_name}_{int(time.time())}".encode()).hexdigest()
            
            # Track this blocker
            self.active_blockers[user_id] = {
                'kr_name': kr_name,
                'blocker_id': blocker_id,
                'followup_sent_at': datetime.now()
            }
            
            # Send follow-up message
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⏰ *24-Hour Blocker Follow-up*\n\nIt's been 24 hours since you reported being blocked on *{kr_name}*. How are things going?"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Resolved"},
                            "action_id": "blocker_resolved_24hr",
                            "value": f"{user_id}_{kr_name}",
                            "style": "primary"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Re-escalate"},
                            "action_id": "blocker_reescalate_24hr",
                            "value": f"{user_id}_{kr_name}"
                        }
                    ]
                }
            ]
            
            self.client.chat_postMessage(
                channel=user_id,
                text=f"24-Hour Blocker Follow-up for {kr_name}",
                blocks=blocks
            )
            
            print(f"✅ Sent 24-hour blocker followup to {user_id} for {kr_name}")
            
        except Exception as e:
            print(f"❌ Error sending blocker followup: {e}")
    
    def escalate_blocker_with_details(self, user_id: str, user_name: str, blocker_description: str, kr_name: str, urgency: str = "medium", notes: str = "", sprint_number: Optional[int] = None):
        """Escalate a blocker to the team with full details."""
        try:
            # Save to Coda first
            if self.coda:
                success = self.coda.add_blocker(user_id, user_name, blocker_description, kr_name, urgency, notes, sprint_number)
                if success:
                    print(f"✅ Blocker saved to Coda for {user_name}")
                else:
                    print(f"⚠️ Failed to save blocker to Coda for {user_name}")
            
            # Track blocker for follow-up
            self.track_blocker_for_followup(user_id, kr_name)
            
            # Escalate to team channel
            escalation_channel = f"#{self.config.SLACK_ESCALATION_CHANNEL}" if self.config.SLACK_ESCALATION_CHANNEL else "#leads"
            
            # Create escalation message
            urgency_emoji = {
                "high": "🚨",
                "medium": "⚠️", 
                "low": "ℹ️"
            }.get(urgency, "⚠️")
            
            message_text = f"{urgency_emoji} *Blocker Reported*\n\n"
            message_text += f"*User:* @{user_name}\n"
            message_text += f"*KR:* {kr_name}\n"
            message_text += f"*Description:* {blocker_description}\n"
            message_text += f"*Urgency:* {urgency.title()}"
            
            if notes:
                message_text += f"\n*Notes:* {notes}"
            if sprint_number:
                message_text += f"\n*Sprint:* {sprint_number}"
            
            message_text += f"\n\n*Anyone can claim and help resolve this!*"
            
            # Create message blocks
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message_text
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Claim"},
                            "action_id": "claim_blocker",
                            "value": f"claim_{user_id}_{kr_name}",
                            "style": "primary"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "📋 View Details"},
                            "action_id": "view_details",
                            "value": f"view_details_{user_id}_{kr_name}"
                        }
                    ]
                }
            ]
            
            # Send to escalation channel
            self.client.chat_postMessage(
                channel=escalation_channel,
                text=f"Blocker reported by {user_name}",
                blocks=blocks
            )
            
            print(f"✅ Blocker escalated to {escalation_channel} for {user_name}")
            
        except Exception as e:
            print(f"❌ Error escalating blocker: {e}")
    
    def track_blocker_for_followup(self, user_id: str, kr_name: str):
        """Track a blocker for 24-hour follow-up."""
        try:
            # Generate unique blocker ID
            blocker_id = hashlib.md5(f"{user_id}_{kr_name}_{int(time.time())}".encode()).hexdigest()
            
            # Track this blocker
            self.active_blockers[user_id] = {
                'kr_name': kr_name,
                'blocker_id': blocker_id,
                'created_at': datetime.now()
            }
            
            print(f"✅ Blocker tracked for follow-up: {user_id} - {kr_name}")
            
        except Exception as e:
            print(f"❌ Error tracking blocker for followup: {e}")
    
    def send_dm(self, user_id: str, message: str):
        """Send a direct message to a user."""
        try:
            self.client.chat_postMessage(
                channel=user_id,
                text=message
            )
        except Exception as e:
            print(f"❌ Error sending DM: {e}")
    
    def get_user_name(self, user_id: str) -> str:
        """Get a user's display name."""
        try:
            response = self.client.users_info(user_id=user_id)
            if response['ok']:
                user = response['user']
                return user.get('real_name') or user.get('name', 'Unknown')
            return 'Unknown'
        except Exception as e:
            print(f"❌ Error getting user name: {e}")
            return 'Unknown'
    
    def update_message(self, channel_id: str, message_ts: str, new_text: str):
        """Update an existing message."""
        try:
            self.client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=new_text
            )
        except Exception as e:
            print(f"❌ Error updating message: {e}")
    
    def send_completion_message_to_accessible_channel(self, message: str):
        """Send completion message to an accessible channel."""
        try:
            # Try escalation channel first
            escalation_channel = f"#{self.config.SLACK_ESCALATION_CHANNEL}" if self.config.SLACK_ESCALATION_CHANNEL else "#leads"
            
            self.client.chat_postMessage(
                channel=escalation_channel,
                text=message
            )
            
        except Exception as e:
            print(f"❌ Error sending completion message to channel: {e}")
    
    def clear_pending_data(self, user_id: str, data_type: str):
        """Clear pending data for a user."""
        try:
            if data_type == 'kr':
                if user_id in self.kr_pending_data:
                    del self.kr_pending_data[user_id]
            elif data_type == 'blocker':
                if user_id in self.blocker_pending_data:
                    del self.blocker_pending_data[user_id]
        except Exception as e:
            print(f"⚠️ Error clearing pending data: {e}")
    
    def has_role(self, user_id: str, role: str) -> bool:
        """Check if a user has a specific role."""
        # This is a placeholder - implement actual role checking logic
        return True  # For now, allow everyone to have all roles