import json
import threading
import traceback
import time
from flask import jsonify, request
from .utils import logger, error_handler, input_validator, safe_executor

def _process_command(bot, user_id, command, text="", channel_id=None):
    """Process slash commands."""
    user_name = bot.get_user_name(user_id)
    print(f"Processing command '{command}' from user {user_name} ({user_id})")
    
    if command == 'help':
        return _handle_help_command(bot, user_id, channel_id)
    elif command == 'kr':
        return _handle_kr_command(bot, user_id, text, channel_id)
    elif command == 'checkin':
        return _handle_checkin_command(bot, user_id, channel_id)
    elif command == 'blocked':
        return _handle_blocked_command(bot, user_id, channel_id)
    elif command == 'health':
        return _handle_health_command(bot, user_id, channel_id)
    elif command == 'role':
        return _handle_role_command(bot, user_id, text, channel_id)
    elif command == 'rolelist':
        return _handle_rolelist_command(bot, user_id, channel_id)
    elif command == 'autorole':
        return _handle_autorole_command(bot, user_id, text, channel_id)
    elif command == 'test_standup':
        return _handle_test_standup_command(bot, user_id, channel_id)
    elif command == 'test_health':
        return _handle_test_health_command(bot, user_id, channel_id)
    elif command in ['blocker', 'blockers']:
        return _handle_blocker_command(bot, user_id, channel_id)
    else:
        print(f"Unknown command: {command}")
        return False

def _handle_help_command(bot, user_id, channel_id):
    """Handle /help command."""
    user_name = bot.get_user_name(user_id)
    
    # Create properly formatted help blocks
    help_blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🤖 Bot Commands Help",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Daily Workflow Commands:*"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "• `/checkin` — Start your daily standup\n• `/health` — Send a health check prompt\n• `/kr (sprint) (kr_name)` — Search for a Key Result in a specific sprint\n• `/blocked` — Report a new blocker\n• `/blocker` — View your current blockers"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Role Management Commands:*"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "• `/role` — Show role help and manage roles (includes auto-assignment)\n• `/rolelist` — List all roles and users"
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
                    "text": "💡 Use `/role` for detailed role management help"
                }
            ]
        }
    ]
    
    # Send as DM with blocks formatting
    bot.send_dm(user_id, "Here are all available commands:", blocks=help_blocks)
    return True

def _handle_kr_command(bot, user_id, text, channel_id):
    """Handle /kr command with sprint number requirement and field memory."""
    try:
        import threading
        def process_kr_command():
            try:
                time.sleep(1.0)
                try:
                    user_info = bot.client.users_info(user=user_id)
                    user_name = user_info['user']['real_name']
                except Exception as e:
                    print(f"❌ Error getting user info: {e}")
                    user_name = f"User {user_id}"
                
                # Check if user has pending KR data to continue
                if hasattr(bot, 'pending_kr_search') and user_id in bot.pending_kr_search:
                    pending_data = bot.pending_kr_search[user_id]
                    bot.send_kr_continue_form(user_id, user_name, pending_data)
                else:
                    # Parse command text for sprint number and KR name
                    parts = text.split() if text else []
                    sprint_number = None
                    search_term = None
                    
                    if parts:
                        # First part should be sprint number
                        try:
                            sprint_number = int(parts[0])
                            # Everything after sprint number is the KR search term
                            if len(parts) > 1:
                                search_term = ' '.join(parts[1:])
                        except ValueError:
                            # If first part isn't a number, show error
                            bot.send_dm(user_id, f"❌ *Invalid Format*\n\nPlease use the format: `/kr (sprint_number) (kr_name)`\n\n*Examples:*\n• `/kr 5` - Search for KRs in Sprint 5\n• `/kr 5 user engagement` - Search for 'user engagement' in Sprint 5\n• `/kr 3 performance` - Search for 'performance' in Sprint 3")
                            return
                    
                    # If no sprint number provided, ask for it
                    if not sprint_number:
                        bot.send_dm(user_id, f"❌ *Sprint Number Required*\n\nPlease use the format: `/kr (sprint_number) (kr_name)`\n\n*Examples:*\n• `/kr 5` - Search for KRs in Sprint 5\n• `/kr 5 user engagement` - Search for 'user engagement' in Sprint 5")
                        return
                    
                    # Always trigger mentor check, pass search_term and sprint_number if present
                    bot.send_mentor_check(
                        user_id=user_id,
                        standup_ts=None,  # No thread for slash commands
                        user_name=user_name,
                        request_type="kr",
                        channel=user_id,
                        search_term=search_term,
                        sprint_number=sprint_number
                    )
            except Exception as e:
                print(f"❌ Error in background KR processing: {e}")
        thread = threading.Thread(target=process_kr_command)
        thread.daemon = True
        thread.start()
        return True
    except Exception as e:
        print(f"❌ Error in KR command handler: {e}")
        return False

