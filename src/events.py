import json
import time
from flask import jsonify, request
from .utils import logger, error_handler, input_validator, safe_executor

# Global submission tracking to prevent duplicates
_submission_tracker = {}

def track_submission(user_id, submission_type, data_hash=None):
    """Track a submission to prevent duplicates."""
    global _submission_tracker
    current_time = time.time()
    
    # Create a unique key for this submission
    if data_hash:
        submission_key = f"{user_id}_{submission_type}_{data_hash}"
    else:
        submission_key = f"{user_id}_{submission_type}_{int(current_time)}"
    
    # Clean up old submissions (older than 30 seconds)
    _submission_tracker = {k: v for k, v in _submission_tracker.items() if current_time - v < 30}
    
    # Check if this is a recent duplicate
    if submission_key in _submission_tracker:
        print(f"🔍 DEBUG: Duplicate submission detected: {submission_key}")
        return False
    
    # Track this submission
    _submission_tracker[submission_key] = current_time
    print(f"🔍 DEBUG: Tracking submission: {submission_key}")
    return True

def log_payload_for_debugging(payload):
    """Log payload structure for debugging."""
    try:
        print("🔍 DEBUG: Received payload:")
        print(f"   Type: {payload.get('type', 'N/A')}")
        print(f"   Keys: {list(payload.keys())}")
        
        if 'user' in payload:
            print(f"   User: {payload['user']}")
        
        if 'actions' in payload:
            print(f"   Actions: {payload['actions']}")
        
        if 'channel' in payload:
            print(f"   Channel: {payload['channel']}")
        
        if 'message' in payload:
            print(f"   Message keys: {list(payload['message'].keys())}")
            
    except Exception as e:
        print(f"❌ Error logging payload: {e}")

def generate_kr_explanation(kr_name, owner, status, definition_of_done=None):
    """Generate a contextual explanation for a KR based on its details."""
    try:
        explanation = f"This KR is currently {status.lower()}"
        
        if owner and owner != 'N/A':
            explanation += f" and is owned by {owner}"
        
        if definition_of_done and definition_of_done.strip():
            explanation += f". The definition of done includes: {definition_of_done}"
        
        explanation += "."
        
        return explanation
    except Exception as e:
        print(f"Error generating KR explanation: {e}")
        return "Unable to generate explanation at this time."

def handle_blocker_note_edit(bot, payload):
    """Handle blocker note edit button click."""
    try:
        print(f"🔍 DEBUG: handle_blocker_note_edit called with payload: {payload}")
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        blocker_id = payload['actions'][0]['value']
        
        print(f"🔍 DEBUG: Processing blocker note edit - User: {user_name}, Blocker ID: {blocker_id}")
        
        # Check if trigger_id exists (button clicks don't have trigger_id)
        trigger_id = payload.get('trigger_id')
        if not trigger_id:
            print(f"❌ DEBUG: No trigger_id found in payload - cannot open modal")
            # Send a message to the user instead
            bot.send_dm(user_id, "❌ Sorry, I can't open the note editor right now. Please try again later.")
            return jsonify({"response_action": "clear"})
        
        # Create modal for editing note
        blocks = [
            {
                "type": "input",
                "block_id": "note_input",
                "label": {"type": "plain_text", "text": "Add or edit note for this blocker:"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "note_text",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Enter your note..."}
                }
            }
        ]
        
        # Store blocker_id for modal submission
        if not hasattr(bot, 'tracked_blockers'):
            bot.tracked_blockers = {}
        bot.tracked_blockers[user_id] = blocker_id
        
        print(f"🔍 DEBUG: Stored blocker_id {blocker_id} for user {user_id}")
        
        # Open modal
        modal_result = bot.open_modal(
            trigger_id=trigger_id,
            title="Edit Blocker Note",
            blocks=blocks,
            submit_text="Save Note",
            callback_id="blocker_note_submit"
        )
        
        if modal_result:
            print(f"✅ DEBUG: Modal opened successfully for blocker note edit")
        else:
            print(f"❌ DEBUG: Failed to open modal for blocker note edit")
        
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"❌ Error handling blocker note edit: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response_action": "clear"})

def handle_blocker_completion(bot, payload):
    """Handle blocker completion button click."""
    try:
        print(f"🔍 DEBUG: handle_blocker_completion called with payload: {payload}")
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        blocker_id = payload['actions'][0]['value']
        channel_id = payload['channel']['id']
        message_ts = payload['message']['ts']
        
        print(f"🔍 DEBUG: Processing blocker completion - User: {user_name}, Blocker ID: {blocker_id}, Channel: {channel_id}")
        
        # Call the bot's handle_blocker_completion method with resolver info
        bot.handle_blocker_completion(blocker_id, channel_id, message_ts, resolver_id=user_id, resolver_name=user_name)
        
        print(f"✅ DEBUG: handle_blocker_completion completed successfully")
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"❌ Error handling blocker completion: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response_action": "clear"})

def handle_complete_blocker_with_form(bot, payload):
    """Handle blocker completion with form modal."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        blocker_id = payload['actions'][0]['value']
        trigger_id = payload['trigger_id']
        
        print(f"🔍 DEBUG: Opening completion form for blocker: {blocker_id}")
        
        # Create completion form modal
        blocks = [
            {
                "type": "input",
                "block_id": "resolution_notes",
                "label": {"type": "plain_text", "text": "How was this blocker resolved?"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "resolution_notes_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Describe how the blocker was resolved, what steps were taken, etc..."}
                }
            }
        ]
        
        bot.open_modal(
            trigger_id=trigger_id,
            title="Complete Blocker",
            blocks=blocks,
            submit_text="Mark Complete",
            callback_id="blocker_completion_submit",
            private_metadata=blocker_id
        )
        
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"❌ Error opening blocker completion form: {e}")
        return jsonify({"response_action": "clear"})

def handle_mentor_response(bot, payload):
    """Handle mentor check responses."""
    try:
        print(f"🔍 DEBUG: handle_mentor_response called with payload: {payload}")
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        action_id = payload['actions'][0]['action_id']
        value = payload['actions'][0]['value']
        channel_id = payload['channel']['id']
        message_ts = payload['message']['ts']
        
        print(f"🔍 DEBUG: handle_mentor_response called - Action: {action_id}, Value: {value}")
        print(f"🔍 DEBUG: User: {user_name} ({user_id})")
        print(f"🔍 DEBUG: Channel: {channel_id}, Message TS: {message_ts}")
        
        # Parse value: mentor_yes/request_type/user_id or mentor_no/request_type/user_id
        parts = value.split('_')
        print(f"🔍 DEBUG: Parsed value parts: {parts}")
        
        if len(parts) >= 3:
            mentor_response = parts[1]  # yes or no
            request_type = parts[2]     # kr or blocker
            target_user_id = parts[3]   # user_id
            
            print(f"🔍 DEBUG: Mentor response: {mentor_response}, Request type: {request_type}, Target user: {target_user_id}")
            
            # Note: Mentor table has been removed as per user request
            
            if mentor_response == 'yes':
                if request_type == 'kr':
                    # User has reached out to mentor, proceed with KR request
                    search_term = bot.pending_kr_search.get(target_user_id)
                    if search_term:
                        # Show KR search results
                        if bot.coda:
                            matches = bot.coda.search_kr_table(search_term)
                            if matches:
                                # Deduplicate KRs by name to avoid showing the same KR multiple times
                                unique_krs = {}
                                for m in matches:
                                    kr_name = m.get('c-yQ1M6UqTSj', 'N/A')
                                    if kr_name not in unique_krs:
                                        unique_krs[kr_name] = m
                                
                                # Use deduplicated results
                                unique_matches = list(unique_krs.values())
                                print(f"🔍 DEBUG: Found {len(matches)} total matches, {len(unique_matches)} unique KRs")
                                
                                # Delete the original mentor check message first
                                print(f"🔍 DEBUG: Deleting mentor check message")
                                try:
                                    bot.update_message(
                                        channel_id=channel_id,
                                        ts=message_ts,
                                        text=f"✅ Found {len(unique_matches)} unique KRs for '{search_term}':"
                                    )
                                except Exception as e:
                                    print(f"❌ Error updating mentor check message: {e}")
                                
                                # Send each unique KR as a separate message
                                print(f"🔍 DEBUG: Sending {len(unique_matches)} unique KR results as separate messages")
                                for i, m in enumerate(unique_matches, 1):
                                    kr_name = m.get('c-yQ1M6UqTSj', 'N/A')
                                    owner = m.get('c-efR-vVo_3w', 'N/A')
                                    status = m.get('c-cC29Yow8Gr', 'N/A')
                                    definition_of_done = m.get('c-P_mQJLObL0', '')
                                    link = m.get('link', None)
                                    explanation = generate_kr_explanation(kr_name, owner, status, definition_of_done)
                                    
                                    # Create individual KR message
                                    kr_message = f"*KR {i}*: {kr_name}\n*Owner*: {owner}\n*Status*: {status}\n*Definition of Done*: {definition_of_done}\n*AI Explanation*: {explanation}"
                                    if link:
                                        kr_message += f"\n<Link|{link}>"
                                    
                                    # Send as separate message
                                    try:
                                        bot.send_dm(target_user_id, kr_message)
                                        print(f"🔍 DEBUG: Sent KR {i} message")
                                    except Exception as e:
                                        print(f"❌ Error sending KR {i} message: {e}")
                            else:
                                # No matches found
                                result_text = f'No matching KRs found for "{search_term}".'
                                print(f"🔍 DEBUG: No matches found, updating mentor check message")
                                bot.update_message(
                                    channel_id=channel_id,
                                    ts=message_ts,
                                    text=result_text
                                )
                        else:
                            # Delete the original mentor check message and replace with error
                            bot.update_message(
                                channel_id=channel_id,
                                ts=message_ts,
                                text=f"Great! Let me help you with your KR request: {search_term}"
                            )
                        
                        # Clear the pending search
                        bot.pending_kr_search.pop(target_user_id, None)
                    else:
                        # No search term provided, delete mentor check and replace with prompt
                        bot.update_message(
                            channel_id=channel_id,
                            ts=message_ts,
                            text="What KR would you like to search for? Please type `/kr [search term]` or `!kr [search term]`."
                        )
                elif request_type == 'blocker':
                    # User has reached out to mentor, proceed with blocker form
                    # Send a new message with the blocker button instead of updating
                    print(f"🔍 DEBUG: Sending new message with blocker button for blocker request")
                    
                    help_text = "🚨 *Great! Let me help you submit your blocker details.*\n\nI can help you submit a blocker report that will be escalated to your team leads.\n\nClick the button below to open the blocker report form."
                    
                    blocks = [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": help_text}
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Report Blocker"},
                                    "action_id": "open_blocker_report_modal",
                                    "value": f"blocker_report_{target_user_id}",
                                    "style": "primary"
                                }
                            ]
                        }
                    ]
                    
                    # Send a new message instead of updating
                    print(f"🔍 DEBUG: Sending DM with blocker button to user: {target_user_id}")
                    result = bot.send_dm(target_user_id, help_text, blocks=blocks)
                    print(f"🔍 DEBUG: send_dm result: {result}")
                    
                    # Also delete the original mentor check message
                    try:
                        print(f"🔍 DEBUG: Updating original mentor check message")
                        bot.update_message(
                            channel_id=channel_id,
                            ts=message_ts,
                            text="✅ Mentor check completed - see message above for blocker form."
                        )
                    except Exception as e:
                        print(f"❌ Error updating mentor check message: {e}")
                else:
                    print(f"❌ DEBUG: Unknown request type: {request_type}")
            elif mentor_response == 'no':
                # Handle "No" response
                print(f"🔍 DEBUG: Handling mentor 'no' response for {request_type}")
                if request_type == 'kr':
                    bot.update_message(
                        channel_id=channel_id,
                        ts=message_ts,
                        text="I understand! Please reach out to your mentor first, then try the `/kr` command again."
                    )
                elif request_type == 'blocker':
                    # For blockers, still send the blocker form even if they haven't talked to mentor
                    # This allows them to submit the blocker anyway
                    print(f"🔍 DEBUG: Sending blocker form despite mentor 'no' response")
                    
                    help_text = "🚨 *Let me help you submit your blocker details.*\n\nI can help you submit a blocker report that will be escalated to your team leads.\n\nClick the button below to open the blocker report form."
                    
                    blocks = [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": help_text}
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Report Blocker"},
                                    "action_id": "open_blocker_report_modal",
                                    "value": f"blocker_report_{target_user_id}",
                                    "style": "primary"
                                }
                            ]
                        }
                    ]
                    
                    # Send a new message with the blocker button
                    print(f"🔍 DEBUG: Sending DM with blocker button to user: {target_user_id}")
                    result = bot.send_dm(target_user_id, help_text, blocks=blocks)
                    print(f"🔍 DEBUG: send_dm result: {result}")
                    
                    # Update the original mentor check message
                    try:
                        print(f"🔍 DEBUG: Updating original mentor check message")
                        bot.update_message(
                            channel_id=channel_id,
                            ts=message_ts,
                            text="✅ Mentor check completed - see message above for blocker form."
                        )
                    except Exception as e:
                        print(f"❌ Error updating mentor check message: {e}")
            else:
                print(f"❌ DEBUG: Unknown mentor response: {mentor_response}")
        else:
            print(f"❌ DEBUG: Could not parse mentor response value: {value}")
        
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"❌ Error in handle_mentor_response: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response_action": "clear"})

def handle_blocker_followup_response(bot, payload):
    """Handle responses to 24-hour blocker follow-up."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        action_id = payload['actions'][0]['action_id']
        value = payload['actions'][0]['value']
        channel_id = payload['channel']['id']
        
        # Parse value: user_id_kr_name
        parts = value.split('_')
        if len(parts) >= 2:
            target_user_id = parts[0]
            kr_name = '_'.join(parts[1:])  # KR name might contain underscores
            
            if action_id == 'blocker_resolved':
                bot.send_dm(user_id, f"🎉 Great! The blocker for {kr_name} has been resolved!")
                # Update the original blocker message
                bot.update_message(channel_id, payload['message']['ts'], 
                                 f"✅ *Blocker for {kr_name} has been resolved by @{user_name}*")
                
            elif action_id == 'blocker_still_blocked':
                bot.send_dm(user_id, f"I understand you're still blocked on {kr_name}. Let me escalate this further.")
                # Escalate to next level
                bot.escalate_by_hierarchy('blocker', f"User @{user_name} is still blocked on {kr_name}")
                
            elif action_id == 'blocker_need_help':
                bot.send_dm(user_id, f"I'll help you get additional support for {kr_name}.")
                # Send enhanced help form
                bot.send_help_followup(user_id, payload['message']['ts'], user_name, channel_id)
        
        return jsonify({"text": "OK"})
    except Exception as e:
        print(f"Error handling blocker followup response: {e}")
        return jsonify({"text": "Error"})

