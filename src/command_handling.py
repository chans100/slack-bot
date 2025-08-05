import time
import threading
from slack_sdk.errors import SlackApiError


class CommandHandler:
    """Handles slash commands and interactive commands."""
    
    def __init__(self, bot):
        self.bot = bot
    
    def handle_commands(self, user_id, text, channel_id):
        """Main command handler that routes to specific command processors."""
        try:
            # Parse the command
            parts = text.strip().split()
            if not parts:
                return
            
            command = parts[0].lower()
            
            # Route to appropriate handler
            if command == '/kr':
                self._process_kr_command(user_id, text, channel_id)
            elif command == '/checkin':
                self._process_checkin_command(user_id, text, channel_id)
            elif command == '/blocked':
                self._process_blocked_command(user_id, text, channel_id)
            elif command == '/health':
                self._process_health_command(user_id, text, channel_id)
            elif command == '/role':
                self._process_role_command(user_id, text, channel_id)
            elif command == '/rolelist':
                self._process_rolelist_command(user_id, text, channel_id)
            elif command == '/help':
                self._process_help_command(user_id, text, channel_id)
            else:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text=f"❌ Unknown command: {command}. Use `/help` to see available commands."
                )
                
        except Exception as e:
            print(f"Error handling command: {e}")
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=f"❌ Error processing command: {str(e)}"
            )
    
    def _process_kr_command(self, user_id, text, channel_id):
        """Process KR search command."""
        try:
            # Respond immediately and process in background to avoid timeout
            def process_kr_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Parse search term
                    parts = text.strip().split()
                    if len(parts) < 2:
                        self.bot.client.chat_postMessage(
                            channel=user_id,
                            text="❌ Usage: `/kr [search term]`"
                        )
                        return
                    
                    search_term = ' '.join(parts[1:])
                    
                    # Check if user has reached out to mentor
                    self.bot.send_mentor_check(user_id, None, "Unknown", "kr", user_id, search_term)
                    
                except Exception as e:
                    print(f"❌ Error in background KR processing: {e}")
            
            thread = threading.Thread(target=process_kr_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing KR search... Check your DM for results."
            
            return {
                "response_type": "ephemeral",
                "text": response_text
            }
            
        except Exception as e:
            print(f"❌ Error in KR command handler: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error processing KR command: {str(e)}"
            }
    
    def _process_checkin_command(self, user_id, text, channel_id):
        """Process checkin command."""
        try:
            # Respond immediately and process in background to avoid timeout
            def process_checkin_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Send standup prompt to user
                    self.bot.send_standup_to_dm(user_id)
                    
                except Exception as e:
                    print(f"❌ Error in background checkin processing: {e}")
            
            thread = threading.Thread(target=process_checkin_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing checkin request... Check your DM for the standup prompt."
            
            return {
                "response_type": "ephemeral",
                "text": response_text
            }
            
        except Exception as e:
            print(f"❌ Error in checkin command handler: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error processing checkin command: {str(e)}"
            }
    
    def _process_blocked_command(self, user_id, text, channel_id):
        """Process blocked command."""
        try:
            # Respond immediately and process in background to avoid timeout
            def process_blocked_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Get user info
                    user_info = self.bot.client.users_info(user=user_id)
                    username = user_info['user']['real_name']
                    
                    # Check if user has reached out to mentor
                    self.bot.send_mentor_check(user_id, None, username, "blocker", user_id)
                    
                except Exception as e:
                    print(f"❌ Error in background blocked processing: {e}")
            
            thread = threading.Thread(target=process_blocked_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing blocked request... Check your DM for the blocker form."
            
            return {
                "response_type": "ephemeral",
                "text": response_text
            }
            
        except Exception as e:
            print(f"❌ Error in blocked command handler: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error processing blocked command: {str(e)}"
            }
    
    def _process_health_command(self, user_id, text, channel_id):
        """Process health command."""
        try:
            # Respond immediately and process in background to avoid timeout
            def process_health_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Send health check to user
                    self.bot.send_health_check_to_dm(user_id)
                    
                except Exception as e:
                    print(f"❌ Error in background health processing: {e}")
            
            thread = threading.Thread(target=process_health_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing health check request... Check your DM for the health check."
            
            return {
                "response_type": "ephemeral",
                "text": response_text
            }
            
        except Exception as e:
            print(f"❌ Error in health command handler: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error processing health command: {str(e)}"
            }
    
    def _process_role_command(self, user_id, text, channel_id):
        """Process role command."""
        try:
            # Check if user has admin role
            if not self.bot.has_role(user_id, 'admin'):
                return {
                    "response_type": "ephemeral",
                    "text": "❌ You need admin privileges to manage roles."
                }
            
            # Respond immediately and process in background to avoid timeout
            def process_role_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Handle role command
                    self.bot._handle_role_command(user_id, text, user_id)
                    
                except Exception as e:
                    print(f"❌ Error in background role processing: {e}")
            
            thread = threading.Thread(target=process_role_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing role command... Check your DM for results."
            
            return {
                "response_type": "ephemeral",
                "text": response_text
            }
            
        except Exception as e:
            print(f"❌ Error in role command handler: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error processing role command: {str(e)}"
            }
    
    def _process_rolelist_command(self, user_id, text, channel_id):
        """Process rolelist command."""
        try:
            # Check if user has admin role
            if not self.bot.has_role(user_id, 'admin'):
                return {
                    "response_type": "ephemeral",
                    "text": "❌ You need admin privileges to view role lists."
                }
            
            # Respond immediately and process in background to avoid timeout
            def process_rolelist_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Get all users and their roles
                    all_users = self.bot.get_slack_user_list()
                    role_summary = {}
                    
                    for user_id in all_users:
                        try:
                            user_info = self.bot.client.users_info(user=user_id)
                            user_name = user_info['user']['real_name']
                            user_roles = self.bot.get_user_roles(user_id)
                            
                            if user_roles:
                                for role in user_roles:
                                    if role not in role_summary:
                                        role_summary[role] = []
                                    role_summary[role].append(f"• {user_name} (<@{user_id}>)")
                        except Exception as e:
                            print(f"❌ Error getting user info for {user_id}: {e}")
                            continue
                    
                    # Create summary message
                    summary_text = "📋 *Role Summary:*\n\n"
                    
                    if role_summary:
                        for role, users in sorted(role_summary.items()):
                            summary_text += f"**{role.title()}** ({len(users)} users):\n"
                            summary_text += "\n".join(users) + "\n\n"
                    else:
                        summary_text += "No users have assigned roles.\n\n"
                    
                    summary_text += "💡 Use `/role add @user role` to assign roles."
                    
                    # Send to user's DM
                    self.bot.client.chat_postMessage(
                        channel=user_id,
                        text=summary_text
                    )
                    
                except Exception as e:
                    print(f"❌ Error in background rolelist processing: {e}")
            
            thread = threading.Thread(target=process_rolelist_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing role list... Check your DM for results."
            
            return {
                "response_type": "ephemeral",
                "text": response_text
            }
            
        except Exception as e:
            print(f"❌ Error in rolelist command handler: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error processing rolelist command: {str(e)}"
            }
    
    def _process_help_command(self, user_id, text, channel_id):
        """Process help command."""
        try:
            # Respond immediately and process in background to avoid timeout
            def process_help_command():
                try:
                    # Add a small delay to avoid rate limiting
                    time.sleep(1.0)
                    
                    # Send help info directly to the user's DM
                    try:
                        print(f"🔍 DEBUG: Sending help info to user DM: {user_id}")
                        if text.strip().lower() == 'admin':
                            if self.bot.has_role(user_id, 'admin'):
                                self.bot.send_info_message(user_id, user_id, mode="admin")
                            else:
                                self.bot.client.chat_postMessage(
                                    channel=user_id,
                                    text="❌ You need admin privileges to view admin/role management commands."
                                )
                        else:
                            self.bot.send_info_message(user_id, user_id, mode="user")
                        print(f"✅ Help information sent successfully to DM")
                    except Exception as e:
                        print(f"❌ Error sending help information to DM: {e}")
                        import traceback
                        traceback.print_exc()
                except Exception as e:
                    print(f"❌ Error in background help processing: {e}")
            
            thread = threading.Thread(target=process_help_command)
            thread.daemon = True
            thread.start()
            
            response_text = "Processing help request... Check your DM for help information."
            
            return {
                "response_type": "ephemeral",
                "text": response_text
            }
            
        except Exception as e:
            print(f"❌ Error in help command handler: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error processing help command: {str(e)}"
            }
    
    def send_info_message(self, channel_id, user_id, mode="user"):
        """Send help/info message to user."""
        try:
            if mode == "user":
                help_text = "🤖 *Slack Bot Commands*\n\n"
                help_text += "**Available Commands:**\n"
                help_text += "• `/kr [search term]` - Search for Key Results\n"
                help_text += "• `/checkin` - Get a standup prompt\n"
                help_text += "• `/blocked` - Report a blocker\n"
                help_text += "• `/health` - Get a health check\n"
                help_text += "• `/help` - Show this help message\n\n"
                help_text += "**Daily Features:**\n"
                help_text += "• Daily standup prompts at 9:00 AM\n"
                help_text += "• Health checks via DM\n"
                help_text += "• Blocker escalation and tracking\n"
                help_text += "• AI-powered response analysis\n\n"
                help_text += "💡 Need help? Contact your team lead or use `/blocked` to report issues."
                
            elif mode == "admin":
                help_text = "🔧 *Admin Commands*\n\n"
                help_text += "**Role Management:**\n"
                help_text += "• `/role list` - Show all available roles\n"
                help_text += "• `/role add @user role` - Add role to user\n"
                help_text += "• `/role remove @user role` - Remove role from user\n"
                help_text += "• `/role users role` - List users with specific role\n"
                help_text += "• `/role channels` - Show role-to-channel mappings\n"
                help_text += "• `/rolelist` - Show complete role summary\n\n"
                help_text += "**Available Roles:**\n"
                help_text += "• pm, lead, developer, designer, qa, devops, sm, admin\n\n"
                help_text += "**User Commands:**\n"
                help_text += "• `/kr [search term]` - Search for Key Results\n"
                help_text += "• `/checkin` - Get a standup prompt\n"
                help_text += "• `/blocked` - Report a blocker\n"
                help_text += "• `/health` - Get a health check\n\n"
                help_text += "💡 Use `/help` for user commands."
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=help_text
            )
            
        except SlackApiError as e:
            print(f"Error sending info message: {e.response['error']}")
    
    def generate_kr_explanation(self, kr_name, owner, status, definition_of_done=None):
        """Generate AI explanation for a KR."""
        try:
            explanation = f"This KR is currently {status.lower()}"
            if owner and owner != "Unknown":
                explanation += f" and is owned by {owner}"
            
            if definition_of_done:
                explanation += f". The definition of done includes: {definition_of_done[:100]}..."
            else:
                explanation += "."
            
            return explanation
            
        except Exception as e:
            print(f"Error generating KR explanation: {e}")
            return "Unable to generate explanation." 