def _handle_checkin_command(bot, user_id, channel_id):
    """Handle /checkin command - send standup prompt to DM."""
    try:
        import threading
        def process_checkin_command():
            try:
                # Add a small delay to avoid rate limiting
                time.sleep(1.0)  # Increased delay for free workspace
                # Send standup with error handling
                try:
                    bot.send_standup_to_dm(user_id)
                    print(f"✅ Standup prompt sent successfully to {user_id}")
                except Exception as e:
                    print(f"❌ Error sending standup prompt: {e}")
                    # Don't try to send error message to avoid cascading failures
            except Exception as e:
                print(f"❌ Error in background checkin processing: {e}")
                # Don't try to send error message to avoid cascading failures
        thread = threading.Thread(target=process_checkin_command)
        thread.daemon = True
        thread.start()
        return True
    except Exception as e:
        print(f"❌ Error in checkin command handler: {e}")
        return False

def _handle_blocked_command(bot, user_id, channel_id):
    """Handle /blocked command - report a new blocker."""
    try:
        print(f"🔍 DEBUG: _handle_blocked_command called for user: {user_id}")
        
        import threading
        def process_blocked_command():
            try:
                # Add a small delay to avoid rate limiting
                time.sleep(1.0)  # Increased delay for free workspace
                
                # Get user info with error handling
                try:
                    user_info = bot.client.users_info(user=user_id)
                    user_name = user_info['user']['real_name']
                except Exception as e:
                    print(f"❌ Error getting user info: {e}")
                    user_name = f"User {user_id}"
                
                # Send mentor check for blocker reporting
                try:
                    print(f"🔍 DEBUG: About to call send_mentor_check for blocker reporting")
                    print(f"🔍 DEBUG: user_id: {user_id}, user_name: {user_name}, request_type: blocker")
                    
                    result = bot.send_mentor_check(
                        user_id=user_id,
                        standup_ts=None,
                        user_name=user_name,
                        request_type="blocker",
                        channel=user_id
                    )
                    
                    print(f"🔍 DEBUG: send_mentor_check result: {result}")
                    
                    if result:
                        print(f"✅ Mentor check sent successfully for blocker reporting to {user_name}")
                    else:
                        print(f"❌ Failed to send mentor check for blocker reporting to {user_name}")
                        
                except Exception as e:
                    print(f"❌ Error sending mentor check for blocker reporting: {e}")
                    import traceback
                    traceback.print_exc()
                    # Send a simple fallback message
                    bot.send_dm(user_id, "🚨 Need to report a blocker? Please try again or contact your team lead directly.")
                        
            except Exception as e:
                print(f"❌ Error in background blocked processing: {e}")
                # Don't try to send error message to avoid cascading failures
        
        thread = threading.Thread(target=process_blocked_command)
        thread.daemon = True
        thread.start()
        
        return True
    except Exception as e:
        print(f"❌ Error in blocked command handler: {e}")
        return False

