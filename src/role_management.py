from slack_sdk.errors import SlackApiError


class RoleManager:
    """Manages user roles, permissions, and role-based functionality."""
    
    def __init__(self, bot):
        self.bot = bot
        # User roles mapping - can be loaded from Coda or config
        self.user_roles = {
            # Format: 'user_id': ['role1', 'role2']
            # Example roles: 'pm', 'lead', 'developer', 'designer', 'qa', 'devops', 'sm'
            'U0919MVQLLU': ['developer', 'lead', 'admin'],  # alexanderchan486
            'U0912DJRNSF': ['pm', 'admin'],  # bot admin
            # Add more users as needed
        }
        
        # Role-based channel mappings
        self.role_channels = {
            'pm': 'general',  # PMs get notified in general channel
            'lead': 'general',  # Leads get notified in general channel
            'developer': 'dev-team',  # Developers get notified in dev-team channel
            'designer': 'design-team',  # Designers get notified in design-team channel
            'qa': 'qa-team',  # QA gets notified in qa-team channel
            'devops': 'devops-team',  # DevOps gets notified in devops-team channel
            'sm': 'general',  # Scrum Masters get notified in general channel
            'admin': 'general'  # Admins get notified in general channel
        }
        
        # Role-based escalation hierarchy
        self.escalation_hierarchy = {
            'blocker': ['developer', 'lead', 'sm', 'pm'],  # Escalate blockers to dev -> lead -> sm -> pm
            'health_check': ['pm', 'admin'],  # Escalate health issues to pm -> admin
            'standup': ['pm', 'lead'],  # Escalate standup issues to pm -> lead
            'kr_issue': ['lead', 'pm']  # Escalate KR issues to lead -> pm
        }
    
    def get_user_roles(self, user_id):
        """Get roles for a specific user."""
        return self.user_roles.get(user_id, [])
    
    def get_users_by_role(self, role):
        """Get all users with a specific role."""
        users = []
        for user_id, roles in self.user_roles.items():
            if role in roles:
                users.append(user_id)
        return users
    
    def has_role(self, user_id, role):
        """Check if a user has a specific role."""
        return role in self.user_roles.get(user_id, [])
    
    def send_role_based_message(self, role, message, channel_override=None):
        """Send a message to all users with a specific role."""
        try:
            users_with_role = self.get_users_by_role(role)
            if not users_with_role:
                print(f"⚠️ No users found with role: {role}")
                return False
            
            # Determine target channel
            target_channel = channel_override or self.role_channels.get(role, 'general')
            
            # Send message to the appropriate channel
            self.bot.client.chat_postMessage(
                channel=f"#{target_channel}",
                text=f"📢 *Message for {role.title()}s:*\n\n{message}"
            )
            
            print(f"✅ Role-based message sent to {len(users_with_role)} {role}s in #{target_channel}")
            return True
            
        except SlackApiError as e:
            print(f"Error sending role-based message: {e.response['error']}")
            return False
    
    def escalate_by_hierarchy(self, issue_type, message, additional_context=""):
        """Escalate an issue through the role hierarchy."""
        try:
            if issue_type not in self.escalation_hierarchy:
                print(f"⚠️ Unknown issue type: {issue_type}")
                return False
            
            hierarchy = self.escalation_hierarchy[issue_type]
            escalation_message = f"🚨 *{issue_type.title()} Escalation*\n\n{message}"
            
            if additional_context:
                escalation_message += f"\n\n*Additional Context:*\n{additional_context}"
            
            # Send to each role in the hierarchy
            for role in hierarchy:
                self.send_role_based_message(role, escalation_message)
            
            print(f"✅ Issue escalated through hierarchy: {hierarchy}")
            return True
            
        except Exception as e:
            print(f"Error escalating by hierarchy: {e}")
            return False
    
    def get_kr_assignees(self, kr_name):
        """Get users assigned to a specific KR based on their roles."""
        try:
            # This would typically query Coda or another system
            # For now, return users with 'developer' role as default KR assignees
            return self.get_users_by_role('developer')
        except Exception as e:
            print(f"Error getting KR assignees: {e}")
            return []
    
    def _handle_role_command(self, user_id, full_text, channel_id):
        """Handle role management commands."""
        try:
            # Parse the command
            parts = full_text.split()
            if len(parts) < 2:
                self._show_role_suggestions(channel_id)
                return
            
            command = parts[1].lower()
            
            if command == 'list':
                self._list_all_roles(channel_id)
            elif command == 'add':
                if len(parts) < 4:
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        text="❌ Usage: `/role add @user role_name`"
                    )
                    return
                user_mention = parts[2]
                role = parts[3].lower()
                self._add_user_role(user_mention, role, channel_id)
            elif command == 'remove':
                if len(parts) < 4:
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        text="❌ Usage: `/role remove @user role_name`"
                    )
                    return
                user_mention = parts[2]
                role = parts[3].lower()
                self._remove_user_role(user_mention, role, channel_id)
            elif command == 'users':
                if len(parts) < 3:
                    self.bot.client.chat_postMessage(
                        channel=channel_id,
                        text="❌ Usage: `/role users role_name`"
                    )
                    return
                role = parts[2].lower()
                self._list_users_by_role(role, channel_id)
            elif command == 'channels':
                self._list_role_channels(channel_id)
            else:
                self._show_role_suggestions(channel_id)
                
        except Exception as e:
            print(f"Error handling role command: {e}")
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=f"❌ Error processing role command: {str(e)}"
            )
    
    def _list_all_roles(self, channel_id):
        """List all available roles."""
        try:
            roles_text = "📋 *Available Roles:*\n\n"
            for role in sorted(self.role_channels.keys()):
                user_count = len(self.get_users_by_role(role))
                roles_text += f"• **{role.title()}** ({user_count} users)\n"
            
            roles_text += "\n💡 Use `/role users role_name` to see who has a specific role."
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=roles_text
            )
            
        except SlackApiError as e:
            print(f"Error listing roles: {e.response['error']}")
    
    def _add_user_role(self, user_mention, role, channel_id):
        """Add a role to a user."""
        try:
            # Extract user ID from mention
            if not user_mention.startswith('<@') or not user_mention.endswith('>'):
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text="❌ Please mention a user with @username"
                )
                return
            
            user_id = user_mention[2:-1]  # Remove <@ and >
            
            # Validate role
            if role not in self.role_channels:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text=f"❌ Invalid role: {role}. Use `/role list` to see available roles."
                )
                return
            
            # Add role to user
            if user_id not in self.user_roles:
                self.user_roles[user_id] = []
            
            if role in self.user_roles[user_id]:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text=f"ℹ️ {user_mention} already has the {role} role."
                )
                return
            
            self.user_roles[user_id].append(role)
            
            # Get user name for confirmation
            try:
                user_info = self.bot.client.users_info(user=user_id)
                user_name = user_info['user']['real_name']
            except:
                user_name = user_mention
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=f"✅ Added {role} role to {user_mention} ({user_name})"
            )
            
        except SlackApiError as e:
            print(f"Error adding user role: {e.response['error']}")
    
    def _remove_user_role(self, user_mention, role, channel_id):
        """Remove a role from a user."""
        try:
            # Extract user ID from mention
            if not user_mention.startswith('<@') or not user_mention.endswith('>'):
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text="❌ Please mention a user with @username"
                )
                return
            
            user_id = user_mention[2:-1]  # Remove <@ and >
            
            # Validate role
            if role not in self.role_channels:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text=f"❌ Invalid role: {role}. Use `/role list` to see available roles."
                )
                return
            
            # Remove role from user
            if user_id not in self.user_roles or role not in self.user_roles[user_id]:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text=f"ℹ️ {user_mention} doesn't have the {role} role."
                )
                return
            
            self.user_roles[user_id].remove(role)
            
            # Get user name for confirmation
            try:
                user_info = self.bot.client.users_info(user=user_id)
                user_name = user_info['user']['real_name']
            except:
                user_name = user_mention
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=f"✅ Removed {role} role from {user_mention} ({user_name})"
            )
            
        except SlackApiError as e:
            print(f"Error removing user role: {e.response['error']}")
    
    def _list_users_by_role(self, role, channel_id):
        """List all users with a specific role."""
        try:
            # Validate role
            if role not in self.role_channels:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text=f"❌ Invalid role: {role}. Use `/role list` to see available roles."
                )
                return
            
            users = self.get_users_by_role(role)
            
            if not users:
                self.bot.client.chat_postMessage(
                    channel=channel_id,
                    text=f"ℹ️ No users found with the {role} role."
                )
                return
            
            # Get user names
            user_list = []
            for user_id in users:
                try:
                    user_info = self.bot.client.users_info(user=user_id)
                    user_name = user_info['user']['real_name']
                    user_list.append(f"• <@{user_id}> ({user_name})")
                except:
                    user_list.append(f"• <@{user_id}> (Unknown)")
            
            users_text = f"👥 *Users with {role.title()} role:*\n\n"
            users_text += "\n".join(user_list)
            users_text += f"\n\nTotal: {len(users)} users"
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=users_text
            )
            
        except SlackApiError as e:
            print(f"Error listing users by role: {e.response['error']}")
    
    def _list_role_channels(self, channel_id):
        """List role-to-channel mappings."""
        try:
            channels_text = "📺 *Role Channel Mappings:*\n\n"
            for role, channel in self.role_channels.items():
                channels_text += f"• **{role.title()}** → #{channel}\n"
            
            channels_text += "\n💡 Messages for each role are sent to their designated channel."
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=channels_text
            )
            
        except SlackApiError as e:
            print(f"Error listing role channels: {e.response['error']}")
    
    def _show_role_suggestions(self, channel_id):
        """Show role command suggestions."""
        try:
            help_text = "🔧 *Role Management Commands:*\n\n"
            help_text += "• `/role list` - Show all available roles\n"
            help_text += "• `/role add @user role` - Add role to user\n"
            help_text += "• `/role remove @user role` - Remove role from user\n"
            help_text += "• `/role users role` - List users with specific role\n"
            help_text += "• `/role channels` - Show role-to-channel mappings\n\n"
            help_text += "💡 Example: `/role add @john developer`"
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                text=help_text
            )
            
        except SlackApiError as e:
            print(f"Error showing role suggestions: {e.response['error']}")
    
    def _show_interactive_role_selector(self, channel_id, user_mention, action_type):
        """Show interactive role selector with dropdown."""
        try:
            # Create role options
            role_options = []
            for role in sorted(self.role_channels.keys()):
                role_options.append({
                    "text": {
                        "type": "plain_text",
                        "text": role.title()
                    },
                    "value": f"{action_type}_{role}_{user_mention}"
                })
            
            message_blocks = [
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
                                "text": "Choose a role",
                                "emoji": True
                            },
                            "options": role_options,
                            "action_id": "role_selector"
                        }
                    ]
                }
            ]
            
            self.bot.client.chat_postMessage(
                channel=channel_id,
                blocks=message_blocks,
                text=f"Role selector for {user_mention}"
            )
            
        except SlackApiError as e:
            print(f"Error showing interactive role selector: {e.response['error']}") 