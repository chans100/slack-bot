import time
from datetime import datetime
from slack_sdk.errors import SlackApiError


class BlockerManager:
    """Manages blocker functionality including escalation, tracking, and resolution."""
    
    def __init__(self, bot):
        self.bot = bot
        self.BLOCKER_FOLLOWUP_DELAY_HOURS = 24
    
    def send_help_followup(self, user_id, standup_ts, user_name, channel=None):
        """Send enhanced blocker follow-up with structured questions."""
        try:
            message = {
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
                            "text": "What's blocking you?"
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
                            "text": "Key Result (KR) Name"
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
                            "text": "Urgency Level"
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
                            "text": "Additional Notes (Optional)"
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
            }
            
            response = self.bot.client.chat_postMessage(
                channel=channel or self.bot.channel_id,
                thread_ts=standup_ts,
                blocks=message["blocks"],
                text=f"<@{user_id}>, I see you need help! Please fill out the blocker details above."
            )
            
            print(f"Enhanced blocker follow-up sent to {user_name} ({user_id})")
            return response['ts']
            
        except SlackApiError as e:
            print(f"Error sending enhanced blocker follow-up: {e.response['error']}")
            return None
    
    def handle_blocker_form_submission(self, payload):
        """Handle blocker form submission from modal."""
        try:
            print("🔍 DEBUG: Received blocker form submission")
            print(f"🔍 DEBUG: Payload keys: {list(payload.keys())}")
            
            # Extract form data from the payload
            state = payload.get('view', {}).get('state', {})
            values = state.get('values', {})
            
            print(f"🔍 DEBUG: State keys: {list(state.keys())}")
            print(f"🔍 DEBUG: Values keys: {list(values.keys())}")
            
            # Get blocker details from form
            blocker_description = values.get('blocker_description', {}).get('blocker_description_input', {}).get('value', '')
            kr_name = values.get('kr_name', {}).get('kr_name_input', {}).get('value', '')
            urgency = values.get('urgency', {}).get('urgency_input', {}).get('selected_option', {}).get('value', '')
            notes = values.get('notes', {}).get('notes_input', {}).get('value', '')
            
            print(f"🔍 DEBUG: Extracted values:")
            print(f"   Blocker Description: {blocker_description}")
            print(f"   KR Name: {kr_name}")
            print(f"   Urgency: {urgency}")
            print(f"   Notes: {notes}")
            
            # Get user info
            user = payload.get('user', {}).get('id', 'unknown')
            username = payload.get('user', {}).get('name', 'unknown')
            
            print(f"🔍 DEBUG: User: {user} ({username})")
            
            # Store in Coda (primary) and MongoDB (fallback)
            success = False
            
            # Try Coda first
            if self.bot.coda and self.bot.coda.blocker_table_id:
                try:
                    print("🔍 DEBUG: Attempting to store in Coda...")
                    success = self.bot.coda.add_blocker(
                        user_id=user,
                        blocker_description=blocker_description,
                        kr_name=kr_name,
                        urgency=urgency,
                        notes=notes,
                        username=username
                    )
                    if success:
                        print(f"✅ Blocker details stored in Coda for {username}")
                    else:
                        print("❌ Coda storage failed")
                except Exception as e:
                    print(f"❌ Error storing blocker in Coda: {e}")
            
            # Send confirmation and escalate
            if success:
                print("🔍 DEBUG: Storage successful, escalating...")
                # Escalate with detailed information
                self.escalate_blocker_with_details(user, username, blocker_description, kr_name, urgency, notes)
            else:
                print("❌ DEBUG: Storage failed in Coda")
            
            return {"response_action": "clear"}, 200
            
        except Exception as e:
            print(f"❌ Error in handle_blocker_form_submission: {e}")
            return {"response_action": "clear"}, 200
    
    def escalate_blocker_with_details(self, user_id, user_name, blocker_description, kr_name, urgency, notes):
        """Escalate blocker with detailed information to leads channel with claim functionality."""
        try:
            import time
            
            # Format urgency with emoji
            urgency_emoji = {
                'Low': '🟢',
                'Medium': '🟡', 
                'High': '🟠',
                'Critical': '🔴'
            }.get(urgency, '⚪')
            
            # Get current KR status from Coda
            kr_status_info = "Unknown"
            print(f"🔍 DEBUG: Attempting to fetch KR status for '{kr_name}'")
            if self.bot.coda and kr_name and kr_name != "Unknown KR":
                try:
                    print(f"🔍 DEBUG: Coda service available, calling get_kr_details for '{kr_name}'")
                    kr_details = self.bot.coda.get_kr_details(kr_name)
                    print(f"🔍 DEBUG: get_kr_details returned: {kr_details}")
                    if kr_details:
                        current_status = kr_details.get('status', 'Unknown')
                        current_helper = kr_details.get('helper', '')
                        print(f"🔍 DEBUG: Current status: '{current_status}', helper: '{current_helper}'")
                        if current_status and current_status != 'Unknown':
                            if current_helper:
                                kr_status_info = f"{current_status} (by {current_helper})"
                            else:
                                kr_status_info = current_status
                        else:
                            kr_status_info = "In Progress"
                        print(f"🔍 DEBUG: Final kr_status_info: '{kr_status_info}'")
                    else:
                        kr_status_info = "Not Found in KR Table"
                        print(f"⚠️ KR '{kr_name}' not found in Coda table - may be a placeholder or incorrect name")
                except Exception as kr_error:
                    print(f"❌ Error fetching KR status: {kr_error}")
                    kr_status_info = "Error fetching status"
            else:
                print(f"🔍 DEBUG: Skipping KR status fetch - Coda: {self.bot.coda is not None}, kr_name: '{kr_name}'")
            
            # Create unique blocker ID for tracking
            blocker_id = f"blocker_{user_id}_{int(time.time())}"
            
            # Create escalation message with claim functionality
            escalation_message = f"🚨 *BLOCKER ESCALATION - {urgency_emoji} {urgency} Priority*\n\n"
            escalation_message += f"<@{user_id}> ({user_name}) is blocked and needs assistance!\n\n"
            escalation_message += f"*Blocker Details:*\n"
            escalation_message += f"• **Description:** {blocker_description}\n"
            escalation_message += f"• **KR:** {kr_name}\n"
            escalation_message += f"• **Urgency:** {urgency_emoji} {urgency}\n"
            escalation_message += f"• **Notes:** {notes if notes else 'None'}\n"
            escalation_message += f"• **Current KR Status:** {kr_status_info}\n\n"
            escalation_message += f"*Status:* ⏳ Unclaimed - Available for leads to claim"
            
            # Create message blocks with claim buttons
            message_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                        "text": escalation_message
                        }
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
                            "value": f"view_{blocker_id}",
                            "action_id": "view_blocker_details"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Mark Resolved",
                                "emoji": True
                            },
                            "value": f"resolve_{blocker_id}",
                            "action_id": "mark_resolved",
                            "style": "primary"
                        }
                    ]
                }
            ]
            
            # Send to leads channel (or general if no leads channel)
            leads_channel = getattr(self.bot.config, 'SLACK_LEADS_CHANNEL', 'leads')
            try:
                response = self.bot.client.chat_postMessage(
                    channel=f"#{leads_channel}",
                    blocks=message_blocks,
                    text=f"🚨 Blocker Alert: {user_name} needs help with {kr_name}"
                )
                print(f"✅ Blocker escalation sent to #{leads_channel} for {user_name}")
            except Exception as e:
                print(f"❌ Error sending to leads channel, falling back to general: {e}")
                # Fallback to general channel
                response = self.bot.client.chat_postMessage(
                    channel="#general",
                    blocks=message_blocks,
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
                'kr_status_info': kr_status_info,
                'escalation_ts': response['ts'],
                'channel': leads_channel,
                'channel_id': response.get('channel'),
                'message_ts': response['ts'],
                'status': 'unclaimed',
                'claimed_by': None,
                'claimed_at': None,
                'progress_updates': []
            }
            if not hasattr(self.bot, 'active_blockers'):
                self.bot.active_blockers = {}
            self.bot.active_blockers[blocker_id] = blocker_info
            # Pass channel_id and message_ts to tracking
            self.track_blocker_for_followup(
                user_id=user_id,
                user_name=user_name,
                blocker_description=blocker_description,
                kr_name=kr_name,
                urgency=urgency,
                notes=notes,
                escalation_ts=response['ts'],
                channel_id=response.get('channel'),
                message_ts=response['ts']
            )
            
            return response['ts']
            
        except SlackApiError as e:
            print(f"❌ Error escalating blocker with details: {e.response['error']}")
            print(f"🔍 DEBUG: Error details: {e.response}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error in escalate_blocker_with_details: {e}")
            return None
    
    def track_blocker_for_followup(self, user_id, user_name, blocker_description, kr_name, urgency, notes, escalation_ts, channel_id=None, message_ts=None):
        """Track blocker for follow-up reminders."""
        try:
            # Create unique key for this blocker
            blocker_key = f"{user_id}_{kr_name}_{blocker_description[:30]}"
            
            # Store blocker info for follow-up
            if not hasattr(self.bot, 'tracked_blockers'):
                self.bot.tracked_blockers = {}
            
            self.bot.tracked_blockers[blocker_key] = {
                'user_id': user_id,
                'user_name': user_name,
                'blocker_description': blocker_description,
                'kr_name': kr_name,
                'urgency': urgency,
                'notes': notes,
                'escalation_ts': escalation_ts,
                'channel_id': channel_id,
                'message_ts': message_ts,
                'escalation_time': datetime.now(),
                'resolved': False,
                'followup_sent': False
            }
            
            print(f"✅ Blocker tracked for follow-up: {blocker_key}")
            
        except Exception as e:
            print(f"❌ Error tracking blocker for follow-up: {e}")
    
    def check_blocker_followups(self):
        """Check for blockers that need follow-up reminders."""
        try:
            if not hasattr(self.bot, 'tracked_blockers'):
                return
            
            current_time = datetime.now()
            
            for blocker_key, blocker_info in self.bot.tracked_blockers.items():
                # Skip if already resolved or followup already sent
                if blocker_info.get('resolved', False) or blocker_info.get('followup_sent', False):
                    continue
                
                # Check if enough time has passed for follow-up
                escalation_time = blocker_info.get('escalation_time')
                if escalation_time:
                    time_since_escalation = current_time - escalation_time
                    hours_since_escalation = time_since_escalation.total_seconds() / 3600
                    
                    if hours_since_escalation >= self.BLOCKER_FOLLOWUP_DELAY_HOURS:
                        # Send follow-up reminder
                        self.send_blocker_followup(blocker_info)
                        blocker_info['followup_sent'] = True
                        print(f"✅ Follow-up sent for blocker: {blocker_key}")
            
        except Exception as e:
            print(f"❌ Error checking blocker followups: {e}")
    
    def send_blocker_followup(self, blocker_info):
        """Send follow-up reminder for a blocker."""
        try:
            user_id = blocker_info['user_id']
            user_name = blocker_info['user_name']
            kr_name = blocker_info['kr_name']
            blocker_description = blocker_info['blocker_description']
            urgency = blocker_info['urgency']
            
            # Format urgency with emoji
            urgency_emoji = {
                'Low': '🟢',
                'Medium': '🟡', 
                'High': '🟠',
                'Critical': '🔴'
            }.get(urgency, '⚪')
            
            followup_message = f"⏰ *Blocker Follow-up Reminder*\n\n"
            followup_message += f"<@{user_id}>, it's been {self.BLOCKER_FOLLOWUP_DELAY_HOURS} hours since you reported a blocker.\n\n"
            followup_message += f"*Blocker Details:*\n"
            followup_message += f"• **Description:** {blocker_description}\n"
            followup_message += f"• **KR:** {kr_name}\n"
            followup_message += f"• **Urgency:** {urgency_emoji} {urgency}\n\n"
            followup_message += f"**Questions:**\n"
            followup_message += f"• Has this blocker been resolved?\n"
            followup_message += f"• Do you need additional help?\n"
            followup_message += f"• Has anyone reached out to assist you?\n\n"
            followup_message += f"Please update us on the status of this blocker!"
            
            # Send to the original channel or DM
            channel_id = blocker_info.get('channel_id') or self.bot.channel_id
            
            try:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text=followup_message
                )
                print(f"✅ Blocker follow-up sent to {user_name}")
            except Exception as e:
                print(f"❌ Error sending blocker follow-up: {e}")
                
        except Exception as e:
            print(f"❌ Error in send_blocker_followup: {e}")
    
    def handle_resolution_modal_submission(self, payload):
        """Handle resolution modal submission."""
        try:
            print("🔍 DEBUG: Received resolution modal submission")
            print(f"🔍 DEBUG: Payload keys: {list(payload.keys())}")
            
            # Extract form data from the payload
            state = payload.get('view', {}).get('state', {})
            values = state.get('values', {})
            
            print(f"🔍 DEBUG: State keys: {list(state.keys())}")
            print(f"🔍 DEBUG: Values keys: {list(values.keys())}")
            
            # Get resolution details from form
            resolution_notes = values.get('resolution_notes', {}).get('resolution_notes_input', {}).get('value', '')
            hidden_data = values.get('hidden_data', {}).get('hidden_data_input', {}).get('value', '')
            
            print(f"🔍 DEBUG: Extracted values:")
            print(f"   Resolution Notes: {resolution_notes}")
            print(f"   Hidden Data: {hidden_data}")
            
            # Parse hidden data
            # Format: "blocker_id" or "dm_user_id_kr_name_description"
            blocker_id = hidden_data.strip()
            if not blocker_id:
                print(f"❌ Invalid hidden data format: {hidden_data}")
                return {"response_action": "clear"}, 200
            
            # Get blocker info from active_blockers, tracked_blockers, or DM format
            blocker_info = None
            blocked_user_id = None
            kr_name = None
            blocker_description = None
            channel_id = None
            message_ts = None
            
            # Check if this is a DM format blocker
            if blocker_id.startswith('dm_'):
                # DM format: "dm_user_id_kr_name_description"
                parts = blocker_id.split('_', 3)
                if len(parts) >= 4:
                    blocked_user_id = parts[1]
                    kr_name = parts[2]
                    blocker_description = parts[3]
                    
                    # Create minimal blocker_info for DM blockers
                    blocker_info = {
                        'user_id': blocked_user_id,
                        'user_name': 'Unknown',  # Will be looked up if needed
                        'kr_name': kr_name,
                        'blocker_description': blocker_description,
                        'urgency': 'Unknown',
                        'notes': '',
                        'source': 'dm_resolution'
                    }
                    print(f"✅ Parsed DM format blocker: {blocker_id}")
                    print(f"   - User ID: {blocked_user_id}")
                    print(f"   - KR Name: {kr_name}")
                    print(f"   - Description: {blocker_description}")
                else:
                    print(f"❌ Invalid DM format: {blocker_id}")
                    return {"response_action": "clear"}, 200
            else:
                # Regular format - try to find in active_blockers
                if hasattr(self.bot, 'active_blockers') and blocker_id in self.bot.active_blockers:
                    blocker_info = self.bot.active_blockers[blocker_id]
                    blocked_user_id = blocker_info['user_id']
                    kr_name = blocker_info['kr_name']
                    blocker_description = blocker_info['blocker_description']
                    channel_id = blocker_info.get('channel_id')
                    message_ts = blocker_info.get('message_ts')
                    print(f"✅ Found blocker in active_blockers: {blocker_id}")
                # If not found in active_blockers, try to find in tracked_blockers
                elif hasattr(self.bot, 'tracked_blockers'):
                    for tracked_id, tracked_info in self.bot.tracked_blockers.items():
                        if tracked_id == blocker_id:
                            blocker_info = tracked_info
                            blocked_user_id = tracked_info['user_id']
                            kr_name = tracked_info['kr_name']
                            blocker_description = tracked_info['blocker_description']
                            channel_id = tracked_info.get('channel_id')
                            message_ts = tracked_info.get('escalation_ts')
                            print(f"✅ Found blocker in tracked_blockers: {blocker_id}")
                            print(f"🔍 DEBUG: Tracked blocker info keys: {list(tracked_info.keys())}")
                            print(f"🔍 DEBUG: Tracked blocker info: {tracked_info}")
                            break
            
            if not blocker_info:
                print(f"❌ Blocker {blocker_id} not found in active_blockers or tracked_blockers")
                print(f"❌ Fallback: Could not find blocker info for deletion or Coda update.")
                return {"response_action": "clear"}, 200
            
            print(f"🔍 DEBUG: Parsed hidden data:")
            print(f"   Blocked User ID: {blocked_user_id}")
            print(f"   KR Name: {kr_name}")
            print(f"   Blocker Description: {blocker_description}")
            
            # Get user info (the person resolving)
            user = payload.get('user', {}).get('id', 'unknown')
            username = payload.get('user', {}).get('name', 'unknown')
            
            print(f"🔍 DEBUG: Resolver: {user} ({username})")
            
            # Log the blocker resolution to Coda (optional - don't fail if Coda is down)
            success = True  # Start with success, only fail if critical errors occur
            if self.bot.coda:
                try:
                    # Log resolution to Blocker Resolution table
                    coda_success = self.bot.coda.resolve_blocker(
                        user_id=blocked_user_id,
                        kr_name=kr_name,
                        blocker_description=blocker_description,
                        resolved_by=username,
                        resolution_notes=resolution_notes,
                        slack_client=self.bot.client,
                        user_name=blocker_info.get('user_name', blocked_user_id)
                    )
                    if coda_success:
                        print(f"✅ Blocker resolution logged in Coda by {username}")
                    else:
                        print("⚠️ Failed to log blocker resolution in Coda, but continuing...")
                        
                except Exception as e:
                    print(f"⚠️ Error logging blocker resolution in Coda: {e}")
                    print("⚠️ Continuing with resolution process...")
                    import traceback
                    traceback.print_exc()
            else:
                print("⚠️ Coda not available, skipping Coda logging")
            
            # Mark as resolved in tracked blockers (if exists)
            if hasattr(self.bot, 'tracked_blockers'):
                for blocker_id, blocker_info in self.bot.tracked_blockers.items():
                    if (blocker_info['user_id'] == blocked_user_id and 
                        blocker_info['kr_name'] == kr_name and
                        blocker_info['blocker_description'] == blocker_description):
                        blocker_info['resolved'] = True
                        blocker_info['resolution_time'] = datetime.now()
                        blocker_info['resolved_by'] = username
                        blocker_info['resolution_notes'] = resolution_notes
                        print(f"✅ Blocker marked as resolved in tracked blockers: {blocker_id}")
                        break
            
            # Mark as resolved in active blockers (new system)
            if hasattr(self.bot, 'active_blockers'):
                resolved_blocker_id = blocker_id
                resolved_blocker_info = None
                if blocker_id in self.bot.active_blockers:
                    # Mark as resolved
                    self.bot.active_blockers[blocker_id]['resolved'] = True
                    self.bot.active_blockers[blocker_id]['resolved_by'] = username
                    self.bot.active_blockers[blocker_id]['resolved_at'] = time.time()
                    self.bot.active_blockers[blocker_id]['resolution_notes'] = resolution_notes
                    resolved_blocker_info = self.bot.active_blockers[blocker_id]
                    print(f"✅ Blocker marked as resolved in active blockers: {blocker_id}")
                else:
                    print(f"❌ Blocker {blocker_id} not found in active blockers")
            
            # Send confirmation messages
            if success:
                # Send confirmation to resolver only (remove duplicate to blocked user)
                try:
                    self.bot.client.chat_postMessage(
                        channel=user,
                        text=f"🎉 Successfully marked blocker as resolved!\n\n**KR:** {kr_name}\n**Description:** {blocker_description}\n**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                    )
                    print(f"✅ Confirmation sent to resolver {username}")
                except Exception as e:
                    print(f"❌ Error sending confirmation to resolver: {e}")
                
                # Delete the blocker message from the channel and update details
                print(f"🔍 DEBUG: Attempting to delete blocker message")
                print(f"🔍 DEBUG: Channel ID: {channel_id}")
                print(f"🔍 DEBUG: Message TS: {message_ts}")
                
                # If we don't have channel_id, try to get it from config and search for the original message
                if not channel_id:
                    # Get accessible channels first
                    accessible_channels = self.bot.get_accessible_channels()
                    if not accessible_channels:
                        print("❌ No accessible channels found for message deletion")
                        accessible_channels = ['general']  # Fallback
                    
                    original_message_deleted = False
                    for channel_name in accessible_channels:
                        print(f"🔍 DEBUG: Trying accessible channel: #{channel_name}")
                        try:
                            # Try to find and delete the original blocker escalation message
                            original_message_deleted = self._find_and_delete_original_blocker_message(
                                channel_name, blocked_user_id, kr_name, blocker_description, username
                            )
                            if original_message_deleted:
                                leads_channel = channel_name
                                print(f"✅ Successfully deleted original message from #{channel_name}")
                                break
                        except Exception as e:
                            print(f"❌ Error trying to delete from #{channel_name}: {e}")
                            continue
                    
                    if original_message_deleted:
                        # Send completion message to leads channel after successful deletion
                        completion_message = f"✅ *Blocker Resolved*\n\n"
                        completion_message += f"**KR:** {kr_name}\n"
                        completion_message += f"**Description:** {blocker_description}\n"
                        completion_message += f"**Resolved by:** {username}\n"
                        completion_message += f"**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                        
                        try:
                            self.bot.client.chat_postMessage(
                                channel=f"#{leads_channel}",
                                text=completion_message
                            )
                            print(f"✅ Sent completion summary to leads channel #{leads_channel}")
                        except Exception as e:
                            print(f"❌ Error sending completion message: {e}")
                    else:
                        print(f"⚠️ Could not find original blocker message to delete")
                        # Try to send completion message to an accessible channel
                        completion_message = f"✅ *Blocker Resolved*\n\n"
                        completion_message += f"**KR:** {kr_name}\n"
                        completion_message += f"**Description:** {blocker_description}\n"
                        completion_message += f"**Resolved by:** {username}\n"
                        completion_message += f"**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                        
                        message_sent = self.bot.send_completion_message_to_accessible_channel(completion_message)
                        
                        if not message_sent:
                            print(f"❌ Could not send completion message to any accessible channel")
                        
                        # Log missing channel/message timestamps for debugging
                        if not channel_id or not message_ts:
                            print(f"❌ Missing channel_id or message_ts for deletion")
                            print(f"❌ channel_id: {channel_id}, message_ts: {message_ts}")
                        
                        return {"response_action": "clear"}, 200
                
                if channel_id and message_ts:
                    try:
                        # Delete the original blocker message
                        self.bot.client.chat_delete(channel=channel_id, ts=message_ts)
                        print(f"✅ Deleted blocker message from channel {channel_id}")
                        
                        # Send a completion summary to the channel
                        completion_message = f"✅ *Blocker Resolved*\n\n"
                        completion_message += f"**KR:** {kr_name}\n"
                        completion_message += f"**Description:** {blocker_description}\n"
                        completion_message += f"**Resolved by:** {username}\n"
                        completion_message += f"**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                        
                        self.bot.client.chat_postMessage(
                            channel=channel_id,
                            text=completion_message
                        )
                        print(f"✅ Sent completion summary to channel {channel_id}")
                        
                    except Exception as e:
                        print(f"❌ Error deleting blocker message or sending completion summary: {e}")
                        import traceback
                        traceback.print_exc()
                        
                        # Fallback: try to update the message instead of deleting it
                        try:
                            completion_message = f"✅ *Blocker Resolved*\n\n"
                            completion_message += f"**KR:** {kr_name}\n"
                            completion_message += f"**Description:** {blocker_description}\n"
                            completion_message += f"**Resolved by:** {username}\n"
                            completion_message += f"**Resolution Notes:** {resolution_notes if resolution_notes else 'None provided'}"
                            
                            self.bot.client.chat_update(
                                channel=channel_id,
                                ts=message_ts,
                                text=completion_message
                            )
                            print(f"✅ Updated blocker message in channel {channel_id} with resolution")
                        except Exception as update_error:
                            print(f"❌ Error updating blocker message: {update_error}")
                else:
                    print(f"❌ Missing channel_id or message_ts for deletion")
                    print(f"❌ channel_id: {channel_id}, message_ts: {message_ts}")
                
                # Remove from active blockers if it exists there
                if hasattr(self.bot, 'active_blockers') and blocker_id in self.bot.active_blockers:
                    del self.bot.active_blockers[blocker_id]
                    print(f"✅ Removed resolved blocker {blocker_id} from active blockers")
                
                # Delete the original unresolved blocker message if tracked
                if hasattr(self.bot, 'tracked_blockers'):
                    for blocker_id, blocker_info in self.bot.tracked_blockers.items():
                        if (
                            blocker_info['user_id'] == blocked_user_id and
                            blocker_info['kr_name'] == kr_name and
                            blocker_info['blocker_description'] == blocker_description
                        ):
                            # Try to delete the reminder/escalation message
                            channel_id = blocker_info.get('channel_id')
                            message_ts = blocker_info.get('escalation_ts')
                            if channel_id and message_ts:
                                try:
                                    self.bot.client.chat_delete(channel=channel_id, ts=message_ts)
                                    print(f"✅ Deleted unresolved blocker message in channel {channel_id} at ts {message_ts}")
                                except Exception as e:
                                    print(f"❌ Error deleting unresolved blocker message: {e}")
                            break
                
                # Delete unresolved reminder messages
                if hasattr(self.bot, 'unresolved_reminder_messages'):
                    # Try multiple key formats for reminder messages
                    reminder_keys_to_try = [
                        f"{blocked_user_id}_{kr_name}_{blocker_description[:30]}",
                        f"{blocked_user_id}_{kr_name}_{blocker_description}",
                        f"{blocked_user_id}_{kr_name}_From Coda check"
                    ]
                    
                    reminder_deleted = False
                    for reminder_key in reminder_keys_to_try:
                        if reminder_key in self.bot.unresolved_reminder_messages:
                            reminder_info = self.bot.unresolved_reminder_messages[reminder_key]
                            try:
                                self.bot.client.chat_delete(
                                    channel=reminder_info['channel_id'], 
                                    ts=reminder_info['message_ts']
                                )
                                print(f"✅ Deleted unresolved reminder message for {reminder_key}")
                                # Remove from tracking
                                del self.bot.unresolved_reminder_messages[reminder_key]
                                reminder_deleted = True
                                break
                            except Exception as e:
                                print(f"❌ Error deleting unresolved reminder message: {e}")
                    
                    if not reminder_deleted:
                        print(f"⚠️ No tracked reminder message found for any key: {reminder_keys_to_try}")
            else:
                # Send error message
                self.bot.client.chat_postMessage(
                    channel=user,
                    text=f"❌ Sorry, there was an error marking the blocker as resolved. Please try again or contact the team."
                )
            
            # Always return a successful response to close the modal
            print("✅ Resolution modal submission completed successfully")
            return {"response_action": "clear"}, 200
        except Exception as e:
            print(f"❌ Error in handle_resolution_modal_submission: {e}")
            import traceback
            traceback.print_exc()
            return {"response_action": "clear"}, 200
    
    def _find_and_delete_original_blocker_message(self, channel_name, user_id, kr_name, blocker_description, resolver_name=None):
        """Find and delete the original blocker escalation message from the channel."""
        try:
            print(f"🔍 DEBUG: Searching for original blocker message in #{channel_name}")
            print(f"🔍 DEBUG: Looking for user: {user_id}, KR: {kr_name}, Description: {blocker_description}")
            
            # First, validate that the channel exists and we have access
            try:
                # Try to get channel info to validate access
                channel_info = self.bot.client.conversations_info(channel=f"#{channel_name}")
                if not channel_info['ok']:
                    print(f"❌ Channel #{channel_name} not found or no access: {channel_info.get('error', 'Unknown error')}")
                    return False
                print(f"✅ Channel #{channel_name} validated")
            except Exception as e:
                print(f"❌ Error validating channel #{channel_name}: {e}")
                return False
            
            # Get recent messages from the channel
            try:
                response = self.bot.client.conversations_history(
                    channel=f"#{channel_name}",
                    limit=50  # Get last 50 messages
                )
                
                if not response['ok']:
                    print(f"❌ Failed to get channel history: {response.get('error', 'Unknown error')}")
                    return False
                
                messages = response.get('messages', [])
                print(f"🔍 DEBUG: Found {len(messages)} messages in channel")
                
                # Look for the blocker escalation message
                for message in messages:
                    # Skip bot messages that aren't blocker escalations
                    if message.get('user') != 'U0912DJRNSF':  # Bot user ID
                        continue
                    
                    # Check if this is a blocker escalation message
                    text = message.get('text', '')
                    if 'BLOCKER ESCALATION' in text and 'is blocked and needs assistance' in text:
                        # Check if this message matches our blocker
                        if (user_id in text and 
                            kr_name in text and 
                            blocker_description in text):
                            
                            print(f"✅ Found matching blocker escalation message")
                            print(f"🔍 DEBUG: Message TS: {message.get('ts')}")
                            
                            # Delete the message
                            try:
                                delete_response = self.bot.client.chat_delete(
                                    channel=f"#{channel_name}",
                                    ts=message.get('ts')
                                )
                                if delete_response['ok']:
                                    print(f"✅ Deleted original blocker escalation message from #{channel_name}")
                                    return True
                                else:
                                    print(f"❌ Failed to delete message: {delete_response.get('error', 'Unknown error')}")
                                    return False
                                
                            except Exception as e:
                                print(f"❌ Error deleting message: {e}")
                                return False
                
                print(f"⚠️ No matching blocker escalation message found")
                return False
                
            except Exception as e:
                print(f"❌ Error accessing channel history: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Error in _find_and_delete_original_blocker_message: {e}")
            return False 