def handle_claim_blocker(bot, payload):
    """Handle claiming a blocker by a lead."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        value = payload['actions'][0]['value']
        channel_id = payload['channel']['id']
        message_ts = payload['message']['ts']
        
        # Parse value: claim_blocker_id_user_id_user_name
        parts = value.split('_')
        if len(parts) >= 4:
            action_type = parts[0]  # claim
            blocker_id = parts[1]
            blocked_user_id = parts[2]
            user_name_part = parts[3]
            # Reconstruct user name if it contains underscores
            user_name_part = '_'.join(parts[3:])
            
            # Get blocker details from active_blockers if available
            blocker_info = None
            if hasattr(bot, 'active_blockers') and blocker_id in bot.active_blockers:
                blocker_info = bot.active_blockers[blocker_id]
                kr_name = blocker_info.get('kr_name', 'Unknown KR')
                blocker_description = blocker_info.get('blocker_description', 'Unknown blocker')
            else:
                # Fallback parsing
                kr_name = "Unknown KR"
                blocker_description = "Unknown blocker"
            
            # Check if user has lead role
            if not bot.has_role(user_id, 'lead') and not bot.has_role(user_id, 'pm'):
                bot.send_dm(user_id, "❌ Only leads and PMs can claim blockers.")
                return jsonify({"text": "Error"})
            
            # Update the message to show it's claimed
            updated_text = f"✅ *Blocker claimed by @{user_name}*\n\n"
            updated_text += f"*User:* <@{blocked_user_id}>\n"
            updated_text += f"*KR:* {kr_name}\n"
            updated_text += f"*Description:* {blocker_description}\n"
            updated_text += f"*Status:* Being addressed by @{user_name}"
            
            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": updated_text}
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "📋 View Details"},
                            "action_id": "view_details",
                            "value": f"view_details_{blocker_id}_{kr_name}"
                        }
                    ]
                }
            ]
            
            bot.update_message(channel_id, message_ts, "", blocks=blocks)
            
            # Update active_blockers tracking
            if hasattr(bot, 'active_blockers') and blocker_id in bot.active_blockers:
                bot.active_blockers[blocker_id]['status'] = 'claimed'
                bot.active_blockers[blocker_id]['claimed_by'] = user_id
                bot.active_blockers[blocker_id]['claimed_at'] = time.time()
            
            # Notify the blocked user via DM
            bot.send_dm(blocked_user_id, f"🎉 Your blocker for {kr_name} has been claimed by @{user_name}! They'll help you resolve it.")
            
            return jsonify({"text": "OK"})
        return jsonify({"text": "Error"})
    except Exception as e:
        print(f"Error handling claim blocker: {e}")
        return jsonify({"text": "Error"})

def handle_view_submission(bot, payload):
    """Handle modal submissions."""
    try:
        callback_id = payload.get('view', {}).get('callback_id', '')
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        
        print(f"🔍 DEBUG: handle_view_submission called with callback_id: '{callback_id}' for user: {user_name}")
        
        # Enhanced submission tracking to prevent duplicates
        submission_key = f"{user_id}_{callback_id}_{int(time.time())}"
        if not hasattr(bot, 'recent_submissions'):
            bot.recent_submissions = {}
        
        # Check if this is a recent duplicate submission (within 10 seconds)
        current_time = time.time()
        recent_submissions = bot.recent_submissions.get(user_id, {})
        
        # Clean up old submissions (older than 15 seconds)
        recent_submissions = {k: v for k, v in recent_submissions.items() if current_time - v < 15}
        bot.recent_submissions[user_id] = recent_submissions
        
        # Check if this callback_id was recently submitted
        if callback_id in recent_submissions:
            print(f"🔍 DEBUG: Duplicate submission detected for {user_name} with callback_id: {callback_id}")
            return jsonify({"response_action": "clear"})
        
        # Track this submission
        recent_submissions[callback_id] = current_time
        bot.recent_submissions[user_id] = recent_submissions
        
        # Route to appropriate handler
        if callback_id == 'checkin_submit':
            return handle_checkin_submission(bot, payload)
        elif callback_id == 'daily_checkin_submit':
            return handle_daily_checkin_submission(bot, payload)
        elif callback_id == 'blocker_submit':
            return handle_blocker_submission(bot, payload)
        elif callback_id == 'blocker_report_submit':
            return handle_blocker_report_submission(bot, payload)
        elif callback_id == 'blocker_note_submit':
            return handle_blocker_note_submission(bot, payload)
        elif callback_id == 'progress_update_submit':
            return handle_progress_update_submission(bot, payload)
        elif callback_id == 'blocker_details_submit':
            return handle_blocker_details_submission(bot, payload)
        elif callback_id == 'health_public_share_submit':
            return handle_health_public_share_submission(bot, payload)
        elif callback_id == 'health_private_share_submission':
            return handle_health_private_share_submission(bot, payload)
        elif callback_id == 'blocker_completion_submit':
            return handle_blocker_completion_submission(bot, payload)
        elif callback_id == 'blocker_resolution_submit':
            return handle_blocker_resolution_submission(bot, payload)
        elif callback_id == 'blocker_sprint_modal':
            return handle_blocker_sprint_modal_submission(bot, payload)
        else:
            print(f"Unknown modal callback_id: {callback_id}")
            return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling view submission: {e}")
        return jsonify({"response_action": "clear"})

def handle_checkin_submission(bot, payload):
    """Handle checkin modal submission with background processing and validation."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Extract form data with proper validation
        status = values.get('checkin_status', {}).get('status_input', {}).get('value', '').strip()
        track_status = values.get('checkin_track', {}).get('track_input', {}).get('selected_option', {}).get('value', '')
        blockers_status = values.get('checkin_blockers', {}).get('blockers_input', {}).get('selected_option', {}).get('value', '')
        notes = values.get('checkin_notes', {}).get('notes_input', {}).get('value', '').strip()
        
        # Validate required fields and provide guidance
        validation_errors = []
        
        if not status:
            validation_errors.append("• *What did you do today?* - Please describe your work and accomplishments")
        
        if not track_status:
            validation_errors.append("• *Are you on track?* - Please select whether you're on track to meet your goals")
        
        if not blockers_status:
            validation_errors.append("• *Do you have blockers?* - Please select your blocker status")
        
        # If there are validation errors, return them to the user
        if validation_errors:
            error_message = "*Please complete the following required fields:*\n\n" + "\n".join(validation_errors)
            return jsonify({
                "response_action": "errors",
                "errors": {
                    "checkin_status": error_message if not status else None,
                    "checkin_track": error_message if not track_status else None,
                    "checkin_blockers": error_message if not blockers_status else None
                }
            })
        
        # Check for duplicate submission
        data_hash = f"{status[:50]}_{track_status}_{blockers_status}_{notes[:50]}"
        if not track_submission(user_id, "checkin_submission", data_hash):
            return jsonify({
                "response_action": "errors",
                "errors": {
                    "checkin_status": "⚠️ This check-in was already submitted. Please wait a moment before trying again."
                }
            })
        
        # Process in background thread to avoid Slack timeout
        def process_checkin_in_background():
            try:
                # Convert status values to readable format
                track_display = {
                    'yes': '✅ Yes - On track',
                    'no': '❌ No - Behind schedule'
                }.get(track_status, track_status)
                
                blockers_display = {
                    'yes': '❌ Yes - I have blockers',
                    'no': '✅ No blockers'
                }.get(blockers_status, blockers_status)
                
                # Check if check-in is late (submitted after 4 PM EST)
                from datetime import datetime, timezone
                import pytz
                
                est_tz = pytz.timezone('US/Eastern')
                current_est = datetime.now(est_tz)
                scheduled_time = current_est.replace(hour=16, minute=0, second=0, microsecond=0)  # 4 PM
                is_late = current_est > scheduled_time
                
                # Save to Coda
                if bot.coda:
                    try:
                        success = bot.coda.add_standup_response(
                            user_id=user_id,
                            response_text=f"Today: {status}\nOn Track: {track_display}\nBlockers: {blockers_display}\nNotes: {notes}" if notes else f"Today: {status}\nOn Track: {track_display}\nBlockers: {blockers_display}",
                            username=user_name,
                            is_late=is_late
                        )
                        if success:
                            print(f"✅ Checkin response saved to Coda for {user_name}")
                        else:
                            print(f"❌ Failed to save checkin response to Coda for {user_name}")
                    except Exception as e:
                        print(f"❌ Error saving checkin response to Coda: {e}")
                else:
                    print(f"⚠️ Coda service not available - checkin response not saved")
                
                # Send simple confirmation message
                response_text = "✅ *Check-in submitted successfully!*"
                
                if is_late:
                    response_text += f"\n⚠️ *Note: This check-in was submitted late and has been tagged accordingly.*"
                
                bot.send_dm(user_id, response_text)
                
                # If user has blockers or is behind, automatically prompt them to report blockers with buttons
                if blockers_status == 'yes' or track_status == 'no':
                    if blockers_status == 'yes' and track_status == 'no':
                        message = "🚨 *You indicated you have blockers AND you're behind schedule.* Please report your blockers so we can help you get back on track!"
                    elif blockers_status == 'yes':
                        message = "🚨 *You indicated you have blockers.* Please report them so we can help you!"
                    elif track_status == 'no':
                        message = "⚠️ *You indicated you're behind schedule.* If you have blockers causing this, please report them so we can help you get back on track!"
                    
                    blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": message
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Report Blocker"
                                    },
                                    "action_id": "open_blocker_report_modal",
                                    "value": f"checkin_prompt_{user_id}",
                                    "style": "primary"
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "No Blocker to Report"
                                    },
                                    "action_id": "checkin_no_blocker",
                                    "value": f"checkin_no_blocker_{user_id}"
                                }
                            ]
                        }
                    ]
                    
                    bot.send_dm(user_id, "", blocks=blocks)
                
            except Exception as e:
                print(f"Error in background checkin processing: {e}")
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your check-in. Please try again.")
        
        # Start background thread
        import threading
        background_thread = threading.Thread(target=process_checkin_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        # Return proper Flask response immediately
        return jsonify({"response_action": "clear"})
        
    except Exception as e:
        print(f"Error handling checkin submission: {e}")
        return jsonify({"response_action": "clear"})

def handle_blocker_submission(bot, payload):
    """Handle blocker modal submission with comprehensive error handling."""
    print(f"🔍 DEBUG: handle_blocker_submission called")
    try:
        # Validate payload structure
        required_fields = ['user', 'view']
        is_valid, missing_fields = input_validator.validate_payload_structure(payload, required_fields)
        if not is_valid:
            return error_handler.handle_validation_error(
                ValueError(f"Missing required fields: {missing_fields}"),
                "handle_blocker_submission",
                additional_data={'missing_fields': missing_fields}
            )
        
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Validate user ID
        if not input_validator.validate_user_id(user_id):
            return error_handler.handle_validation_error(
                ValueError(f"Invalid user ID: {user_id}"),
                "handle_blocker_submission",
                user_id=user_id
            )
        
        # Extract and validate form data
        description = values.get('blocker_description', {}).get('description_input', {}).get('value', '')
        kr_name = values.get('blocker_kr', {}).get('kr_input', {}).get('value', '')
        urgency = values.get('blocker_urgency', {}).get('urgency_input', {}).get('selected_option', {}).get('value', 'medium')
        
        # Validate required fields
        if not description.strip():
            bot.send_dm(user_id, "❌ Blocker description is required. Please try again.")
            return jsonify({"response_action": "clear"})
        
        if not kr_name.strip():
            bot.send_dm(user_id, "❌ KR name is required. Please try again.")
            return jsonify({"response_action": "clear"})
        
        # Check for duplicate submission
        data_hash = f"{description[:50]}_{kr_name[:50]}_{urgency}"
        if not track_submission(user_id, "blocker_submission", data_hash):
            bot.send_dm(user_id, "⚠️ This blocker submission was already processed. Please wait a moment before trying again.")
            return jsonify({"response_action": "clear"})
        
        # Sanitize inputs
        sanitized_description = input_validator.sanitize_text(description)
        sanitized_kr_name = input_validator.sanitize_text(kr_name)
        
        # Send immediate confirmation to user
        bot.send_dm(user_id, f"✅ Blocker submitted! Processing in background...")
        
        # Run escalation in background thread to avoid blocking the form
        def escalate_in_background():
            try:
                bot.escalate_blocker_with_details(user_id, user_name, sanitized_description, sanitized_kr_name, urgency, "")
                bot.send_dm(user_id, f"✅ Blocker processed and escalated! Your team will be notified.")
                logger.info(f"Blocker submitted successfully by {user_name}", user_id=user_id, kr_name=sanitized_kr_name)
            except Exception as escalation_error:
                # Log the error
                error_handler.handle_unexpected_error(
                    escalation_error, "escalate_blocker_with_details", user_id,
                    additional_data={'description': sanitized_description, 'kr_name': sanitized_kr_name, 'urgency': urgency}
                )
                # Inform user of the error
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your blocker. Please try again or contact support.")
        
        # Start background thread
        import threading
        background_thread = threading.Thread(target=escalate_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        # Return proper Flask response
        return jsonify({"response_action": "clear"})
        
    except Exception as e:
        # Log the error
        error_handler.handle_unexpected_error(
            e, "handle_blocker_submission", 
            user_id=payload.get('user', {}).get('id') if payload else None
        )
        # Try to inform user of the error
        try:
            user_id = payload.get('user', {}).get('id') if payload else None
            if user_id:
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your blocker submission. Please try again.")
        except:
            pass  # If we can't even send the error message, just continue
        
        return jsonify({"response_action": "clear"})

def handle_blocker_note_submission(bot, payload):
    """Handle blocker note modal submission with comprehensive error handling."""
    try:
        # Validate payload structure
        required_fields = ['user', 'view']
        is_valid, missing_fields = input_validator.validate_payload_structure(payload, required_fields)
        if not is_valid:
            return error_handler.handle_validation_error(
                ValueError(f"Missing required fields: {missing_fields}"),
                "handle_blocker_note_submission",
                additional_data={'missing_fields': missing_fields}
            )
        
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Validate user ID
        if not input_validator.validate_user_id(user_id):
            return error_handler.handle_validation_error(
                ValueError(f"Invalid user ID: {user_id}"),
                "handle_blocker_note_submission",
                user_id=user_id
            )
        
        # Extract note
        note = values.get('note_input', {}).get('note_text', {}).get('value', '')
        blocker_id = bot.tracked_blockers.get(user_id)
        
        # Sanitize note
        sanitized_note = input_validator.sanitize_text(note)
        
        if blocker_id and bot.coda:
            try:
                # Update blocker note in Coda
                success = bot.coda.update_blocker_note(blocker_id, sanitized_note)
                if success:
                    bot.send_dm(user_id, "✅ Blocker note updated successfully!")
                    logger.info(f"Blocker note updated successfully by {user_name}", user_id=user_id, blocker_id=blocker_id)
                else:
                    bot.send_dm(user_id, "❌ Failed to update blocker note. Please try again.")
                    logger.warning(f"Failed to update blocker note for {user_name}", user_id=user_id, blocker_id=blocker_id)
            except Exception as coda_error:
                error_handler.handle_coda_error(
                    coda_error, "update_blocker_note", user_id,
                    additional_data={'blocker_id': blocker_id, 'note': sanitized_note}
                )
                bot.send_dm(user_id, "❌ Sorry, there was an error updating your blocker note. Please try again.")
        else:
            if not blocker_id:
                bot.send_dm(user_id, "❌ No blocker found to update. Please try again.")
            else:
                bot.send_dm(user_id, "⚠️ Coda service not available. Please try again later.")
        
        # Clear tracked blocker
        bot.tracked_blockers.pop(user_id, None)
        
        # Return proper Flask response
        return jsonify({"response_action": "clear"})
        
    except Exception as e:
        # Log the error
        error_handler.handle_unexpected_error(
            e, "handle_blocker_note_submission", 
            user_id=payload.get('user', {}).get('id') if payload else None
        )
        # Try to inform user of the error
        try:
            user_id = payload.get('user', {}).get('id') if payload else None
            if user_id:
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your note submission. Please try again.")
        except:
            pass  # If we can't even send the error message, just continue
        
        return jsonify({"response_action": "clear"})

def handle_progress_update_submission(bot, payload):
    """Handle progress update modal submission."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        private_metadata = payload['view'].get('private_metadata', '')
        
        # Extract progress update
        progress = values.get('progress_input', {}).get('progress_text', {}).get('value', '')
        
        # Check if we have private_metadata (new format from /blockers)
        if private_metadata:
            # Parse private_metadata: blocker_row_id_kr_name
            parts = private_metadata.split('_')
            if len(parts) >= 2:
                blocker_row_id = parts[0]
                kr_name = '_'.join(parts[1:])  # KR name might contain underscores
                
                # Save progress update to Coda
                if bot.coda:
                    try:
                        # Update blocker with progress
                        success = bot.coda.update_blocker_progress(
                            blocker_row_id=blocker_row_id,
                            progress_update=progress,
                            updated_by=user_name
                        )
                        if success:
                            print(f"✅ Progress update saved to Coda for {user_name}")
                        else:
                            print(f"❌ Failed to save progress update to Coda for {user_name}")
                    except Exception as e:
                        print(f"❌ Error saving progress update to Coda: {e}")
                
                # Send confirmation DM
                confirmation_text = f"✅ Progress update submitted!\n\n"
                confirmation_text += f"*KR:* {kr_name}\n"
                confirmation_text += f"*Progress Update:* {progress}\n"
                confirmation_text += f"*Updated by:* @{user_name}"
                
                bot.send_dm(user_id, confirmation_text)
            else:
                bot.send_dm(user_id, "❌ Error: Could not parse blocker information.")
        else:
            # Legacy format - use tracked_blockers
            blocker_id = bot.tracked_blockers.get(user_id)
            
            if blocker_id:
                # Update the original blocker message with progress
                bot.update_blocker_message_with_progress(blocker_id, bot.channel_id, None)
                
                bot.send_dm(user_id, "✅ Progress update submitted!")
            else:
                bot.send_dm(user_id, "❌ No blocker found to update.")
            
            # Clear tracked blocker
            bot.tracked_blockers.pop(user_id, None)
        
        # Return proper Flask response
        from flask import jsonify
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling progress update submission: {e}")
        from flask import jsonify
        return jsonify({"response_action": "clear"})

def handle_events(bot, payload):
    """Handle Slack events."""
    try:
        event_type = payload.get('type')
        
        if event_type == 'url_verification':
            return payload.get('challenge')
        
        if event_type == 'event_callback':
            event = payload.get('event', {})
            event_subtype = event.get('subtype')
            
            # Skip bot messages and message edits
            if event_subtype in ['bot_message', 'message_changed']:
                return "OK"
            
            # Handle different event types
            if event.get('type') == 'message':
                return _handle_message_event(bot, event)
            elif event.get('type') == 'reaction_added':
                return _handle_reaction_event(bot, event)
        
        return "OK"
    except Exception as e:
        print(f"Error handling events: {e}")
        return "Error"

def _handle_message_event(bot, event):
    """Handle message events."""
    try:
        user_id = event.get('user')
        text = event.get('text', '')
        channel_id = event.get('channel')
        thread_ts = event.get('thread_ts')
        message_ts = event.get('ts')
        
        if not user_id or not text:
            return "OK"
        
        # Skip bot messages to prevent processing our own messages
        if 'bot_id' in event or user_id == bot.config.SLACK_BOT_USER_ID:
            return "OK"
        
        # Check if this is a DM (channel starts with 'D')
        is_dm = channel_id.startswith('D')
        
        if is_dm:
            # Check if this is a reply to a standup prompt (has thread_ts)
            if thread_ts:
                print(f"🔍 DEBUG: Processing as standup response (in thread)")
                # This is a reply in a DM (standup response)
                bot.handle_standup_response(
                    user_id=user_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    text=text,
                    channel_id=channel_id
                )
                return "standup_response_processed"
            
            # Handle commands in DM
            if bot.handle_commands(user_id, text, channel_id):
                return "command_processed"
        
        # Check for bot mentions
        if f'<@{bot.config.SLACK_BOT_USER_ID}>' in text:
            return _handle_bot_mention(bot, user_id, text, channel_id)
        
        # Check for specific keywords
        if any(keyword in text.lower() for keyword in ['blocker', 'blocked', 'stuck']):
            return _handle_blocker_keyword(bot, user_id, text, channel_id)
        
        return "OK"
    except Exception as e:
        print(f"Error handling message event: {e}")
        return "Error"

def _handle_reaction_event(bot, event):
    """Handle reaction events."""
    try:
        user_id = event.get('user')
        reaction = event.get('reaction')
        item = event.get('item', {})
        
        # Handle daily standup reactions
        if reaction in ['white_check_mark', 'warning', 'rotating_light'] and item.get('type') == 'message':
            message_ts = item.get('ts')
            if message_ts in bot.active_standups:
                bot.handle_quick_reaction(user_id, message_ts, reaction)
                return "OK"
        
        if reaction == 'white_check_mark' and item.get('type') == 'message':
            # Handle completion reaction
            return _handle_completion_reaction(bot, user_id, item)
        
        return "OK"
    except Exception as e:
        print(f"Error handling reaction event: {e}")
        return "Error"

def _handle_bot_mention(bot, user_id, text, channel_id):
    """Handle bot mentions."""
    try:
        user_name = bot.get_user_name(user_id)
        
        # Extract command from mention
        mention_pattern = f'<@{bot.config.SLACK_BOT_USER_ID}>'
        command_text = text.replace(mention_pattern, '').strip()
        
        if not command_text:
            # Show help
            help_text = f"@{user_name} Here are the available commands:\\n"
            help_text += "• `/kr` - View or update your KRs\\n"
            help_text += "• `/checkin` - Check in with your status\\n"
            help_text += "• `/blocked` - Report a blocker\\n"
            help_text += "• `/health` - Health check\\n"
            help_text += "• `/blocker` - View your blockers\\n"
            help_text += "• `/role` - Manage your roles"
            
            bot.send_message(channel_id, help_text)
            return "OK"
        
        # Process as command
        parts = command_text.split(' ', 1)
        command = parts[0].lower()
        text_param = parts[1] if len(parts) > 1 else ""
        
        # Import the command processing function
        from .commands import _process_command
        _process_command(bot, user_id, command, text_param, channel_id)
        return "OK"
    except Exception as e:
        print(f"Error handling bot mention: {e}")
        return "Error"

def _handle_blocker_keyword(bot, user_id, text, channel_id):
    """Handle blocker keywords in messages."""
    try:
        user_name = bot.get_user_name(user_id)
        
        # Check if this is a new blocker report
        if 'blocker' in text.lower() or 'blocked' in text.lower():
            # Ask if they want to report a blocker
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"@{user_name} I noticed you mentioned being blocked. Would you like to report this as a formal blocker?"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Yes, report blocker"},
                            "action_id": "report_blocker",
                            "value": text
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "No, thanks"},
                            "action_id": "dismiss_blocker"
                        }
                    ]
                }
            ]
            
            bot.send_message(channel_id, "", blocks=blocks)
        
        return "OK"
    except Exception as e:
        print(f"Error handling blocker keyword: {e}")
        return "Error"

def _handle_completion_reaction(bot, user_id, item):
    """Handle completion reactions."""
    try:
        # This could be used to mark items as complete
        # For now, just log it
        print(f"User {user_id} marked item {item.get('ts')} as complete")
        return "OK"
    except Exception as e:
        print(f"Error handling completion reaction: {e}")
        return "Error"

def register_event_routes(app, bot):
    """Register event routes with comprehensive error handling."""
    
    @app.route('/slack/events', methods=['POST'])
    def handle_events_route():
        """Handle Slack events with comprehensive error handling."""
        try:
            # Handle both JSON and form-encoded payloads
            if request.is_json:
                payload = request.get_json()
            else:
                # Handle form-encoded data (button clicks come this way)
                payload = request.form.to_dict()
                if 'payload' in payload:
                    import json
                    payload = json.loads(payload['payload'])
                print(f"🔍 DEBUG: Received form-encoded payload: {payload}")
            
            if not payload:
                print(f"❌ DEBUG: Empty payload received")
                return jsonify({"text": "OK"})
            
            # Log payload for debugging
            log_payload_for_debugging(payload)
            
            # Check if payload is valid
            if not payload:
                print(f"❌ DEBUG: Empty or invalid payload received")
                return jsonify({"text": "OK"})
            
            # Validate payload structure - but be more flexible for different event types
            payload_type = payload.get('type')
            print(f"🔍 DEBUG: Payload type: {payload_type}")
            print(f"🔍 DEBUG: Payload keys: {list(payload.keys()) if payload else 'None'}")
            
            # Handle different payload types
            if payload_type == 'url_verification':
                return jsonify({"challenge": payload.get('challenge')})
            elif payload_type == 'event_callback':
                # This is a standard Slack event
                pass
            elif payload_type == 'block_actions' or payload_type == 'view_submission':
                # This is an interactive component
                pass
            elif not payload_type:
                # Some events might not have a type field, check if it's an interactive component
                if 'actions' in payload or 'view' in payload:
                    print(f"🔍 DEBUG: Interactive component detected without type field")
                    pass
                else:
                    print(f"❌ DEBUG: Unknown payload structure - no type field and not interactive")
                    print(f"❌ DEBUG: Full payload: {payload}")
                    return jsonify({"text": "OK"})
            else:
                print(f"🔍 DEBUG: Unknown payload type: {payload_type}")
                return jsonify({"text": "OK"})
            
            # Handle interactive components (block_actions, view_submission)
            if payload_type in ['block_actions', 'view_submission']:
                print(f"🔍 DEBUG: Processing interactive component with type: {payload_type}")
                return handle_interactive_components(bot, payload)
            
            # Handle interactive components without type field (some Slack events)
            if not payload_type and ('actions' in payload or 'view' in payload):
                print(f"🔍 DEBUG: Processing interactive component without type field")
                return handle_interactive_components(bot, payload)
            
            # Handle event callbacks
            if payload_type == 'event_callback':
                event = payload.get('event', {})
                
                print(f"🔍 DEBUG: Event callback received - Event type: {event.get('type')}")
                print(f"🔍 DEBUG: Event keys: {list(event.keys())}")
                
                # Validate event structure
                if not event:
                    print(f"❌ DEBUG: Event is missing from payload")
                    return jsonify({"text": "OK"})
                
                # Skip bot messages and message edits
                event_subtype = event.get('subtype')
                if event_subtype in ['bot_message', 'message_changed']:
                    return jsonify({"text": "OK"})
                
                            # Handle button clicks in DMs (they come as event_callback)
            if event.get('type') == 'message' and 'blocks' in event:
                print(f"🔍 DEBUG: Message with blocks detected - checking for button interactions")
                blocks = event.get('blocks', [])
                
                # Check if this is an actual button click event (has user interaction)
                # Only process if this event represents a user clicking a button, not just a message with buttons
                if event.get('user') and event.get('user') != 'unknown' and event.get('user') != 'U0912DJRNSF':
                    print(f"🔍 DEBUG: User interaction detected - processing as button click")
                    for block in blocks:
                        if block.get('type') == 'actions':
                            elements = block.get('elements', [])
                            for element in elements:
                                if element.get('type') == 'button':
                                    print(f"🔍 DEBUG: Button found in event_callback: {element.get('action_id')}")
                                    # Convert event_callback to block_actions format for processing
                                    button_payload = {
                                        'type': 'block_actions',
                                        'user': {'id': event.get('user', 'unknown')},
                                        'actions': [element],
                                        'channel': {'id': event.get('channel', 'unknown')},
                                        'message': {'ts': event.get('ts', 'unknown')},
                                        'trigger_id': event.get('trigger_id')  # Add trigger_id if available
                                    }
                                    print(f"🔍 DEBUG: Converted button payload: {button_payload}")
                                    return handle_interactive_components(bot, button_payload)
                else:
                    print(f"🔍 DEBUG: No user interaction or bot message - treating as normal message with buttons")
                    # This is just a message with buttons, not a button click
                    # Just return OK for bot messages with buttons
                    return jsonify({"text": "OK"})
                
                # Handle different event types
                if event.get('type') == 'message':
                    result = _handle_message_event(bot, event)
                elif event.get('type') == 'reaction_added':
                    result = _handle_reaction_event(bot, event)
                else:
                    logger.info(f"Unhandled event type: {event.get('type')}")
                    result = "OK"
                
                if result == "OK":
                    return jsonify({"text": "OK"})
                else:
                    return jsonify({"text": result})
            
            # Handle interactive components
            if payload.get('type') in ['interactive_message', 'block_actions']:
                return handle_interactive_components(bot, payload)
            
            # Handle view submissions
            if payload.get('type') == 'view_submission':
                return handle_view_submission(bot, payload)
            
            logger.info(f"Unhandled payload type: {payload.get('type')}")
            return jsonify({"text": "OK"})
            
        except Exception as e:
            return error_handler.handle_unexpected_error(
                e, "handle_events_route"
            )

def handle_interactive_components(bot, payload):
    """Handle interactive components with comprehensive error handling."""
    try:
        print(f"🔍 DEBUG: handle_interactive_components called")
        print(f"🔍 DEBUG: Payload type: {payload.get('type')}")
        
        # Validate payload structure - be more lenient for different payload types
        if not payload:
            print(f"❌ DEBUG: Empty payload")
            return jsonify({"text": "OK"})
        
        # Check if this is a valid interactive component payload
        has_actions = 'actions' in payload and payload['actions']
        has_view = 'view' in payload and payload['view']
        has_user = 'user' in payload and payload['user']
        
        # Handle view_submission payloads (modal submissions)
        if payload.get('type') == 'view_submission':
            return handle_view_submission(bot, payload)
        
        # For block_actions, we need actions and user
        if not has_actions or not has_user:
            print(f"❌ DEBUG: Not a valid interactive component payload")
            print(f"❌ DEBUG: Has actions: {has_actions}, Has user: {has_user}")
            print(f"❌ DEBUG: Payload keys: {list(payload.keys()) if payload else 'None'}")
            # Return OK instead of error to avoid spam
            return jsonify({"text": "OK"})
        
        actions = payload.get('actions', [])
        if not actions:
            print(f"❌ DEBUG: No actions found in payload")
            return jsonify({"text": "OK"})
        
        action_id = actions[0].get('action_id', '')
        user_id = payload['user']['id']
        
        print(f"🔍 DEBUG: Action ID: {action_id}")
        print(f"🔍 DEBUG: User ID: {user_id}")
        
        # Validate user ID
        if not input_validator.validate_user_id(user_id):
            print(f"❌ DEBUG: Invalid user ID: {user_id}")
            return jsonify({"text": "OK"})
        
        # Route to appropriate handler
        if action_id == 'edit_blocker_note':
            return safe_executor.execute(handle_blocker_note_edit, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'complete_blocker':
            return safe_executor.execute(handle_blocker_completion, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'complete_blocker_with_form':
            return safe_executor.execute(handle_complete_blocker_with_form, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id in ['great', 'okay', 'not_great']:
            return safe_executor.execute(handle_health_response, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id in ['escalate_help', 'monitor_issue']:
            return safe_executor.execute(handle_followup_response, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id in ['health_share_public', 'health_share_private']:
            return safe_executor.execute(handle_health_share_response, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'health_no_share':
            return safe_executor.execute(handle_health_no_share, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id in ['mentor_yes', 'mentor_no']:
            return safe_executor.execute(handle_mentor_response, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id in ['blocker_resolved', 'blocker_still_blocked', 'blocker_need_help']:
            return safe_executor.execute(handle_blocker_followup_response, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'claim_blocker':
            return safe_executor.execute(handle_claim_blocker, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'update_progress':
            return safe_executor.execute(handle_update_progress, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'mark_resolved':
            return safe_executor.execute(handle_mark_resolved, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'view_blocker_details':
            return safe_executor.execute(handle_view_blocker_details, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'view_details':
            return safe_executor.execute(handle_view_details, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'submit_blocker_details':
            return safe_executor.execute(handle_submit_blocker_details, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'open_blocker_report_modal':
            return safe_executor.execute(handle_open_blocker_report_modal, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'open_blocker_modal_channel':
            return safe_executor.execute(handle_open_blocker_modal_channel, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'submit_blocker_form':
            return safe_executor.execute(handle_submit_blocker_form, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'open_checkin_modal':
            return safe_executor.execute(handle_open_checkin_modal, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'checkin_no_blocker':
            return safe_executor.execute(handle_checkin_no_blocker, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'view_all_blockers':
            return safe_executor.execute(handle_view_all_blockers, "handle_interactive_components", user_id, bot=bot, payload=payload)
        elif action_id == 'open_blocker_sprint_modal':
            return safe_executor.execute(handle_open_blocker_sprint_modal, "handle_interactive_components", user_id, bot=bot, payload=payload)
        else:
            logger.warning(f"Unhandled action_id: {action_id}")
            return jsonify({"text": "OK"})
            
    except Exception as e:
        return error_handler.handle_unexpected_error(
            e, "handle_interactive_components"
        )



def handle_health_response(bot, payload):
    """Handle health check button responses with background processing."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        action_id = payload['actions'][0]['action_id']
        channel_id = payload['channel']['id']
        message_ts = payload['message']['ts']
        
        # Map action_id to mood
        mood_map = {
            'great': '😊 Great',
            'okay': '😐 Okay',
            'not_great': '😕 Not great'
        }
        
        mood = mood_map.get(action_id, 'Unknown')
        
        # Store the mood for later use
        if not hasattr(bot, 'health_responses'):
            bot.health_responses = {}
        bot.health_responses[user_id] = mood
        
        # Send immediate confirmation
        bot.send_dm(user_id, f"✅ Health check response received! Processing in background...")
        
        # Process Coda saving in background thread to avoid Slack timeout
        def process_health_check_in_background():
            try:
                # Save to Coda if available - use the main Health_Check table
                if bot.coda:
                    try:
                        # For initial health check, save to main Health_Check table
                        success = bot.coda.save_health_check(user_id, user_name, mood, "", False)
                        if success:
                            print(f"✅ Health check response stored in Health_Check table for {user_name}")
                            bot.send_dm(user_id, "✅ Your health check has been saved to Coda!")
                        else:
                            print(f"❌ Failed to store health check in Health_Check table for {user_name}")
                            bot.send_dm(user_id, "⚠️ Your health check was processed, but there was an issue saving to Coda.")
                    except Exception as e:
                        print(f"❌ Error storing health check in Health_Check table: {e}")
                        bot.send_dm(user_id, "⚠️ Your health check was processed, but there was an issue saving to Coda.")
                else:
                    bot.send_dm(user_id, "✅ Your health check has been processed!")
                
            except Exception as e:
                print(f"Error in background health check processing: {e}")
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your health check. Please try again.")
        
        # Start background thread
        import threading
        background_thread = threading.Thread(target=process_health_check_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        # Send follow-up prompt asking what they want to share
        followup_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Thanks for your response! Would you like to share anything with the team?"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Public Share",
                            "emoji": True
                        },
                        "value": f"public_{action_id}",
                        "action_id": "health_share_public",
                        "style": "primary"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Private Share",
                            "emoji": True
                        },
                        "value": f"private_{action_id}",
                        "action_id": "health_share_private"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "No Thanks",
                            "emoji": True
                        },
                        "value": f"no_share_{action_id}",
                        "action_id": "health_no_share"
                    }
                ]
            }
        ]
        
        # Send the follow-up prompt
        bot.send_dm(user_id, "Thanks for your response! Would you like to share anything with the team?", blocks=followup_blocks)
        
        return jsonify({"response_action": "clear"})
        
    except Exception as e:
        print(f"❌ Error in handle_health_response: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response_action": "clear"})