def _handle_health_command(bot, user_id, channel_id):
    """Handle /health command - send health check to DM."""
    try:
        import threading
        def process_health_command():
            try:
                # Add a small delay to avoid rate limiting
                time.sleep(1.0)  # Increased delay for free workspace
                # Send health check with error handling
                try:
                    bot.send_health_check_to_dm(user_id)
                    print(f"✅ Health check prompt sent successfully to {user_id}")
                except Exception as e:
                    print(f"❌ Error sending health check prompt: {e}")
                    # Don't try to send error message to avoid cascading failures
            except Exception as e:
                print(f"❌ Error in background health processing: {e}")
                # Don't try to send error message to avoid cascading failures
        thread = threading.Thread(target=process_health_command)
        thread.daemon = True
        thread.start()
        return True
    except Exception as e:
        print(f"❌ Error in health command handler: {e}")
        return False

def _handle_role_command(bot, user_id, text, channel_id):
    """Handle /role command."""
    try:
        import threading
        def process_role_command():
            try:
                # Add a small delay to avoid rate limiting
                time.sleep(1.0)  # Increased delay for free workspace
                
                # Process role command directly to the user's DM
                try:
                    print(f"🔍 DEBUG: Processing role command to user DM: {user_id}")
                    bot._handle_role_command(user_id, text, user_id)  # Send to user's DM
                    print(f"✅ Role command processed successfully to DM")
                except Exception as e:
                    print(f"❌ Error processing role command to DM: {e}")
                    import traceback
                    traceback.print_exc()
                    # Don't try to send error message to avoid cascading failures
                    
            except Exception as e:
                print(f"❌ Error in background role processing: {e}")
                # Don't try to send error message to avoid cascading failures
        
        thread = threading.Thread(target=process_role_command)
        thread.daemon = True
        thread.start()
        
        return True
        
    except Exception as e:
        print(f"❌ Error in role command handler: {e}")
        return False

def _handle_rolelist_command(bot, user_id, channel_id):
    """Handle /rolelist command."""
    try:
        import threading
        def process_rolelist():
            try:
                # Add a small delay to avoid rate limiting
                time.sleep(1.0)  # Increased delay for free workspace
                
                # List roles directly to the user's DM
                try:
                    print(f"🔍 DEBUG: Listing roles to user DM: {user_id}")
                    bot._list_all_roles(user_id)  # Send to user's DM
                    print(f"✅ Role list processed successfully to DM")
                except Exception as e:
                    print(f"❌ Error listing roles to DM: {e}")
                    import traceback
                    traceback.print_exc()
                    # Don't try to send error message to avoid cascading failures
                    
            except Exception as e:
                print(f"❌ Error in background rolelist processing: {e}")
                # Don't try to send error message to avoid cascading failures
        
        thread = threading.Thread(target=process_rolelist)
        thread.daemon = True
        thread.start()
        
        return True
        
    except Exception as e:
        print(f"❌ Error in rolelist command handler: {e}")
        return False

def _handle_test_standup_command(bot, user_id, channel_id):
    """Handle /test_standup command - manually trigger daily standup."""
    user_name = bot.get_user_name(user_id)
    
    # Check if user has admin role
    if not bot.has_role(user_id, 'admin'):
        bot.send_dm(user_id, f"❌ @{user_name} Only admins can trigger test standups.")
        return False
    
    # Manually trigger the daily standup
    bot.send_standup_to_all_users()
    bot.send_dm(user_id, f"✅ @{user_name} Daily standup triggered manually!")
    return True

def _handle_test_health_command(bot, user_id, channel_id):
    """Handle /test_health command - manually trigger health check."""
    user_name = bot.get_user_name(user_id)
    
    # Check if user has admin role
    if not bot.has_role(user_id, 'admin'):
        bot.send_dm(user_id, f"❌ @{user_name} Only admins can trigger test health checks.")
        return False
    
    # Manually trigger the health check
    bot.send_health_check_to_all_users()
    bot.send_dm(user_id, f"✅ @{user_name} Health check triggered manually!")
    return True

