from datetime import datetime
from slack_sdk.errors import SlackApiError


class StandupManager:
    """Manages daily standup functionality including prompts, responses, and follow-ups."""
    
    def __init__(self, bot):
        self.bot = bot
    
    def send_daily_standup(self):
        """Send the daily standup prompt message with hybrid interaction options."""
        try:
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🌅 *Good morning team! Time for the daily standup!*\n\n"
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
                                   f"<!channel> please respond by {self.bot.config.RESPONSE_DEADLINE}. Let's stay aligned! 💬"
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
            
            response = self.bot.client.chat_postMessage(
                channel=self.bot.channel_id,
                blocks=message["blocks"],
                text="Daily Standup - React for quick status or reply in thread for details"
            )
            
            # Track this standup
            self.bot.active_standups[response['ts']] = {
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
            if standup_key in self.bot.standup_responses:
                print(f"⚠️ User {user_id} has already submitted a standup response today (quick reaction)")
                # Send a polite message informing them they've already responded
                self.bot.client.chat_postMessage(
                    channel=self.bot.channel_id,
                    thread_ts=standup_ts,
                    text=f"<@{user_id}>, you've already submitted your standup response for today! Thanks for staying on top of it! ✅"
                )
                return
            
            # Get user info
            user_info = self.bot.client.users_info(user=user_id)
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
            if standup_ts not in self.bot.active_standups:
                self.bot.active_standups[standup_ts] = {'responses': {}, 'quick_responses': {}}
            
            self.bot.active_standups[standup_ts]['quick_responses'][user_id] = {
                'status': status_info['status'],
                'reaction': reaction,
                'timestamp': datetime.now(),
                'user_name': user_name
            }
            
            # Mark user as having submitted standup response today
            self.bot.standup_responses.add(standup_key)
            print(f"✅ User {user_id} marked as having submitted standup response for {today} (quick reaction)")
            
            # Respond based on status
            if status_info['status'] == 'needs_help':
                # Send detailed follow-up for help requests
                self.bot.send_help_followup(user_id, standup_ts, user_name)
            else:
                # Acknowledge quick status
                self.bot.client.chat_postMessage(
                    channel=self.bot.channel_id,
                    thread_ts=standup_ts,
                    text=f"<@{user_id}>: {status_info['message']}"
                )
                
        except SlackApiError as e:
            print(f"Error handling quick reaction: {e.response['error']}")
    
    def parse_standup_response(self, text):
        """Parse standup response text: 1st line = today, 2nd = on_track, 3rd = blockers."""
        lines = [l.strip().lower() for l in text.strip().split('\n') if l.strip()]
        parsed = {
            'today': lines[0] if len(lines) > 0 else '',
            'on_track': lines[1] if len(lines) > 1 else '',
            'blockers': lines[2] if len(lines) > 2 else ''
        }
        return parsed

    def handle_standup_response(self, user_id, message_ts, thread_ts, text, channel_id=None):
        """Handle standup response in thread."""
        try:
            print(f"🔍 DEBUG: Processing standup response from user {user_id}")
            print(f"🔍 DEBUG: Message text: {text[:100]}...")
            print(f"🔍 DEBUG: Channel ID: {channel_id}")
            
            # Check if this specific message has already been processed
            if message_ts in self.bot.processed_events:
                print(f"⚠️ Message {message_ts} already processed, skipping")
                return
            
            # Check if user has already submitted a standup response today
            today = datetime.now().strftime('%Y-%m-%d')
            standup_key = f"{user_id}_{today}"
            if standup_key in self.bot.standup_responses:
                print(f"⚠️ User {user_id} has already submitted a standup response today")
                # Send a polite message informing them they've already responded
                target_channel = channel_id or self.bot.channel_id
                self.bot.client.chat_postMessage(
                    channel=target_channel,
                    thread_ts=thread_ts,
                    text=f"<@{user_id}>, you've already submitted your standup response for today! Thanks for staying on top of it! ✅"
                )
                return
            
            # Get user info
            user_info = self.bot.client.users_info(user=user_id)
            user_name = user_info['user']['real_name']
            print(f"🔍 DEBUG: User name: {user_name}")
            
            # Parse the response
            parsed_data = self.parse_standup_response(text)
            print(f"🔍 DEBUG: Parsed data: {parsed_data}")
            
            # Generate AI-powered analysis of the standup response
            ai_analysis = ""
            try:
                from mistral_service import MistralService
                mistral = MistralService()
                analysis_result = mistral.analyze_standup_response(text)
                if analysis_result and isinstance(analysis_result, dict):
                    sentiment = analysis_result.get('sentiment', 'neutral')
                    urgency = analysis_result.get('urgency', 'medium')
                    suggestions = analysis_result.get('suggestions', [])
                    key_points = analysis_result.get('key_points', [])
                    
                    # Create AI analysis text
                    sentiment_emoji = {'positive': '😊', 'neutral': '😐', 'negative': '😟'}.get(sentiment, '😐')
                    urgency_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(urgency, '🟡')
                    
                    ai_analysis = f"\n\n🤖 *AI Analysis:*\n• Sentiment: {sentiment_emoji} {sentiment.title()}\n• Urgency: {urgency_emoji} {urgency.title()}"
                    
                    if suggestions:
                        ai_analysis += f"\n• Suggestions: {'; '.join(suggestions[:2])}"
                    
                    if key_points:
                        ai_analysis += f"\n• Key Points: {'; '.join(key_points[:2])}"
                    
                    print(f"🔍 DEBUG: AI Analysis - Sentiment: {sentiment}, Urgency: {urgency}")
            except Exception as ai_error:
                print(f"⚠️ Error generating AI analysis: {ai_error}")
                ai_analysis = ""
            
            # Store response in Coda
            success = False
            
            # Try Coda (standup table)
            if self.bot.coda and self.bot.coda.standup_table_id:
                try:
                    success = self.bot.coda.add_standup_response(
                        user_id=user_id,
                        response_text=text,
                        username=user_name
                    )
                    if success:
                        print("✅ Standup response stored in Coda successfully")
                except Exception as e:
                    print(f"❌ Error storing response in Coda: {e}")
            else:
                print("⚠️ Standup table ID not configured - skipping Coda storage")
            
            if not success:
                print("❌ Failed to store response in Coda")
                # Don't fail the request - just log the issue
                success = True  # Mark as success to continue processing
            
            # Mark this message as processed
            self.bot.processed_events.add(message_ts)
            
            # Mark user as having submitted standup response today
            today = datetime.now().strftime('%Y-%m-%d')
            standup_key = f"{user_id}_{today}"
            self.bot.standup_responses.add(standup_key)
            print(f"✅ User {user_id} marked as having submitted standup response for {today}")
            print("✅ Message marked as processed")
            
            # Check if user needs follow-up with more flexible parsing
            on_track_text = parsed_data.get('on_track', '').lower()
            blockers_text = parsed_data.get('blockers', '').lower()
            
            # More comprehensive detection for not being on track
            not_on_track_phrases = [
                'no', 'not on track', 'not on', 'behind', 'off track', 'off', 
                'not track', 'not meeting', 'not going well', 'struggling',
                'falling behind', 'behind schedule', 'delayed', 'late'
            ]
            not_on_track = any(phrase in on_track_text for phrase in not_on_track_phrases)
            
            # More comprehensive detection for blockers
            blocker_phrases = [
                'yes', 'blocker', 'blocked', 'stuck', 'issue', 'problem', 'yes i have',
                'have blocker', 'need help', 'help', 'trouble', 'difficulty',
                'challenge', 'obstacle', 'impediment', 'barrier'
            ]
            has_blockers = any(phrase in blockers_text for phrase in blocker_phrases)
            
            needs_followup = not_on_track or has_blockers
            
            print(f"🔍 DEBUG: on_track_text: '{on_track_text}', blockers_text: '{blockers_text}'")
            print(f"🔍 DEBUG: not_on_track: {not_on_track}, has_blockers: {has_blockers}")
            
            print(f"🔍 DEBUG: Needs followup: {needs_followup}")
            
            if needs_followup:
                # Check if we've already sent a followup to this user in this thread
                followup_key = f"followup_{user_id}_{thread_ts}"
                if followup_key not in self.bot.health_check_responses:
                    print(f"🔍 DEBUG: Sending followup message to {user_name}")
                    self.send_followup_message(user_id, thread_ts, parsed_data, channel_id, ai_analysis)
                else:
                    print(f"⚠️ Followup already sent to {user_id} in thread {thread_ts}")
            else:
                print(f"🔍 DEBUG: No followup needed for {user_name}")
                # Send acknowledgment to the correct channel with AI analysis
                target_channel = channel_id or self.bot.channel_id
                acknowledgment_text = f"Thanks <@{user_id}> for your standup update! ✅{ai_analysis}"
                self.bot.client.chat_postMessage(
                    channel=target_channel,
                    thread_ts=thread_ts,
                    text=acknowledgment_text
                )
                
        except SlackApiError as e:
            print(f"Error handling standup response: {e.response['error']}")
        except Exception as e:
            print(f"Unexpected error in handle_standup_response: {e}")
            import traceback
            traceback.print_exc()

    def send_followup_message(self, user_id, thread_ts, parsed_data, channel_id=None, ai_analysis=""):
        """Send follow-up message for users who need help."""
        try:
            # Check if we've already sent a followup to this user in this thread
            followup_key = f"followup_{user_id}_{thread_ts}"
            if followup_key in self.bot.health_check_responses:
                print(f"⚠️ Already sent followup to {user_id} in thread {thread_ts}")
                return
            
            # Mark that we've sent a followup
            self.bot.health_check_responses.add(followup_key)
            
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
            target_channel = channel_id or self.bot.channel_id
            
            response = self.bot.client.chat_postMessage(
                channel=target_channel,
                thread_ts=thread_ts,
                blocks=message["blocks"],
                text=f"Follow-up for <@{user_id}> - React for help options"
            )
            
            # Mark followup as sent
            followup_key = f"followup_{user_id}_{thread_ts}"
            self.bot.health_check_responses.add(followup_key)
            print(f"✅ Followup message marked as sent: {response['ts']}")
            
            # Store user data for button handling
            self.bot.user_responses[user_id] = {
                'followup_ts': response['ts'],
                'thread_ts': thread_ts,
                'parsed_data': parsed_data,
                'user_name': self.bot.client.users_info(user=user_id)['user']['real_name']
            }
            
        except SlackApiError as e:
            print(f"Error sending followup message: {e.response['error']}")
    
    def send_standup_to_dm(self, user_id):
        """Send standup prompt to a specific user via DM."""
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
                            "text": f"🌅 *Good morning {user_name}! Time for your daily standup!*\n\n"
                                   "Please provide your update:\n\n"
                                   "• **Today:** What did you work on?\n"
                                   "• **On Track:** Are you on track with your goals? (Yes/No)\n"
                                   "• **Blockers:** Do you have any blockers? (Yes/No)\n\n"
                                   f"Please respond by {self.bot.config.RESPONSE_DEADLINE}. Let's stay aligned! 💬"
                        }
                    }
                ]
            }
            
            response = self.bot.client.chat_postMessage(
                channel=dm_channel,
                blocks=message["blocks"],
                text=f"Daily Standup for {user_name}"
            )
            
            print(f"✅ Standup sent to {user_name} ({user_id})")
            return response['ts']
            
        except SlackApiError as e:
            print(f"Error sending standup to DM: {e.response['error']}")
            return None
    
    def escalate_issue(self, user_id, user_name, parsed_data):
        """Escalate issue based on parsed standup data."""
        try:
            escalation_message = f"🚨 *Issue Escalation*\n\n<@{user_id}> reported issues in standup:\n\n*Details:*\n• On Track: {parsed_data.get('on_track', 'Unknown')}\n• Blockers: {parsed_data.get('blockers', 'Unknown')}\n• Today's Work: {parsed_data.get('today', 'Not specified')}\n\nPlease check the standup thread and offer support."
            
            self.bot.client.chat_postMessage(
                channel=f"#{getattr(self.bot.config, 'SLACK_ESCALATION_CHANNEL', 'leads')}",
                text=escalation_message
            )
            
        except SlackApiError as e:
            print(f"Error escalating issue: {e.response['error']}") 