def handle_update_progress(bot, payload):
    """Handle update progress button click."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        trigger_id = payload['trigger_id']
        value = payload['actions'][0]['value']
        
        # Parse value: could be either "blocker_row_id_kr_name" (from /blockers) or old format
        parts = value.split('_')
        
        if parts[0] == 'blocker' and len(parts) >= 3:
            # From /blockers command
            blocker_row_id = parts[1]
            kr_name = '_'.join(parts[2:])  # KR name might contain underscores
            
            # Create progress update modal
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
            
            bot.open_modal(
                trigger_id=trigger_id,
                title="Update Blocker Progress",
                blocks=blocks,
                submit_text="Submit Progress",
                callback_id="progress_update_submit",
                private_metadata=f"{blocker_row_id}_{kr_name}"
            )
        else:
            # Legacy format - store blocker info for modal submission
            bot.tracked_blockers[user_id] = value
            
            # Create progress update modal
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
            
            bot.open_modal(
                trigger_id=trigger_id,
                title="Update Blocker Progress",
                blocks=blocks,
                submit_text="Submit Progress",
                callback_id="progress_update_submit"
            )
        
        return jsonify({"text": "OK"})
    except Exception as e:
        print(f"Error handling update progress: {e}")
        return jsonify({"text": "Error"})

def handle_mark_resolved(bot, payload):
    """Handle mark resolved button click."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        value = payload['actions'][0]['value']
        channel_id = payload['channel']['id']
        message_ts = payload['message']['ts']
        
        # Parse value: could be either "blocker_row_id_kr_name" (from /blockers) or "resolve_blocker_id" (from channel)
        parts = value.split('_')
        
        if parts[0] == 'blocker' and len(parts) >= 3:
            # From /blockers command - open resolution form
            blocker_row_id = parts[1]
            kr_name = '_'.join(parts[2:])  # KR name might contain underscores
            
            # Open resolution form modal
            trigger_id = payload['trigger_id']
            blocks = [
                {
                    "type": "input",
                    "block_id": "resolution_notes",
                    "label": {"type": "plain_text", "text": "Resolution Notes"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "resolution_notes_input",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "How was this blocker resolved?"}
                    }
                }
            ]
            
            bot.open_modal(
                trigger_id=trigger_id,
                title="Resolve Blocker",
                blocks=blocks,
                submit_text="Mark Resolved",
                callback_id="blocker_resolution_submit",
                private_metadata=f"{blocker_row_id}_{kr_name}"
            )
            
        elif parts[0] == 'resolve' and len(parts) >= 2:
            # From channel escalation - direct resolution
            blocker_id = parts[1]
            
            # Update message to show resolution
            updated_text = f"✅ *Blocker has been resolved by @{user_name}*\n\n"
            updated_text += f"*Resolved by:* @{user_name}\n"
            updated_text += f"*Status:* Complete"
            
            bot.update_message(channel_id, message_ts, updated_text)
            
            # Update Coda and notify blocked user if we have blocker info
            if hasattr(bot, 'active_blockers') and blocker_id in bot.active_blockers:
                blocker_info = bot.active_blockers[blocker_id]
                blocked_user_id = blocker_info['user_id']
                kr_name = blocker_info['kr_name']
                
                # Update Coda
                if bot.coda:
                    try:
                        bot.coda.mark_blocker_complete(row_id=blocker_id, resolution_notes="Resolved via channel escalation")
                        bot.coda.resolve_blocker_from_kr(kr_name=kr_name, resolution_notes="Resolved via channel escalation")
                        
                        # Send completion notification to leads channel
                        try:
                            from datetime import datetime
                            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            completion_message = f"🎉 *Blocker Resolved* - @{user_name} has successfully resolved a blocker!"
                            completion_message += f"\n• *KR:* {kr_name}"
                            completion_message += f"\n• *Resolved by:* @{user_name}"
                            completion_message += f"\n• *Resolved at:* {current_time}"
                            completion_message += f"\n• *Resolution notes:* Resolved via channel escalation"
                            completion_message += f"\n• *Status:* KR status updated to 'Unblocked' in Coda"
                            
                            bot.send_completion_message_to_accessible_channel(completion_message)
                            print(f"✅ Sent completion message to leads channel")
                        except Exception as channel_error:
                            print(f"⚠️ Error sending completion message to channel: {channel_error}")
                        
                    except Exception as e:
                        print(f"❌ Error updating Coda: {e}")
                
                # Notify the blocked user via DM
                bot.send_dm(blocked_user_id, f"🎉 Your blocker for {kr_name} has been resolved by @{user_name}!")
        
        return jsonify({"text": "OK"})
    except Exception as e:
        print(f"Error handling mark resolved: {e}")
        return jsonify({"text": "Error"})