def _handle_blocker_command(bot, user_id, channel_id):
    """Handle /blocker command with sprint number requirement and field memory."""
    try:
        import threading
        
        def process_blocker_command():
            try:
                # Add a small delay to avoid rate limiting
                time.sleep(1.0)
                
                # Get user info with error handling
                try:
                    user_info = bot.client.users_info(user=user_id)
                    user_name = user_info['user']['real_name']
                except Exception as e:
                    print(f"❌ Error getting user info: {e}")
                    user_name = f"User {user_id}"
                
                # Check if user has pending blocker data to continue
                if hasattr(bot, 'blocker_pending_data') and user_id in bot.blocker_pending_data:
                    pending_data = bot.blocker_pending_data[user_id]
                    bot.send_blocker_continue_form(user_id, user_name, pending_data)
                else:
                    # Send a message asking for sprint number
                    blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*View Your Blockers*\\n\\nPlease specify a sprint number to view your blockers:"
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "sprint_number",
                            "label": {
                                "type": "plain_text",
                                "text": "Sprint Number"
                            },
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "sprint_number_input",
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "e.g., 5"
                                }
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "View Blockers"
                                    },
                                    "action_id": "view_blockers_with_sprint",
                                    "value": user_id
                                }
                            ]
                        }
                    ]
                    
                    bot.send_dm(user_id, "Please provide a sprint number to view your blockers:", blocks=blocks)
                
            except Exception as e:
                print(f"❌ Error in background blocker processing: {e}")
                bot.send_dm(user_id, "❌ Error processing blocker command. Please try again.")
        
        thread = threading.Thread(target=process_blocker_command)
        thread.daemon = True
        thread.start()
        
        return True
    except Exception as e:
        print(f"❌ Error in blocker command handler: {e}")
        return False

def _handle_autorole_command(bot, user_id, text, channel_id):
    """Handle /autorole command - auto-assign roles to users."""
    try:
        import threading
        def process_autorole_command():
            try:
                # Add a small delay to avoid rate limiting
                time.sleep(1.0)
                
                # Get user info with error handling
                try:
                    user_info = bot.client.users_info(user=user_id)
                    user_name = user_info['user']['real_name']
                except Exception as e:
                    print(f"❌ Error getting user info: {e}")
                    user_name = f"User {user_id}"
                
                # Parse command arguments
                parts = text.split() if text else []
                
                if not parts:  # Just /autorole
                    bot.send_dm(user_id, "🔄 Starting auto-role assignment for all users...")
                    bot.auto_assign_roles()
                    bot.send_dm(user_id, "✅ Auto-role assignment completed!")
                    
                elif parts[0].lower() == 'refresh':
                    bot.send_dm(user_id, "🔄 Refreshing all user roles...")
                    bot.refresh_all_roles()
                    bot.send_dm(user_id, "✅ Role refresh completed!")
                    
                elif parts[0].lower() == 'new':
                    bot.send_dm(user_id, "🔄 Assigning roles to new users...")
                    bot.assign_roles_to_new_users()
                    bot.send_dm(user_id, "✅ New user role assignment completed!")
                    
                elif parts[0].lower() == 'user' and len(parts) >= 2:
                    user_mention = parts[1]
                    target_user_id = bot._extract_user_id_from_mention(user_mention)
                    
                    if target_user_id:
                        bot.send_dm(user_id, f"🔄 Auto-assigning roles to {user_mention}...")
                        bot.auto_assign_roles(user_id=target_user_id)
                        bot.send_dm(user_id, f"✅ Auto-role assignment completed for {user_mention}!")
                    else:
                        bot.send_dm(user_id, f"❌ Could not find user: {user_mention}")
                        
                else:
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
                            "type": "divider"
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": "💡 The bot analyzes job titles, departments, and Slack profile fields to automatically assign appropriate roles\n\n*Note:* Users need job titles in their Slack profiles for accurate role assignment"
                                }
                            ]
                        }
                    ]
                    bot.send_dm(user_id, "Auto-role assignment help:", blocks=autorole_blocks)
                        
            except Exception as e:
                print(f"❌ Error in background autorole processing: {e}")
                bot.send_dm(user_id, "❌ Error processing autorole command. Please try again.")
        
        thread = threading.Thread(target=process_autorole_command)
        thread.daemon = True
        thread.start()
        
        return True
    except Exception as e:
        print(f"❌ Error in autorole command handler: {e}")
        return False

