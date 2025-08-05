import time
from datetime import datetime
from slack_sdk.errors import SlackApiError


class EventHandler:
    """Handles Slack events and interactions."""
    
    def __init__(self, bot):
        self.bot = bot
    
    def handle_reaction(self, user_id, message_ts, reaction):
        """Handle reactions to follow-up messages."""
        try:
            # Find the user data for this message
            user_data = None
            for uid, data in self.bot.user_responses.items():
                if data.get('followup_ts') == message_ts:
                    user_data = data
                    break
            
            if not user_data:
                print(f"No user data found for message {message_ts}")
                return
            
            # Handle escalation reactions
            if reaction == 'sos':
                # Send message with button to open blocker form
                message = {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"<@{user_id}>, I see you need help! 🚨\n\n"
                                       "Let me help you get unblocked. Please click the button below to provide details:"
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Report Blocker",
                                        "emoji": True
                                    },
                                    "value": f"open_blocker_form_{user_id}",
                                    "action_id": "escalate_help"
                                }
                            ]
                        }
                    ]
                }
                
                response = self.bot.client.chat_postMessage(
                    channel=self.bot.channel_id,
                    thread_ts=user_data['thread_ts'],
                    blocks=message["blocks"],
                    text=f"<@{user_id}>, please click the button to report your blocker details."
                )
                print(f"✅ Blocker form button sent to {user_data['user_name']}")
                
            elif reaction == 'clock4':
                # Acknowledge monitoring
                self.bot.client.chat_postMessage(
                    channel=self.bot.channel_id,
                    thread_ts=user_data['thread_ts'],
                    text=f"Got it <@{user_id}>, we'll keep an eye on this. Please keep your mentor informed of any updates! 🚧"
                )
                # Clean up
                del self.bot.user_responses[user_id]
                
        except SlackApiError as e:
            print(f"Error handling reaction: {e.response['error']}")
    
    def handle_button_click(self, payload):
        """Handle button click interactions."""
        trigger_id = payload.get('trigger_id')  # Ensure trigger_id is always available
        try:
            print("Received button click payload:", payload)
            user = payload['user']['id']
            username = payload['user'].get('name', payload['user'].get('username', 'Unknown'))
            
            # Handle different action types
            action_data = payload['actions'][0]
            action_id = action_data['action_id']
            
            # Get action value safely (not all actions have 'value')
            action = action_data.get('value', '')
            
            message_ts = payload['message']['ts']
            channel_id = payload['channel']['id']
            print(f"User {username} ({user}) clicked {action_id} with value: {action}")
            
            # Handle health check buttons
            if action_id in ['great', 'okay', 'not_great']:
                return self._handle_health_check_response(user, username, action, message_ts, channel_id)
            
            # Handle mentor response
            elif action_id in ['mentor_response_yes', 'mentor_response_no']:
                return self._handle_mentor_response(user, username, action_id, action, message_ts, channel_id)
            
            # Handle blocker form submission
            elif action_id == 'submit_blocker_details':
                return self._handle_blocker_form_submission(payload)
            
            # Handle role selector dropdown
            elif action_id == 'role_selector':
                return self._handle_role_selector(user, username, action_data, message_ts, channel_id)
            
            # Handle follow-up buttons
            elif action_id in ['escalate_help', 'monitor_issue']:
                return self._handle_followup_buttons(user, username, action_id, message_ts, channel_id)
            
            # Handle explanation submission
            elif action_id == 'submit_explanation':
                return self._handle_explanation_submission(user, username, action, payload)
            
            # Handle skip explanation
            elif action_id == 'skip_explanation':
                return self._handle_skip_explanation(user, message_ts, channel_id)
            
            # Handle public/private chat
            elif action_id in ['public_chat', 'private_chat']:
                return self._handle_chat_choice(user, username, action_id, action, payload)
            
            # Handle help offers
            elif action_id == 'offer_help':
                return self._handle_help_offer(user, username, action, payload)
            
            # Handle other buttons
            elif action_id in ['helped', 'mark_completed', 'refresh_status']:
                return self._handle_other_buttons(user, username, action_id, action, payload)
            
            else:
                print(f"❌ Unknown action_id: {action_id}")
                return {"response_action": "errors", "errors": ["Unknown action"]}, 400
                
        except Exception as e:
            print(f"❌ Error in handle_button_click: {e}")
            return {"response_action": "errors", "errors": ["Internal error"]}, 500
    
    def _handle_health_check_response(self, user, username, action, message_ts, channel_id):
        """Handle health check button responses."""
        try:
            # Check if user has already responded to this health check
            response_key = f"{user}_{message_ts}"
            if response_key in self.bot.health_check_responses:
                print(f"❌ User {username} already responded to health check")
                return {"response_action": "errors", "errors": ["User already responded"]}, 200
            
            # Store response and mark user as responded
            success = False
            
            # Try Coda first (primary storage)
            if self.bot.coda and self.bot.coda.main_table_id:
                try:
                    success = self.bot.coda.add_response(
                        user_id=user,
                        response=action,
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
                        "text": f"Thanks for your response! Could you tell us a bit more about why you're feeling {action.replace('_', ' ')} today?"
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
                            "value": f"public_{action}",
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
                            "value": f"private_{action}",
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
            
            return {"response_action": "clear"}, 200
            
        except SlackApiError as e:
            print(f"Error handling health check response: {e.response['error']}")
            return {"response_action": "errors", "errors": ["Slack API error"]}, 500
    
    def _handle_mentor_response(self, user, username, action_id, action, message_ts, channel_id):
        """Handle mentor response buttons."""
        try:
            # Extract mentor response and request type from action value
            mentor_response = "Yes" if action_id == 'mentor_response_yes' else "No"
            request_type = action.split('_')[-1] if '_' in action else "blocker"
            
            print(f"🔍 DEBUG: Mentor response received:")
            print(f"   - User: {username} ({user})")
            print(f"   - Response: {mentor_response}")
            print(f"   - Request Type: {request_type}")
            
            # Store mentor response in Coda
            success = False
            if self.bot.coda and self.bot.coda.mentor_table_id:
                try:
                    success = self.bot.coda.add_mentor_check(
                        user_id=user,
                        mentor_response=mentor_response,
                        request_type=request_type,
                        username=username
                    )
                    if success:
                        print(f"✅ Mentor response stored in Coda for {username}")
                except Exception as e:
                    print(f"❌ Error storing mentor response in Coda: {e}")
            
            if not success:
                print("❌ Failed to store mentor response in Coda")
            
            # Handle based on mentor response
            if mentor_response == "Yes":
                if request_type == "blocker":
                    self.bot.send_help_followup(
                        user_id=user,
                        standup_ts=message_ts,
                        user_name=username,
                        channel=channel_id
                    )
                    response_text = "Great! Let's get you the help you need. Please fill out the details above."
                elif request_type == "kr":
                    # Handle KR request
                    response_text = self._handle_kr_request(user, username, message_ts, channel_id)
                else:
                    response_text = "Great! Let's proceed with your request."
            else:
                # Use the new function for 'No' response
                self.bot.handle_mentor_no_response(user, channel_id, message_ts)
                return {"response_action": "clear"}, 200
            
            if response_text:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text=response_text
                )
            return {"response_action": "clear"}, 200
            
        except SlackApiError as e:
            print(f"Error handling mentor response: {e.response['error']}")
            return {"response_action": "errors", "errors": ["Slack API error"]}, 500
    
    def _handle_kr_request(self, user, username, message_ts, channel_id):
        """Handle KR request after mentor check."""
        try:
            # Check if a search term was provided
            search_term = None
            if hasattr(self.bot, 'pending_kr_search'):
                search_term = self.bot.pending_kr_search.get(user)
            
            if search_term:
                # Show KR search results
                matches = self.bot.coda.search_kr_table(search_term)
                if matches:
                    result_lines = []
                    for m in matches:
                        kr_name = m.get('c-yQ1M6UqTSj', 'N/A')
                        owner = m.get('c-efR-vVo_3w', 'N/A')
                        status = m.get('c-cC29Yow8Gr', 'N/A')
                        definition_of_done = m.get('c-P_mQJLObL0', '')
                        link = m.get('link', None)
                        explanation = self.bot.generate_kr_explanation(kr_name, owner, status, definition_of_done)
                        line = f"*KR*: {kr_name}\n*Owner*: {owner}\n*Status*: {status}\n*Definition of Done*: {definition_of_done}\n*AI Explanation*: {explanation}"
                        if link:
                            line += f"\n<Link|{link}>"
                        result_lines.append(line)
                    result_text = '\n\n'.join(result_lines)
                else:
                    result_text = f'No matching KRs found for "{search_term}".'
                
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text=result_text
                )
                self.bot.pending_kr_search[user] = None
                return None  # Already sent results
            else:
                # No search term provided, prompt for KR
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text="What KR would you like to search for? Please type `/kr [search term]` or `!kr [search term]`."
                )
                return None  # Already sent prompt
                
        except Exception as e:
            print(f"❌ Error handling KR request: {e}")
            return "Sorry, there was an error processing your KR request. Please try again."
    
    def _handle_blocker_form_submission(self, payload):
        """Handle blocker form submission from modal."""
        try:
            # Extract form data from the payload
            state = payload.get('view', {}).get('state', {})
            values = state.get('values', {})
            
            # Get blocker details from form
            blocker_description = values.get('blocker_description', {}).get('blocker_description_input', {}).get('value', '')
            kr_name = values.get('kr_name', {}).get('kr_name_input', {}).get('value', '')
            urgency = values.get('urgency', {}).get('urgency_input', {}).get('selected_option', {}).get('value', '')
            notes = values.get('notes', {}).get('notes_input', {}).get('value', '')
            
            # Get user info
            user = payload.get('user', {}).get('id', 'unknown')
            username = payload.get('user', {}).get('name', 'unknown')
            
            # Store in Coda
            success = False
            if self.bot.coda and self.bot.coda.blocker_table_id:
                try:
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
                except Exception as e:
                    print(f"❌ Error storing blocker in Coda: {e}")
            
            # Send confirmation and escalate
            if success:
                # Escalate with detailed information
                self.bot.escalate_blocker_with_details(user, username, blocker_description, kr_name, urgency, notes)
            
            return {"response_action": "clear"}, 200
            
        except Exception as e:
            print(f"❌ Error in handle_blocker_form_submission: {e}")
            return {"response_action": "clear"}, 200
    
    def _handle_role_selector(self, user, username, action_data, message_ts, channel_id):
        """Handle role selector dropdown."""
        try:
            # Parse the selected value: action_type_role_user_mention
            selected_value = action_data.get('selected_option', {}).get('value', '')
            if selected_value:
                parts = selected_value.split('_', 2)  # Split into max 3 parts
                if len(parts) >= 2:
                    action_type = parts[0]
                    role = parts[1]
                    user_mention = parts[2] if len(parts) > 2 else None
                    
                    print(f"🔍 DEBUG: Role selector selected:")
                    print(f"   - Action: {action_type}")
                    print(f"   - Role: {role}")
                    print(f"   - User: {user_mention}")
                    
                    # Execute the role action
                    if action_type == 'add' and user_mention:
                        self.bot._add_user_role(user_mention, role, channel_id)
                    elif action_type == 'remove' and user_mention:
                        self.bot._remove_user_role(user_mention, role, channel_id)
                    elif action_type == 'users':
                        self.bot._list_users_by_role(role, channel_id)
                    
                    # Update the message to show the action was completed
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"✅ Role action completed: {action_type} {role}"
                    )
            
            return {"response_action": "clear"}, 200
            
        except Exception as e:
            print(f"❌ Error handling role selector: {e}")
            return {"response_action": "errors", "errors": ["Role selector error"]}, 500
    
    def _handle_followup_buttons(self, user, username, action_id, message_ts, channel_id):
        """Handle follow-up buttons (escalate_help, monitor_issue)."""
        try:
            if action_id == 'escalate_help':
                # Open a modal with the blocker form
                try:
                    modal_view = {
                        "type": "modal",
                        "callback_id": "blocker_form",
                        "title": {
                            "type": "plain_text",
                            "text": "Report Blocker",
                            "emoji": True
                        },
                        "submit": {
                            "type": "plain_text",
                            "text": "Submit",
                            "emoji": True
                        },
                        "close": {
                            "type": "plain_text",
                            "text": "Cancel",
                            "emoji": True
                        },
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"<@{user}>, I see you need help! 🚨\n\n"
                                           "Let me help you get unblocked. Please provide the following information:"
                                }
                            },
                            {
                                "type": "input",
                                "block_id": "blocker_description",
                                "label": {
                                    "type": "plain_text",
                                    "text": "What's blocking you?",
                                    "emoji": True
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
                                    "text": "Key Result (KR) Name",
                                    "emoji": True
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
                                    "text": "Urgency Level",
                                    "emoji": True
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
                                    "text": "Additional Notes (Optional)",
                                    "emoji": True
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
                            }
                        ]
                    }
                    
                    # Open the modal
                    response = self.bot.client.views_open(
                        trigger_id=trigger_id,
                        view=modal_view
                    )
                    
                    print(f"✅ Blocker modal opened for {username}")
                    
                except SlackApiError as e:
                    print(f"Error opening blocker modal: {e.response['error']}")
                    # Fallback: send a simple message if modal fails
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"<@{user}>, I see you need help! Please contact your mentor or team lead directly. 🚨"
                    )
                
                return {"response_action": "clear"}, 200
                
            elif action_id == 'monitor_issue':
                # Handle "Can wait" button - acknowledge and clean up
                try:
                    # Send acknowledgment message
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=message_ts,
                        text=f"Got it <@{user}>, we'll keep an eye on this. Please keep your mentor informed of any updates! 🚧"
                    )
                    print(f"✅ 'Can wait' acknowledged for {username}")
                    return {"response_action": "clear"}, 200
                except Exception as e:
                    print(f"❌ Error handling 'Can wait' button: {e}")
                    return {"response_action": "errors", "errors": ["Error processing request"]}, 500
            else:
                print(f"❌ No user data found for {user}")
                return {"response_action": "errors", "errors": ["No user data found"]}, 400
                
        except Exception as e:
            print(f"❌ Error handling followup buttons: {e}")
            return {"response_action": "errors", "errors": ["Followup button error"]}, 500
    
    def _handle_explanation_submission(self, user, username, action, payload):
        """Handle explanation submission."""
        try:
            # Extract explanation from the input
            state = payload.get('state', {})
            values = state.get('values', {})
            explanation = values.get('health_check_explanation', {}).get('explanation_input', {}).get('value', '')
            
            # Extract the original health check response from the button value
            original_response = action.split('_', 1)[1] if '_' in action else 'unknown'
            
            # Save to After_Health_Check table
            success = False
            if self.bot.coda:
                try:
                    success = self.bot.coda.add_health_check_explanation(
                        user_id=user,
                        username=username,
                        health_check_response=original_response,
                        explanation=explanation
                    )
                    if success:
                        print(f"✅ Health check explanation stored in Coda for {username}")
                except Exception as e:
                    print(f"❌ Error storing health check explanation in Coda: {e}")
            
            # Send confirmation
            if success:
                self.bot.client.chat_postMessage(
                    channel=payload['channel']['id'],
                    thread_ts=payload['message']['ts'],
                    text=f"✅ Thanks <@{user}>! Your explanation has been recorded."
                )
            else:
                self.bot.client.chat_postMessage(
                    channel=payload['channel']['id'],
                    thread_ts=payload['message']['ts'],
                    text=f"❌ Sorry <@{user}>, there was an error saving your explanation. Please try again."
                )
            
            return {"response_action": "clear"}, 200
            
        except Exception as e:
            print(f"❌ Error handling explanation submission: {e}")
            return {"response_action": "errors", "errors": ["Explanation submission error"]}, 500
    
    def _handle_skip_explanation(self, user, message_ts, channel_id):
        """Handle skip explanation button."""
        try:
            self.bot.client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"👍 No problem <@{user}>! Thanks for your health check response."
            )
            return {"response_action": "clear"}, 200
            
        except SlackApiError as e:
            print(f"Error handling skip explanation: {e.response['error']}")
            return {"response_action": "errors", "errors": ["Skip explanation error"]}, 500
    
    def _handle_chat_choice(self, user, username, action_id, action, payload):
        """Handle public/private chat choice."""
        try:
            # Extract explanation from the input
            state = payload.get('state', {})
            values = state.get('values', {})
            explanation = values.get('health_check_explanation', {}).get('explanation_input', {}).get('value', '')
            
            # Extract the original health check response from the button value
            original_response = action.split('_', 1)[1] if '_' in action else 'unknown'
            
            if action_id == 'public_chat':
                # Save to After_Health_Check table
                success = False
                if self.bot.coda:
                    try:
                        success = self.bot.coda.add_health_check_explanation(
                            user_id=user,
                            username=username,
                            health_check_response=original_response,
                            explanation=explanation
                        )
                        if success:
                            print(f"✅ Public health check explanation stored in Coda for {username}")
                    except Exception as e:
                        print(f"❌ Error storing public health check explanation in Coda: {e}")
                
                # Send confirmation
                if success:
                    self.bot.client.chat_postMessage(
                        channel=payload['channel']['id'],
                        thread_ts=payload['message']['ts'],
                        text=f"✅ Thanks <@{user}>! Your explanation has been recorded and shared with the team."
                    )
                else:
                    self.bot.client.chat_postMessage(
                        channel=payload['channel']['id'],
                        thread_ts=payload['message']['ts'],
                        text=f"❌ Sorry <@{user}>, there was an error saving your explanation. Please try again."
                    )
                
            elif action_id == 'private_chat':
                # Send private response without saving to Coda
                if explanation.strip():
                    self.bot.client.chat_postMessage(
                        channel=payload['channel']['id'],
                        thread_ts=payload['message']['ts'],
                        text=f"🤫 <@{user}>, I understand. Your message is private and won't be shared with the team. If you need anything, feel free to reach out anytime!"
                    )
                else:
                    self.bot.client.chat_postMessage(
                        channel=payload['channel']['id'],
                        thread_ts=payload['message']['ts'],
                        text=f"🤫 <@{user}>, no worries! This conversation is private. If you need anything later, just let me know."
                    )
            
            return {"response_action": "clear"}, 200
            
        except Exception as e:
            print(f"❌ Error handling chat choice: {e}")
            return {"response_action": "errors", "errors": ["Chat choice error"]}, 500
    
    def _handle_help_offer(self, user, username, action, payload):
        """Handle help offer button."""
        try:
            # Check if help has already been offered for this message
            message_ts = payload['message']['ts']
            if message_ts in self.bot.help_offers:
                print(f"❌ Help already offered for message {message_ts}")
                return {"response_action": "errors", "errors": ["Help already offered"]}, 200
            
            # Extract the user who needs help from the button value
            # Button value format: "help_{user_id}"
            if action.startswith('help_'):
                help_needed_user_id = action.replace('help_', '')
                
                # Mark this message as having help offered
                self.bot.help_offers.add(message_ts)
                
                # Get the helper's name
                helper_info = self.bot.client.users_info(user=user)
                helper_name = helper_info['user']['real_name']
                
                # Get the person who needs help's name
                try:
                    help_needed_info = self.bot.client.users_info(user=help_needed_user_id)
                    help_needed_name = help_needed_info['user']['real_name']
                except:
                    help_needed_name = f"<@{help_needed_user_id}>"
                
                # Update the message to show who offered help
                updated_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"✅ *Blocker Resolved*\n\n<@{help_needed_user_id}> ({help_needed_name}) has been helped by <@{user}> ({helper_name})!\n\nIf you'd like to offer additional help, you can still reach out to <@{help_needed_user_id}> directly."
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ Helped",
                                    "emoji": True
                                },
                                "value": "helped",
                                "action_id": "helped",
                                "style": "primary",
                                "confirm": {
                                    "title": {
                                        "type": "plain_text",
                                        "text": "Already Helped"
                                    },
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": "This person has already been helped. The button is now disabled."
                                    },
                                    "confirm": {
                                        "type": "plain_text",
                                        "text": "OK"
                                    },
                                    "deny": {
                                        "type": "plain_text",
                                        "text": "Cancel"
                                    }
                                }
                            }
                        ]
                    }
                ]
                
                # Update the message
                try:
                    self.bot.client.chat_update(
                        channel=payload['channel']['id'],
                        ts=message_ts,
                        blocks=updated_blocks,
                        text=f"✅ {help_needed_name} has been helped by {helper_name}!"
                    )
                    print(f"✅ Help offered by {helper_name} to {help_needed_name}")
                except Exception as e:
                    print(f"❌ Error updating message: {e}")
                
                # Send DM to the person who needed help
                try:
                    dm_response = self.bot.client.conversations_open(users=[help_needed_user_id])
                    dm_channel = dm_response['channel']['id']
                    
                    self.bot.client.chat_postMessage(
                        channel=dm_channel,
                        text=f"🎉 Great news! <@{user}> ({helper_name}) has offered to help you with your blocker. They should be reaching out to you soon!"
                    )
                except Exception as e:
                    print(f"❌ Could not send DM to {help_needed_user_id}: {e}")
                
                return {"response_action": "clear"}, 200
            else:
                print(f"❌ Invalid help button value: {action}")
                return {"response_action": "errors", "errors": ["Invalid help request"]}, 400
                
        except Exception as e:
            print(f"❌ Error handling help offer: {e}")
            return {"response_action": "errors", "errors": ["Help offer error"]}, 500
    
    def _handle_other_buttons(self, user, username, action_id, action, payload):
        """Handle other buttons (helped, mark_completed, refresh_status)."""
        try:
            if action_id == 'helped':
                # This button is just for show - it's already been helped
                return {"response_action": "clear"}, 200
                
            elif action_id == 'mark_completed':
                # Extract KR name from button value (format: "complete_{kr_name}")
                if action.startswith('complete_'):
                    kr_name = action.replace('complete_', '')
                    
                    # Get KR information for display
                    if self.bot.coda:
                        try:
                            kr_info = self.bot.coda.get_kr_display_info(kr_name)
                            if kr_info:
                                # Display KR information without updating status
                                display_text = f"📊 *KR Information*\n\n*{kr_name}*\n"
                                display_text += f"• **Owner:** {kr_info.get('owner', 'Unknown')}\n"
                                display_text += f"• **Status:** {kr_info.get('status', 'Unknown')}\n"
                                display_text += f"• **Progress:** {kr_info.get('progress', 'Unknown')}%\n"
                                display_text += f"• **Objective:** {kr_info.get('objective', 'Unknown')}\n"
                                display_text += f"• **Sprint:** {kr_info.get('sprint', 'Unknown')}\n"
                                display_text += f"• **Predicted Hours:** {kr_info.get('predicted_hours', 'Unknown')}\n"
                                display_text += f"• **Urgency:** {kr_info.get('urgency', 'Unknown')}\n"
                                
                                if kr_info.get('notes'):
                                    display_text += f"• **Notes:** {kr_info.get('notes', '')[:100]}...\n"
                                
                                display_blocks = [
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": display_text
                                        }
                                    }
                                ]
                                
                                try:
                                    self.bot.client.chat_update(
                                        channel=payload['channel']['id'],
                                        ts=payload['message']['ts'],
                                        blocks=display_blocks,
                                        text=f"📊 KR Information: {kr_name}"
                                    )
                                    print(f"✅ KR '{kr_name}' information displayed")
                                except Exception as update_error:
                                    print(f"❌ Error updating display message: {update_error}")
                            else:
                                print(f"⚠️ Failed to get KR '{kr_name}' information from Coda")
                        except Exception as kr_error:
                            print(f"❌ Error getting KR information: {kr_error}")
                    
                    return {"response_action": "clear"}, 200
                else:
                    print(f"❌ Invalid completion button value: {action}")
                    return {"response_action": "errors", "errors": ["Invalid completion request"]}, 400
                    
            elif action_id == 'refresh_status':
                # Extract KR name from button value (format: "refresh_{kr_name}")
                if action.startswith('refresh_'):
                    safe_kr_name = action.replace('refresh_', '')
                    
                    # Get original KR name from mapping
                    kr_name = self.bot.kr_name_mappings.get(safe_kr_name, safe_kr_name)
                    
                    # Get current KR status from Coda
                    kr_status_info = "Unknown"
                    if self.bot.coda and kr_name and kr_name != "Unknown KR":
                        try:
                            kr_details = self.bot.coda.get_kr_details(kr_name)
                            if kr_details:
                                current_status = kr_details.get('status', 'Unknown')
                                current_helper = kr_details.get('helper', '')
                                if current_status and current_status != 'Unknown':
                                    if current_helper:
                                        kr_status_info = f"{current_status} (by {current_helper})"
                                    else:
                                        kr_status_info = current_status
                                else:
                                    kr_status_info = "In Progress"
                            else:
                                kr_status_info = "Not Found in KR Table"
                        except Exception as kr_error:
                            print(f"❌ Error fetching KR status: {kr_error}")
                            kr_status_info = "Error fetching status"
                    
                    # Send status update
                    self.bot._send_simple_status_update(
                        payload['channel']['id'],
                        payload['message']['ts'],
                        kr_name,
                        kr_status_info,
                        safe_kr_name
                    )
                    
                    return {"response_action": "clear"}, 200
                else:
                    print(f"❌ Invalid refresh button value: {action}")
                    return {"response_action": "errors", "errors": ["Invalid refresh request"]}, 400
            
            return {"response_action": "clear"}, 200
            
        except Exception as e:
            print(f"❌ Error handling other buttons: {e}")
            return {"response_action": "errors", "errors": ["Other button error"]}, 500 