def handle_daily_checkin_submission(bot, payload):
    """Handle daily checkin modal submission."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Extract form data
        yesterday = values.get('yesterday_work', {}).get('yesterday_input', {}).get('value', '')
        today = values.get('today_work', {}).get('today_input', {}).get('value', '')
        blockers = values.get('blockers', {}).get('blockers_input', {}).get('value', '')
        
        # Save to Coda
        if bot.coda:
            try:
                # Combine the responses into a single text
                response_text = f"Yesterday: {yesterday}\nToday: {today}\nBlockers: {blockers}"
                success = bot.coda.add_standup_response(
                    user_id=user_id,
                    response_text=response_text,
                    username=user_name
                )
                if success:
                    print(f"✅ Daily checkin response saved to Coda for {user_name}")
                else:
                    print(f"❌ Failed to save daily checkin response to Coda for {user_name}")
            except Exception as e:
                print(f"❌ Error saving daily checkin response to Coda: {e}")
        else:
            print(f"⚠️ Coda service not available - daily checkin response not saved")
        
        # Send confirmation as DM
        response_text = f"✅ @{user_name} Daily check-in submitted!\n\n"
        response_text += f"*Yesterday:* {yesterday}\n"
        response_text += f"*Today:* {today}\n"
        if blockers:
            response_text += f"*Blockers:* {blockers}"
        
        # Send as DM
        bot.send_dm(user_id, response_text)
        
        # Return proper Flask response
        from flask import jsonify
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling daily checkin submission: {e}")
        from flask import jsonify
        return jsonify({"response_action": "clear"})

def handle_blocker_report_submission(bot, payload):
    """Handle blocker report modal submission with duplicate prevention."""
    print(f"🔍 DEBUG: handle_blocker_report_submission called")
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Extract form data
        description = values.get('blocker_description', {}).get('blocker_description_input', {}).get('value', '')
        kr_name = values.get('kr_name', {}).get('kr_name_input', {}).get('value', '')
        urgency = values.get('urgency', {}).get('urgency_input', {}).get('selected_option', {}).get('value', 'Medium')
        notes = values.get('notes', {}).get('notes_input', {}).get('value', '')
        
        # Check for duplicate submission
        data_hash = f"{description[:50]}_{kr_name[:50]}_{urgency}_{notes[:50]}"
        if not track_submission(user_id, "blocker_report_submission", data_hash):
            bot.send_dm(user_id, "⚠️ This blocker report was already processed. Please wait a moment before trying again.")
            return jsonify({"response_action": "clear"})
        
        # Send immediate confirmation to user
        bot.send_dm(user_id, f"✅ Blocker submitted! Processing in background...")
        
        # Run escalation in background thread to avoid blocking the form
        def escalate_in_background():
            try:
                bot.escalate_blocker_with_details(user_id, user_name, description, kr_name, urgency, notes)
                bot.send_dm(user_id, f"✅ Blocker processed and escalated! Your team will be notified.")
            except Exception as escalation_error:
                print(f"Error in background escalation: {escalation_error}")
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your blocker. Please try again or contact support.")
        
        # Start background thread
        import threading
        background_thread = threading.Thread(target=escalate_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        # Return proper Flask response
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling blocker report submission: {e}")
        return jsonify({"response_action": "clear"})



def handle_view_blocker_details(bot, payload):
    """Handle view blocker details button click."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        value = payload['actions'][0]['value']
        channel_id = payload['channel']['id']
        message_ts = payload['message']['ts']
        
        # Parse value: user_id_kr_name
        parts = value.split('_')
        if len(parts) >= 2:
            blocked_user_id = parts[0]
            kr_name = parts[1]
            
            # Call the bot method to view blocker details
            bot.view_blocker_details(f"{blocked_user_id}_{kr_name}", channel_id, message_ts)
        
        return jsonify({"text": "OK"})
    except Exception as e:
        print(f"Error handling view blocker details: {e}")
        return jsonify({"text": "Error"})