def register_command_routes(app, bot):
    """Register command routes with comprehensive error handling."""
    
    # Track recent commands to prevent duplicates - make it accessible to the inner function
    recent_commands = {}
    
    @app.route('/slack/command', methods=['POST'])
    def handle_slash_commands():
        """Handle slash commands with comprehensive error handling."""
        nonlocal recent_commands  # Declare that we're using the outer scope variable
        
        try:
            print(f"🔍 DEBUG: handle_slash_commands called")
            
            # Validate request
            if not request.form:
                print(f"🔍 DEBUG: No form data found")
                return error_handler.handle_validation_error(
                    ValueError("Request must contain form data"),
                    "handle_slash_commands"
                )
            
            # Extract command data
            user_id = request.form.get('user_id')
            command = request.form.get('command', '').lstrip('/')
            text = request.form.get('text', '').strip()
            channel_id = request.form.get('channel_id')
            
            print(f"🔍 DEBUG: Command data - user_id: {user_id}, command: {command}, text: {text}")
            
            # Validate required fields
            if not user_id:
                print(f"🔍 DEBUG: No user_id found")
                return error_handler.handle_validation_error(
                    ValueError("User ID is required"),
                    "handle_slash_commands"
                )
            
            if not command:
                print(f"🔍 DEBUG: No command found")
                return error_handler.handle_validation_error(
                    ValueError("Command is required"),
                    "handle_slash_commands",
                    user_id=user_id
                )
            
            # Validate user ID format
            if not input_validator.validate_user_id(user_id):
                print(f"🔍 DEBUG: Invalid user_id format: {user_id}")
                return error_handler.handle_validation_error(
                    ValueError(f"Invalid user ID format: {user_id}"),
                    "handle_slash_commands",
                    user_id=user_id
                )
            
            # Validate channel ID if provided
            if channel_id and not input_validator.validate_channel_id(channel_id):
                print(f"🔍 DEBUG: Invalid channel_id format: {channel_id}")
                return error_handler.handle_validation_error(
                    ValueError(f"Invalid channel ID format: {channel_id}"),
                    "handle_slash_commands",
                    user_id=user_id,
                    additional_data={'channel_id': channel_id}
                )
            
            # Sanitize text input
            sanitized_text = input_validator.sanitize_text(text)
            
            # Check for duplicate commands (within 5 seconds)
            import time
            current_time = time.time()
            command_key = f"{user_id}_{command}_{sanitized_text}"
            
            if command_key in recent_commands:
                last_time = recent_commands[command_key]
                if current_time - last_time < 5:  # 5 second window
                    print(f"🔍 DEBUG: Duplicate command detected and ignored: {command_key}")
                    return jsonify({
                        "response_type": "ephemeral",
                        "text": "Command already being processed. Please wait a moment."
                    })
            
            # Store this command
            recent_commands[command_key] = current_time
            
            # Clean up old entries (older than 10 seconds)
            cleanup_time = current_time - 10
            recent_commands = {k: v for k, v in recent_commands.items() if v > cleanup_time}
            
            logger.info(f"Processing command '{command}' from user {user_id} with text: '{sanitized_text}'")
            
            print(f"🔍 DEBUG: About to call _process_command")
            
            # Process command
            result = _process_command(bot, user_id, command, sanitized_text, channel_id)
            
            print(f"🔍 DEBUG: _process_command returned: {result}")
            
            if result:
                return jsonify({
                    "response_type": "ephemeral",
                    "text": "Command processed successfully"
                })
            else:
                return error_handler.handle_validation_error(
                    ValueError(f"Unknown or failed command: {command}"),
                    "handle_slash_commands",
                    user_id=user_id,
                    additional_data={'command': command, 'text': sanitized_text}
                )
                
        except Exception as e:
            print(f"🔍 DEBUG: Exception caught in handle_slash_commands: {str(e)}")
            import traceback
            print(f"🔍 DEBUG: Full traceback: {traceback.format_exc()}")
            return error_handler.handle_unexpected_error(
                e, "handle_slash_commands"
            ) 