def handle_view_details(bot, payload):
    """Handle view details button click - shows comprehensive KR details and replaces reply message."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        value = payload['actions'][0]['value']
        channel_id = payload['channel']['id']
        message_ts = payload['message']['ts']
        
        # Parse value: view_details_blocker_U0919MVQLLU_1753924282_Create linkedin posts for urgent intern positions
        parts = value.split('_')
        if len(parts) >= 4:
            # Format: view_details_blocker_U0919MVQLLU_1753924282_KR_NAME_WITH_SPACES
            # The blocker_id is actually "blocker_U0919MVQLLU_1753924282"
            # parts[0] = "view"
            # parts[1] = "details" 
            # parts[2] = "blocker"
            # parts[3] = "U0919MVQLLU"
            # parts[4] = "1753924282"
            # parts[5:] = KR_NAME_WITH_SPACES
            
            # Reconstruct the blocker_id correctly
            if parts[1] == "details" and parts[2] == "blocker":
                blocker_id = f"{parts[2]}_{parts[3]}_{parts[4]}"  # blocker_U0919MVQLLU_1753924282
                kr_name = '_'.join(parts[5:])  # KR name might contain underscores and spaces
            else:
                print(f"❌ Unexpected button value format: {value}")
                return jsonify({"text": "Error"})
        
        # Get comprehensive KR details from Coda using the same search as /kr command
        kr_matches = bot.coda.search_kr_table(kr_name) if bot.coda else []
        kr_details = None
        kr_blocked_info = None
        kr_progress = bot.get_kr_progress_from_coda(kr_name)
        
        # Use the first match found (same logic as /kr command)
        if kr_matches:
            match = kr_matches[0]  # Use first match
            kr_details = {
                "row_id": match.get("id"),
                "kr_name": match.get("c-yQ1M6UqTSj", ""),
                "owner": match.get("c-efR-vVo_3w", ""),
                "status": match.get("c-cC29Yow8Gr", ""),
                "definition_of_done": match.get("c-P_mQJLObL0", ""),
                "target_date": match.get("c--UuxnDdGq7", ""),
                "progress": match.get("c--I8Kuqx_r3", ""),
                "notes": match.get("c-whRefnNl8_", "")
            }
            # Get blocked info for this specific KR
            kr_blocked_info = bot.coda.get_kr_blocked_info(kr_name) if bot.coda else None
        
        # Create comprehensive details message
        details_text = f"📋 *KR Details for: {kr_name}*\n\n"
        
        # Add note about search results
        if kr_matches:
            details_text += f"*Found in KR database search*\n\n"
        else:
            details_text += f"*⚠️ KR not found in database*\n\n"
        
        # Add KR details if available
        if kr_details:
            details_text += f"*Owner:* {kr_details.get('owner', 'Unknown')}\n"
            details_text += f"*Status:* {kr_details.get('status', 'Unknown')}\n"
            details_text += f"*Definition of Done:* {kr_details.get('definition_of_done', 'Not specified')}\n"
            details_text += f"*Target Date:* {kr_details.get('target_date', 'Not specified')}\n\n"
        
        # Add progress information
        details_text += "*Progress Information:*\n"
        if kr_details and kr_details.get("progress"):
            details_text += f"• *Current Progress:* {kr_details.get('progress')}\n"
        elif kr_progress:
            details_text += f"• *Current Progress:* {kr_progress}\n"
        else:
            details_text += "• *Current Progress:* No progress data available\n"
        
        # Add blocked information if KR is blocked
        if kr_blocked_info and kr_blocked_info.get('is_blocked'):
            details_text += f"\n*🚨 BLOCKED STATUS:*\n"
            details_text += f"• *Blocked At:* {kr_blocked_info.get('blocked_at', 'Unknown')}\n"
            details_text += f"• *Blocked By:* {kr_blocked_info.get('blocked_by', 'Unknown')}\n"
            details_text += f"• *Blocker Context:* {kr_blocked_info.get('blocker_context', 'No context provided')}\n"
        
        # Add blocker context if available
        if hasattr(bot, 'active_blockers') and blocker_id in bot.active_blockers:
            blocker_info = bot.active_blockers[blocker_id]
            details_text += f"\n*Current Blocker Info:*\n"
            details_text += f"• *Status:* {blocker_info.get('status', 'Unknown')}\n"
            if blocker_info.get('claimed_by'):
                claimed_by_name = bot.get_user_name(blocker_info['claimed_by'])
                details_text += f"• *Claimed by:* @{claimed_by_name}\n"
            details_text += f"• *Urgency:* {blocker_info.get('urgency', 'Unknown')}\n"
            details_text += f"• *Notes:* {blocker_info.get('notes', 'None')}\n"
        
        # Check if we have a stored reply timestamp for this blocker
        reply_ts = None
        if hasattr(bot, 'active_blockers') and blocker_id in bot.active_blockers:
            blocker_info = bot.active_blockers[blocker_id]
            reply_ts = blocker_info.get('details_reply_ts')
        
        if reply_ts:
            # Try to update the existing reply message
            try:
                bot.update_message(channel_id, reply_ts, details_text)
                print(f"✅ Updated existing details message for KR '{kr_name}' (reply_ts: {reply_ts})")
                return jsonify({"text": "OK"})
            except Exception as update_error:
                print(f"⚠️ Error updating existing message: {update_error}")
                # If update fails, we'll send a new message below
        
        # Send a new reply and store its timestamp
        try:
            response = bot.send_message(channel_id, details_text, thread_ts=message_ts)
            if response and hasattr(bot, 'active_blockers') and blocker_id in bot.active_blockers:
                # Store the reply timestamp for future updates
                bot.active_blockers[blocker_id]['details_reply_ts'] = response['ts']
                print(f"✅ Sent new details message for KR '{kr_name}' and stored reply_ts: {response['ts']}")
            else:
                print(f"✅ Sent new details message for KR '{kr_name}'")
        except Exception as send_error:
            print(f"❌ Error sending details message: {send_error}")
    
        return jsonify({"text": "OK"})
    except Exception as e:
        print(f"Error handling view details: {e}")
        return jsonify({"text": "Error"})

def handle_submit_blocker_details(bot, payload):
    """Handle submit blocker details button click."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        trigger_id = payload['trigger_id']
        
        # Create blocker details modal
        blocks = [
            {
                "type": "input",
                "block_id": "blocker_description",
                "label": {"type": "plain_text", "text": "What's blocking you?"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "blocker_description_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Describe the blocker in detail..."}
                }
            },
            {
                "type": "input",
                "block_id": "kr_name",
                "label": {"type": "plain_text", "text": "Key Result (KR) Name"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "kr_name_input",
                    "placeholder": {"type": "plain_text", "text": "e.g., KR1: Increase user engagement"}
                }
            },
            {
                "type": "input",
                "block_id": "urgency",
                "label": {"type": "plain_text", "text": "Urgency Level"},
                "element": {
                    "type": "static_select",
                    "action_id": "urgency_input",
                    "placeholder": {"type": "plain_text", "text": "Select urgency level"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Low - Can wait a few days"}, "value": "Low"},
                        {"text": {"type": "plain_text", "text": "Medium - Need help this week"}, "value": "Medium"},
                        {"text": {"type": "plain_text", "text": "High - Blocking progress now"}, "value": "High"},
                        {"text": {"type": "plain_text", "text": "Critical - Blocking team/delivery"}, "value": "Critical"}
                    ]
                }
            },
            {
                "type": "input",
                "block_id": "notes",
                "label": {"type": "plain_text", "text": "Additional Notes (Optional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Any additional context or details..."}
                },
                "optional": True
            }
        ]
        
        bot.open_modal(
            trigger_id=trigger_id,
            title="Submit Blocker Details",
            blocks=blocks,
            submit_text="Submit Blocker",
            callback_id="blocker_details_submit"
        )
        
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling submit blocker details: {e}")
        return jsonify({"response_action": "clear"})

def handle_followup_response(bot, payload):
    """Handle followup response buttons."""
    try:
        action_id = payload['actions'][0]['action_id']
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        trigger_id = payload['trigger_id']
        
        if action_id == 'escalate_help':
            # User needs immediate help - send blocker form
            blocks = [
                {
                    "type": "input",
                    "block_id": "blocker_description",
                    "label": {"type": "plain_text", "text": "What's blocking you?"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "blocker_description_input",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "Describe the blocker in detail..."}
                    }
                },
                {
                    "type": "input",
                    "block_id": "kr_name",
                    "label": {"type": "plain_text", "text": "Key Result (KR) Name"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "kr_name_input",
                        "placeholder": {"type": "plain_text", "text": "e.g., KR1: Increase user engagement"}
                    }
                },
                {
                    "type": "input",
                    "block_id": "urgency",
                    "label": {"type": "plain_text", "text": "Urgency Level"},
                    "element": {
                        "type": "static_select",
                        "action_id": "urgency_input",
                        "placeholder": {"type": "plain_text", "text": "Select urgency level"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "Low - Can wait a few days"}, "value": "Low"},
                            {"text": {"type": "plain_text", "text": "Medium - Need help this week"}, "value": "Medium"},
                            {"text": {"type": "plain_text", "text": "High - Blocking progress now"}, "value": "High"},
                            {"text": {"type": "plain_text", "text": "Critical - Blocking team/delivery"}, "value": "Critical"}
                        ]
                    }
                },
                {
                    "type": "input",
                    "block_id": "notes",
                    "label": {"type": "plain_text", "text": "Additional Notes (Optional)"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "notes_input",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "Any additional context or details..."}
                    },
                    "optional": True
                }
            ]
            
            bot.open_modal(
                trigger_id=trigger_id,
                title="Submit Blocker Details",
                blocks=blocks,
                submit_text="Submit Blocker",
                callback_id="blocker_details_submit"
            )
            
        elif action_id == 'monitor_issue':
            # User can wait - acknowledge
            bot.send_dm(user_id, f"@{user_name} Thanks for letting us know. We'll check in with you later if needed.")
        
        return jsonify({"text": "OK"})
    except Exception as e:
        print(f"Error handling followup response: {e}")
        return jsonify({"text": "Error"})

def handle_health_share_response(bot, payload):
    """Handle health share response (public/private/no thanks) with background processing."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        action_id = payload['actions'][0]['action_id']
        
        # Get the stored mood
        mood = bot.health_responses.get(user_id, 'Unknown')
        
        if action_id == 'health_no_share':
            # User doesn't want to share - process in background
            bot.send_dm(user_id, "Thanks for the health check! Processing in background...")
            
            def process_no_share_in_background():
                try:
                    # Clear the stored mood
                    if hasattr(bot, 'health_responses'):
                        bot.health_responses.pop(user_id, None)
                    bot.send_dm(user_id, "Thanks for the health check! Take care! 💚")
                except Exception as e:
                    print(f"Error in background no share processing: {e}")
            
            import threading
            background_thread = threading.Thread(target=process_no_share_in_background)
            background_thread.daemon = True
            background_thread.start()
            
            return jsonify({"response_action": "clear"})
        
        elif action_id == 'health_share_private':
            # User wants to share privately - open a modal
            trigger_id = payload['trigger_id']
            
            blocks = [
                {
                    "type": "input",
                    "block_id": "private_share",
                    "label": {"type": "plain_text", "text": "What would you like to share?"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "private_share_input",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "Share your thoughts, feelings, or anything else..."}
                    }
                }
            ]
            
            bot.open_modal(
                trigger_id=trigger_id,
                title="Share Privately",
                blocks=blocks,
                submit_text="Share",
                callback_id="health_private_share_submit"
            )
            return jsonify({"response_action": "clear"})
        
        elif action_id == 'health_share_public':
            # User wants to share publicly - open a modal
            trigger_id = payload['trigger_id']
            
            blocks = [
                {
                    "type": "input",
                    "block_id": "public_share",
                    "label": {"type": "plain_text", "text": "What would you like to share publicly?"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "public_share_input",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "This will be saved to Coda and shared with your team..."}
                    }
                }
            ]
            
            bot.open_modal(
                trigger_id=trigger_id,
                title="Share Publicly",
                blocks=blocks,
                submit_text="Share",
                callback_id="health_public_share_submit"
            )
            return jsonify({"response_action": "clear"})
        
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling health share response: {e}")
        return jsonify({"text": "Error"})

def handle_blocker_details_submission(bot, payload):
    """Handle blocker details submission from help followup with duplicate prevention."""
    print(f"🔍 DEBUG: handle_blocker_details_submission called")
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Extract form data
        description = values.get('blocker_description', {}).get('blocker_description_input', {}).get('value', '')
        kr_name = values.get('kr_name', {}).get('kr_name_input', {}).get('value', '')
        urgency = values.get('urgency', {}).get('urgency_input', {}).get('selected_option', {}).get('value', 'Medium')
        notes = values.get('notes', {}).get('notes_input', {}).get('value', '')
        
        # Check for duplicate submission
        data_hash = f"{description[:50]}_{kr_name[:50]}_{urgency}_{notes[:50]}"
        if not track_submission(user_id, "blocker_details_submission", data_hash):
            bot.send_dm(user_id, "⚠️ This blocker details submission was already processed. Please wait a moment before trying again.")
            return jsonify({"response_action": "clear"})
        
        # Send immediate confirmation to user
        bot.send_dm(user_id, f"✅ Blocker details submitted! Processing in background...")
        
        # Run escalation in background thread to avoid blocking the form
        def escalate_in_background():
            try:
                bot.escalate_blocker_with_details(user_id, user_name, description, kr_name, urgency, notes)
                bot.send_dm(user_id, f"✅ Blocker details processed and escalated! Your team will be notified.")
            except Exception as escalation_error:
                print(f"Error in background escalation: {escalation_error}")
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your blocker details. Please try again or contact support.")
        
        # Start background thread
        import threading
        background_thread = threading.Thread(target=escalate_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        # Return proper Flask response
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling blocker details submission: {e}")
        return jsonify({"response_action": "clear"})

def handle_health_public_share_submission(bot, payload):
    """Handle health public share submission - saves to Coda with background processing."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Extract the share text
        share_text = values.get('public_share', {}).get('public_share_input', {}).get('value', '')
        mood = bot.health_responses.get(user_id, 'Unknown')
        
        # Send immediate confirmation
        bot.send_dm(user_id, "✅ Processing your public share in background...")
        
        # Process Coda saving in background thread
        def process_public_share_in_background():
            try:
                # Save to Coda if available
                if bot.coda:
                    try:
                        # Save health check sharing to After_Health_Check table
                        success = bot.coda.save_health_check_sharing(user_id, user_name, mood, share_text, is_public=True)
                        if success:
                            bot.send_dm(user_id, "✅ Your health check has been shared publicly and saved to Coda!")
                        else:
                            bot.send_dm(user_id, "⚠️ Your health check was shared publicly, but there was an issue saving to Coda.")
                    except Exception as e:
                        print(f"Error saving to Coda: {e}")
                        bot.send_dm(user_id, "⚠️ Your health check was shared publicly, but there was an issue saving to Coda.")
                else:
                    bot.send_dm(user_id, "✅ Your health check has been shared publicly!")
                
                # Clear the stored mood
                bot.health_responses.pop(user_id, None)
                
            except Exception as e:
                print(f"Error in background public share processing: {e}")
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your public share. Please try again.")
        
        # Start background thread
        import threading
        background_thread = threading.Thread(target=process_public_share_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        # Return proper Flask response immediately
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling health public share submission: {e}")
        return jsonify({"response_action": "clear"})

def handle_health_no_share(bot, payload):
    """Handle health check no share response with background processing."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        
        # Send immediate confirmation
        bot.send_dm(user_id, "✅ Processing your response in background...")
        
        # Process in background thread
        def process_no_share_in_background():
            try:
                # Clear the stored mood
                if hasattr(bot, 'health_responses'):
                    bot.health_responses.pop(user_id, None)
                
                # Send thank you message
                bot.send_dm(user_id, "✅ Thanks for your response! Take care! 💚")
                
            except Exception as e:
                print(f"Error in background no share processing: {e}")
        
        import threading
        background_thread = threading.Thread(target=process_no_share_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling health no share: {e}")
        return jsonify({"response_action": "clear"})

def handle_health_private_share_submission(bot, payload):
    """Handle health private share submission - saves to Coda as private with background processing."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Extract the share text
        share_text = values.get('private_share', {}).get('private_share_input', {}).get('value', '')
        mood = bot.health_responses.get(user_id, 'Unknown')
        
        # Send immediate confirmation
        bot.send_dm(user_id, "✅ Processing your private share in background...")
        
        # Process Coda saving in background thread
        def process_private_share_in_background():
            try:
                # Save to Coda if available (as private)
                if bot.coda:
                    try:
                        # Save health check sharing to After_Health_Check table as private
                        success = bot.coda.save_health_check_sharing(user_id, user_name, mood, share_text, is_public=False)
                        if success:
                            bot.send_dm(user_id, "✅ Thanks for sharing! Your thoughts have been saved privately. Take care! 💚")
                        else:
                            bot.send_dm(user_id, "✅ Thanks for sharing! Your thoughts are kept private. Take care! 💚")
                    except Exception as e:
                        print(f"Error saving to Coda: {e}")
                        bot.send_dm(user_id, "✅ Thanks for sharing! Your thoughts are kept private. Take care! 💚")
                else:
                    bot.send_dm(user_id, "✅ Thanks for sharing! Your thoughts are kept private. Take care! 💚")
                
                # Clear the stored mood
                bot.health_responses.pop(user_id, None)
                
            except Exception as e:
                print(f"Error in background private share processing: {e}")
                bot.send_dm(user_id, "❌ Sorry, there was an error processing your private share. Please try again.")
        
        # Start background thread
        import threading
        background_thread = threading.Thread(target=process_private_share_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        # Return proper Flask response immediately
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling health private share submission: {e}")
        return jsonify({"response_action": "clear"})

def handle_blocker_completion_submission(bot, payload):
    """Handle blocker completion form submission."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        
        # Extract the resolution notes
        resolution_notes = values.get('resolution_notes', {}).get('resolution_notes_input', {}).get('value', '')
        
        # Get the blocker ID from the modal's private metadata
        blocker_id = payload['view'].get('private_metadata', '')
        
        if not blocker_id:
            print(f"❌ No blocker ID found in modal metadata")
            bot.send_dm(user_id, "❌ Error: Could not identify which blocker to complete. Please try again.")
            return jsonify({"response_action": "clear"})
        
        print(f"🔍 DEBUG: Completing blocker {blocker_id} with resolution: {resolution_notes}")
        
        # Get blocker details from Coda
        if bot.coda:
            blocker_details = bot.coda.get_blocker_by_id(blocker_id)
            if blocker_details:
                kr_name = blocker_details.get('kr_name', 'Unknown KR')
                
                # Mark blocker as complete in Coda
                success = bot.coda.mark_blocker_complete(row_id=blocker_id, resolution_notes=resolution_notes)
                if success:
                    # Update KR status if we have the KR name
                    if kr_name and kr_name != 'Unknown KR':
                        try:
                            bot.coda.resolve_blocker_from_kr(
                                kr_name=kr_name,
                                resolved_by=user_name,
                                resolved_by_id=user_id,
                                resolution_notes=resolution_notes
                            )
                        except Exception as kr_error:
                            print(f"⚠️ Error updating KR status: {kr_error}")
                    
                    # Send completion notification to leads channel
                    try:
                        from datetime import datetime
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        completion_message = f"🎉 *Blocker Resolved* - @{user_name} has successfully resolved a blocker!"
                        completion_message += f"\n• *KR:* {kr_name}"
                        completion_message += f"\n• *Resolved by:* @{user_name}"
                        completion_message += f"\n• *Resolved at:* {current_time}"
                        completion_message += f"\n• *Resolution notes:* {resolution_notes}"
                        completion_message += f"\n• *Status:* KR status updated to 'Unblocked' in Coda"
                        
                        bot.send_completion_message_to_accessible_channel(completion_message)
                        print(f"✅ Sent completion message to leads channel")
                    except Exception as channel_error:
                        print(f"⚠️ Error sending completion message to channel: {channel_error}")
                    
                    # Send confirmation to user
                    bot.send_dm(user_id, f"✅ Blocker completed successfully!\n\n*Resolution:* {resolution_notes}\n\nThis has been saved to Coda and the KR status updated.")
                else:
                    bot.send_dm(user_id, "❌ Error: Failed to mark blocker as complete in Coda. Please try again.")
            else:
                bot.send_dm(user_id, "❌ Error: Could not find blocker details. Please try again.")
        else:
            bot.send_dm(user_id, f"✅ Blocker completion submitted! Resolution notes: {resolution_notes}")
        
        # Return proper Flask response
        from flask import jsonify
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling blocker completion submission: {e}")
        bot.send_dm(user_id, "❌ Error processing blocker completion. Please try again.")
        from flask import jsonify
        return jsonify({"response_action": "clear"})

def handle_blocker_resolution_submission(bot, payload):
    """Handle blocker resolution modal submission from /blockers command."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        values = payload['view']['state']['values']
        private_metadata = payload['view']['private_metadata']
        
        # Extract form data
        resolution_notes = values.get('resolution_notes', {}).get('resolution_notes_input', {}).get('value', '')
        
        # Parse private_metadata: blocker_row_id_kr_name
        parts = private_metadata.split('_')
        if len(parts) >= 2:
            blocker_row_id = parts[0]
            kr_name = '_'.join(parts[1:])  # KR name might contain underscores
            
            # Save to Coda
            if bot.coda:
                try:
                    # Mark blocker as complete
                    success = bot.coda.mark_blocker_complete(
                        row_id=blocker_row_id,
                        resolution_notes=resolution_notes
                    )
                    if success:
                        print(f"✅ Blocker resolution saved to Coda for {user_name}")
                        
                        # Send completion notification to leads channel
                        try:
                            from datetime import datetime
                            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            completion_message = f"🎉 *Blocker Resolved* - @{user_name} has successfully resolved a blocker!"
                            completion_message += f"\n• *KR:* {kr_name}"
                            completion_message += f"\n• *Resolved by:* @{user_name}"
                            completion_message += f"\n• *Resolved at:* {current_time}"
                            completion_message += f"\n• *Resolution notes:* {resolution_notes}"
                            completion_message += f"\n• *Status:* Blocker marked complete in Coda"
                            
                            bot.send_completion_message_to_accessible_channel(completion_message)
                            print(f"✅ Sent completion message to leads channel")
                        except Exception as channel_error:
                            print(f"⚠️ Error sending completion message to channel: {channel_error}")
                    else:
                        print(f"❌ Failed to save blocker resolution to Coda for {user_name}")
                    
                    # Update KR status
                    kr_success = bot.coda.resolve_blocker_from_kr(
                        kr_name=kr_name,
                        resolution_notes=resolution_notes
                    )
                    if kr_success:
                        print(f"✅ KR status updated to 'Unblocked' for {kr_name}")
                    else:
                        print(f"❌ Failed to update KR status for {kr_name}")
                        
                except Exception as e:
                    print(f"❌ Error saving blocker resolution to Coda: {e}")
            else:
                print(f"⚠️ Coda service not available - blocker resolution not saved")
            
            # Send confirmation DM
            confirmation_text = f"✅ Blocker resolved!\n\n"
            confirmation_text += f"*KR:* {kr_name}\n"
            confirmation_text += f"*Resolution Notes:* {resolution_notes}\n"
            confirmation_text += f"*Resolved by:* @{user_name}"
            
            bot.send_dm(user_id, confirmation_text)
        
        # Return proper Flask response
        from flask import jsonify
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"Error handling blocker resolution submission: {e}")
        from flask import jsonify
        return jsonify({"response_action": "clear"})

def handle_open_blocker_report_modal(bot, payload):
    """Handle opening the blocker report modal."""
    try:
        print(f"🔍 DEBUG: handle_open_blocker_report_modal called with payload: {payload}")
        
        # Get the correct user ID from the mentor check value in the button
        actions = payload.get('actions', [])
        if actions:
            value = actions[0].get('value', '')
            print(f"🔍 DEBUG: Button value: {value}")
            
            # Parse the value to get the actual user ID
            parts = value.split('_')
            if len(parts) >= 3 and parts[0] == 'checkin' and parts[1] == 'prompt':
                actual_user_id = parts[2]  # The user ID is the 3rd part
                print(f"🔍 DEBUG: Actual user ID from button value: {actual_user_id}")
            elif len(parts) >= 3 and parts[0] == 'blocker' and parts[1] == 'report':
                actual_user_id = parts[2]  # The user ID is the 3rd part
                print(f"🔍 DEBUG: Actual user ID from button value: {actual_user_id}")
            else:
                print(f"❌ DEBUG: Could not parse user ID from button value: {value}")
                return jsonify({"response_action": "clear"})
        else:
            print(f"❌ DEBUG: No actions found in payload")
            return jsonify({"response_action": "clear"})
        
        user_name = bot.get_user_name(actual_user_id)
        print(f"🔍 DEBUG: Creating blocker form for user: {user_name}")
        
        # Open a modal with the blocker form (same as checkin)
        trigger_id = payload.get('trigger_id')
        if not trigger_id:
            print(f"❌ DEBUG: No trigger_id available for modal")
            # Fallback to sending a simple message
            bot.send_dm(actual_user_id, f"🚨 Blocker Report for @{user_name}\n\nPlease use the `/blocked` command again to open the blocker form.")
            return jsonify({"response_action": "clear"})
        
        # Create modal blocks (same structure as checkin)
        modal_blocks = [
            {
                "type": "input",
                "block_id": "blocker_description",
                "label": {"type": "plain_text", "text": "What's blocking you?"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "blocker_description_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Describe the blocker in detail..."}
                }
            },
            {
                "type": "input",
                "block_id": "kr_name",
                "label": {"type": "plain_text", "text": "Key Result (KR) Name"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "kr_name_input",
                    "placeholder": {"type": "plain_text", "text": "e.g., KR1: Increase user engagement"}
                }
            },
            {
                "type": "input",
                "block_id": "urgency",
                "label": {"type": "plain_text", "text": "Urgency Level"},
                "element": {
                    "type": "static_select",
                    "action_id": "urgency_input",
                    "placeholder": {"type": "plain_text", "text": "Select urgency level"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Low - Can wait a few days"}, "value": "Low"},
                        {"text": {"type": "plain_text", "text": "Medium - Need help this week"}, "value": "Medium"},
                        {"text": {"type": "plain_text", "text": "High - Blocking progress now"}, "value": "High"},
                        {"text": {"type": "plain_text", "text": "Critical - Blocking team/delivery"}, "value": "Critical"}
                    ]
                }
            },
            {
                "type": "input",
                "block_id": "notes",
                "label": {"type": "plain_text", "text": "Additional Notes (Optional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Any additional context or details..."}
                },
                "optional": True
            }
        ]
        
        # Open the modal
        result = bot.open_modal(
            trigger_id=trigger_id,
            title="Submit Blocker Details",
            blocks=modal_blocks,
            submit_text="Submit Blocker",
            callback_id="blocker_details_submit"
        )
        print(f"🔍 DEBUG: Blocker modal opened: {result}")
        
        return jsonify({"response_action": "clear"})
        
    except Exception as e:
        print(f"❌ Error in handle_open_blocker_report_modal: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response_action": "clear"})

def handle_submit_blocker_form(bot, payload):
    """Handle submission of the blocker form from interactive blocks with duplicate prevention."""
    try:
        print(f"🔍 DEBUG: handle_submit_blocker_form called with payload: {payload}")
        
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        channel_id = payload['channel']['id']
        message_ts = payload['message']['ts']
        
        # Extract form data from the payload
        state = payload.get('state', {})
        values = state.get('values', {})
        
        # Extract the form fields
        kr_name = values.get('kr_name', {}).get('kr_name_input', {}).get('value', '')
        blocker_description = values.get('blocker_description', {}).get('blocker_description_input', {}).get('value', '')
        urgency = values.get('urgency', {}).get('urgency_select', {}).get('selected_option', {}).get('value', 'medium')
        notes = values.get('notes', {}).get('notes_input', {}).get('value', '')
        
        print(f"🔍 DEBUG: Form data - KR: {kr_name}, Description: {blocker_description}, Urgency: {urgency}, Notes: {notes}")
        
        if not kr_name or not blocker_description:
            # Send error message
            error_message = "❌ Please fill in both KR Name and Description fields."
            bot.update_message(channel_id, message_ts, error_message)
            return jsonify({"response_action": "clear"})
        
        # Check for duplicate submission
        data_hash = f"{blocker_description[:50]}_{kr_name[:50]}_{urgency}_{notes[:50]}"
        if not track_submission(user_id, "submit_blocker_form", data_hash):
            bot.update_message(channel_id, message_ts, "⚠️ This blocker submission was already processed. Please wait a moment before trying again.")
            return jsonify({"response_action": "clear"})
        
        # Update the message with immediate confirmation
        immediate_message = f"✅ *Blocker Report Submitted!*\n\n*KR:* {kr_name}\n*Description:* {blocker_description}\n*Urgency:* {urgency.title()}\n*Notes:* {notes if notes else 'None'}\n\nProcessing in background..."
        bot.update_message(channel_id, message_ts, immediate_message)
        
        # Process the blocker submission in background thread
        def escalate_in_background():
            try:
                bot.escalate_blocker_with_details(
                    user_id=user_id,
                    user_name=user_name,
                    blocker_description=blocker_description,
                    kr_name=kr_name,
                    urgency=urgency,
                    notes=notes
                )
                
                # Update the message with success
                success_message = f"✅ *Blocker Report Processed Successfully!*\n\n*KR:* {kr_name}\n*Description:* {blocker_description}\n*Urgency:* {urgency.title()}\n*Notes:* {notes if notes else 'None'}\n\nYour blocker has been escalated to your team leads."
                bot.update_message(channel_id, message_ts, success_message)
                
                print(f"✅ Blocker form submitted successfully for {user_name}")
                
            except Exception as e:
                print(f"❌ Error processing blocker submission: {e}")
                error_message = "❌ Sorry, there was an error processing your blocker. Please try again or contact your team lead directly."
                bot.update_message(channel_id, message_ts, error_message)
        
        # Start background thread
        import threading
        background_thread = threading.Thread(target=escalate_in_background)
        background_thread.daemon = True
        background_thread.start()
        
        return jsonify({"response_action": "clear"})
        
    except Exception as e:
        print(f"❌ Error in handle_submit_blocker_form: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response_action": "clear"})

def handle_open_blocker_modal_channel(bot, payload):
    """Handle opening the blocker modal from the public channel."""
    try:
        print(f"🔍 DEBUG: handle_open_blocker_modal_channel called with payload: {payload}")
        
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        
        # Get the user ID from the button value
        actions = payload.get('actions', [])
        if actions:
            value = actions[0].get('value', '')
            print(f"🔍 DEBUG: Button value: {value}")
            
            parts = value.split('_')
            if len(parts) >= 3 and parts[0] == 'blocker' and parts[1] == 'modal':
                actual_user_id = parts[2]
                print(f"🔍 DEBUG: Actual user ID from button value: {actual_user_id}")
            else:
                print(f"❌ DEBUG: Could not parse user ID from button value: {value}")
                return jsonify({"response_action": "clear"})
        else:
            print(f"❌ DEBUG: No actions found in payload")
            return jsonify({"response_action": "clear"})
        
        # Check if trigger_id exists (should exist in public channel)
        trigger_id = payload.get('trigger_id')
        print(f"🔍 DEBUG: trigger_id: {trigger_id}")
        
        if not trigger_id:
            print(f"❌ DEBUG: No trigger_id found in channel payload")
            return jsonify({"response_action": "clear"})
        
        # Create modal for blocker report
        blocks = [
            {
                "type": "input",
                "block_id": "kr_name",
                "label": {"type": "plain_text", "text": "Which KR is this blocker related to?"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "kr_name_input",
                    "placeholder": {"type": "plain_text", "text": "e.g., Implement user authentication"}
                }
            },
            {
                "type": "input",
                "block_id": "blocker_description",
                "label": {"type": "plain_text", "text": "Describe the blocker:"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "blocker_description_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "What's blocking your progress?"}
                }
            },
            {
                "type": "input",
                "block_id": "urgency",
                "label": {"type": "plain_text", "text": "Urgency level:"},
                "element": {
                    "type": "static_select",
                    "action_id": "urgency_select",
                    "placeholder": {"type": "plain_text", "text": "Select urgency"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Low"}, "value": "low"},
                        {"text": {"type": "plain_text", "text": "Medium"}, "value": "medium"},
                        {"text": {"type": "plain_text", "text": "High"}, "value": "high"},
                        {"text": {"type": "plain_text", "text": "Critical"}, "value": "critical"}
                    ]
                }
            },
            {
                "type": "input",
                "block_id": "notes",
                "label": {"type": "plain_text", "text": "Additional notes (optional):"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Any additional context..."}
                },
                "optional": True
            }
        ]
        
        # Open modal
        modal_result = bot.open_modal(
            trigger_id=trigger_id,
            title="Report Blocker",
            blocks=blocks,
            submit_text="Submit Blocker Report",
            callback_id="blocker_report_submit"
        )
        
        if modal_result:
            print(f"✅ DEBUG: Blocker report modal opened successfully from channel")
        else:
            print(f"❌ DEBUG: Failed to open blocker report modal from channel")
        
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"❌ Error in handle_open_blocker_modal_channel: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response_action": "clear"})

def handle_open_checkin_modal(bot, payload):
    """Handle opening the checkin modal from the DM."""
    try:
        print(f"🔍 DEBUG: handle_open_checkin_modal called with payload: {payload}")
        
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        
        # Get the user ID from the button value
        actions = payload.get('actions', [])
        if actions:
            value = actions[0].get('value', '')
            print(f"🔍 DEBUG: Button value: {value}")
            
            parts = value.split('_')
            if len(parts) >= 3 and parts[0] == 'open' and parts[1] == 'checkin':
                actual_user_id = parts[2]
                print(f"🔍 DEBUG: Actual user ID from button value: {actual_user_id}")
            else:
                print(f"❌ DEBUG: Could not parse user ID from button value: {value}")
                return jsonify({"response_action": "clear"})
        else:
            print(f"❌ DEBUG: No actions found in payload")
            return jsonify({"response_action": "clear"})
        
        # Check if trigger_id exists
        trigger_id = payload.get('trigger_id')
        print(f"🔍 DEBUG: trigger_id: {trigger_id}")
        
        if not trigger_id:
            print(f"❌ DEBUG: No trigger_id found in payload")
            return jsonify({"response_action": "clear"})
        
        # Use the bot's open_checkin_modal method
        success = bot.open_checkin_modal(trigger_id, user_id)
        
        if success:
            print(f"✅ DEBUG: Checkin modal opened successfully")
        else:
            print(f"❌ DEBUG: Failed to open checkin modal")
        
        return jsonify({"response_action": "clear"})
    except Exception as e:
        print(f"❌ Error in handle_open_checkin_modal: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"response_action": "clear"})

def handle_checkin_no_blocker(bot, payload):
    """Handle when user clicks 'No Blocker to Report' after check-in prompt."""
    try:
        user_id = payload['user']['id']
        user_name = bot.get_user_name(user_id)
        
        # Send acknowledgment message
        bot.send_dm(user_id, "✅ Understood! No blocker to report. If you encounter any issues later, feel free to use `/blocked` to report them.")
        
        return jsonify({"text": "OK"})
        
    except Exception as e:
        print(f"Error handling checkin no blocker: {e}")
        return jsonify({"text": "OK"})

def handle_blocker_sprint_modal_submission(bot, payload):
    """Handle blocker sprint modal submission - show user's blockers filtered by sprint."""
    try:
        import threading
        
        def process_blocker_sprint_command():
            try:
                user_id = payload['user']['id']
                user_name = bot.get_user_name(user_id)
                values = payload['view']['state']['values']
                
                # Extract sprint number from form
                sprint_input = values.get('sprint_input', {}).get('sprint_number', {})
                sprint_number = sprint_input.get('value', '').strip()
                
                print(f"🔍 DEBUG: Processing blocker sprint command for user {user_name}, sprint: '{sprint_number}'")
                
                # Get user's blockers filtered by sprint
                try:
                    blockers = bot.coda.get_user_blockers_by_sprint(user_id, sprint_number if sprint_number else None)
                    print(f"🔍 DEBUG: Blockers fetched: {len(blockers)} blockers")
                    
                    if not blockers:
                        sprint_text = f" in Sprint {sprint_number}" if sprint_number else ""
                        bot.send_dm(user_id, f"You have no active blockers{sprint_text}.")
                        return
                    
                    # Create blocks for each blocker
                    blocks = []
                    sprint_text = f" (Sprint {sprint_number})" if sprint_number else ""
                    
                    for idx, blocker in enumerate(blockers, 1):
                        block_text = f"*Blocker {idx}:{sprint_text}\\n*KR:* {blocker['kr_name']}\\n*Description:* {blocker['blocker_description']}\\n*Urgency:* {blocker['urgency']}\\n*Notes:* {blocker['notes']}"
                        blocks.append({
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": block_text},
                            "block_id": f"blocker_{blocker['row_id']}"
                        })
                        blocks.append({
                            "type": "actions",
                            "block_id": f"actions_{blocker['row_id']}",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Add/Edit Note"},
                                    "action_id": "edit_blocker_note",
                                    "value": blocker['row_id']
                                },
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Update Progress"},
                                    "action_id": "update_progress",
                                    "value": f"blocker_{blocker['row_id']}_{blocker['kr_name']}"
                                },
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Mark Resolved"},
                                    "style": "primary",
                                    "action_id": "mark_resolved",
                                    "value": f"blocker_{blocker['row_id']}_{blocker['kr_name']}"
                                }
                            ]
                        })
                    
                    sprint_header = f" (Sprint {sprint_number})" if sprint_number else ""
                    print(f"🔍 DEBUG: Sending blocker list with blocks: {len(blocks)} blocks")
                    bot.send_dm(user_id, f"Here are your current blockers{sprint_header}:", blocks=blocks)
                    
                except Exception as e:
                    print(f"❌ Error getting blockers: {e}")
                    bot.send_dm(user_id, "❌ Error retrieving your blockers. Please try again.")
                        
            except Exception as e:
                print(f"❌ Error in background blocker sprint processing: {e}")
                bot.send_dm(user_id, "❌ Error processing blocker command. Please try again.")
        
        thread = threading.Thread(target=process_blocker_sprint_command)
        thread.daemon = True
        thread.start()
        
        return jsonify({"response_action": "clear"})
        
    except Exception as e:
        print(f"❌ Error in blocker sprint modal submission handler: {e}")
        return jsonify({"response_action": "clear"})

def handle_view_all_blockers(bot, payload):
    """Handle 'View All Blockers' button click."""
    try:
        import threading
        
        def process_view_all_blockers():
            try:
                user_id = payload['user']['id']
                user_name = bot.get_user_name(user_id)
                
                print(f"🔍 DEBUG: Processing view all blockers for user {user_name}")
                
                # Get user's blockers (no sprint filter)
                try:
                    blockers = bot.coda.get_user_blockers_by_sprint(user_id, None)
                    print(f"🔍 DEBUG: Blockers fetched: {len(blockers)} blockers")
                    
                    if not blockers:
                        bot.send_dm(user_id, "You have no active blockers.")
                        return
                    
                    # Create blocks for each blocker
                    blocks = []
                    for idx, blocker in enumerate(blockers, 1):
                        block_text = f"*Blocker {idx}:\\n*KR:* {blocker['kr_name']}\\n*Description:* {blocker['blocker_description']}\\n*Urgency:* {blocker['urgency']}\\n*Notes:* {blocker['notes']}"
                        blocks.append({
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": block_text},
                            "block_id": f"blocker_{blocker['row_id']}"
                        })
                        blocks.append({
                            "type": "actions",
                            "block_id": f"actions_{blocker['row_id']}",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Add/Edit Note"},
                                    "action_id": "edit_blocker_note",
                                    "value": blocker['row_id']
                                },
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Update Progress"},
                                    "action_id": "update_progress",
                                    "value": f"blocker_{blocker['row_id']}_{blocker['kr_name']}"
                                },
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Mark Resolved"},
                                    "style": "primary",
                                    "action_id": "mark_resolved",
                                    "value": f"blocker_{blocker['row_id']}_{blocker['kr_name']}"
                                }
                            ]
                        })
                    
                    print(f"🔍 DEBUG: Sending blocker list with blocks: {len(blocks)} blocks")
                    bot.send_dm(user_id, "Here are your current blockers:", blocks=blocks)
                    
                except Exception as e:
                    print(f"❌ Error getting blockers: {e}")
                    bot.send_dm(user_id, "❌ Error retrieving your blockers. Please try again.")
                        
            except Exception as e:
                print(f"❌ Error in background view all blockers processing: {e}")
                bot.send_dm(user_id, "❌ Error processing blocker command. Please try again.")
        
        thread = threading.Thread(target=process_view_all_blockers)
        thread.daemon = True
        thread.start()
        
        return jsonify({"text": "OK"})
        
    except Exception as e:
        print(f"❌ Error in view all blockers handler: {e}")
        return jsonify({"text": "OK"})

def handle_open_blocker_sprint_modal(bot, payload):
    """Handle 'Filter by Sprint' button click - open modal to get sprint number."""
    try:
        trigger_id = payload.get('trigger_id')
        if not trigger_id:
            print(f"❌ DEBUG: No trigger_id found in payload")
            return jsonify({"text": "OK"})
        
        # Create modal blocks for sprint input
        blocks = [
            {
                "type": "input",
                "block_id": "sprint_input",
                "label": {
                    "type": "plain_text",
                    "text": "Sprint Number"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "sprint_number",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g., 8, 9, 10"
                    }
                },
                "optional": True
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Enter a sprint number to filter blockers, or leave empty to see all blockers"
                    }
                ]
            }
        ]
        
        # Open modal to get sprint number
        success = bot.open_modal(
            trigger_id=trigger_id,
            title="View Blockers by Sprint",
            blocks=blocks,
            submit_text="View Blockers",
            callback_id="blocker_sprint_modal"
        )
        
        if success:
            print(f"✅ DEBUG: Blocker sprint modal opened successfully")
        else:
            print(f"❌ DEBUG: Failed to open blocker sprint modal")
        
        return jsonify({"text": "OK"})
        
    except Exception as e:
        print(f"❌ Error in open blocker sprint modal handler: {e}")
        return jsonify({"text": "OK"})