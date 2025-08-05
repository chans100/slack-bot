import schedule
import time
from datetime import datetime, timedelta
from slack_sdk.errors import SlackApiError


class SchedulingManager:
    """Manages scheduling of daily tasks, reminders, and automated messages."""
    
    def __init__(self, bot):
        self.bot = bot
        self.setup_schedules()
    
    def setup_schedules(self):
        """Set up all scheduled tasks."""
        # Reset daily prompts at midnight
        schedule.every().day.at("00:00").do(self.reset_daily_prompts)
        
        # Schedule daily standup
        schedule.every().day.at(self.bot.config.STANDUP_TIME).do(self.send_standup_to_all_users)
        
        # Schedule reminder for missing responses
        schedule.every().day.at(self.bot.config.REMINDER_TIME).do(self.check_missing_responses)
        
        # Schedule daily health check
        schedule.every().day.at("09:00").do(self.send_health_check_to_all_users)
        
        # Schedule daily blocker digest at 15:30 (commented out for development)
        # schedule.every().day.at("15:30").do(self.send_daily_blocker_digest)
    
    def reset_daily_prompts(self):
        """Reset daily prompt tracking at midnight."""
        self.bot.daily_prompts_sent = {
            'standup': False,
            'health_check': False
        }
        print("✅ Daily prompts reset for new day")
    
    def check_missing_responses(self):
        """Check for missing responses and send reminders."""
        try:
            # Get current time
            now = datetime.now()
            
            # Check each active standup
            for standup_ts, standup_data in self.bot.active_standups.items():
                # Calculate time since standup
                time_since = now - standup_data['timestamp']
                
                # If more than 2 hours have passed, send reminder
                if time_since.total_seconds() > 7200:  # 2 hours
                    reminder_message = "⏰ *Reminder: Please respond to the daily standup!*\n\nIf you haven't already, please either:\n• React to the main message with your status\n• Reply in the thread with your detailed update\n\nYour input helps the team stay aligned! 💬"
                    
                    self.bot.client.chat_postMessage(
                        channel=self.bot.channel_id,
                        thread_ts=standup_ts,
                        text=reminder_message
                    )
                    
                    print(f"Reminder sent for standup {standup_ts}")
                    
        except SlackApiError as e:
            print(f"Error checking missing responses: {e.response['error']}")
    
    def send_standup_to_all_users(self, users=None):
        """Send standup prompt to all users or specified users."""
        try:
            if users is None:
                # Get all users from Slack
                users = self.bot.get_slack_user_list()
            
            if not users:
                print("⚠️ No users found to send standup to")
                return
            
            # Send standup to each user
            for user_id in users:
                try:
                    self.bot.send_standup_to_dm(user_id)
                    time.sleep(0.5)  # Rate limiting
                except Exception as e:
                    print(f"❌ Error sending standup to {user_id}: {e}")
            
            print(f"✅ Standup sent to {len(users)} users")
            
        except Exception as e:
            print(f"❌ Error in send_standup_to_all_users: {e}")
    
    def send_health_check_to_all_users(self, users=None):
        """Send health check to all users or specified users."""
        try:
            if users is None:
                # Get all users from Slack
                users = self.bot.get_slack_user_list()
            
            if not users:
                print("⚠️ No users found to send health check to")
                return
            
            # Send health check to each user
            for user_id in users:
                try:
                    self.bot.send_health_check_to_dm(user_id)
                    time.sleep(0.5)  # Rate limiting
                except Exception as e:
                    print(f"❌ Error sending health check to {user_id}: {e}")
            
            print(f"✅ Health check sent to {len(users)} users")
            
        except Exception as e:
            print(f"❌ Error in send_health_check_to_all_users: {e}")
    
    def send_daily_blocker_digest(self):
        """Send daily blocker digest to the team."""
        try:
            # This function sends the message but doesn't actually grab the blocker list - NEED TO FIX
            digest_message = "📊 *Daily Blocker Digest*\n\nHere's a summary of today's blockers and their status:\n\n"
            digest_message += "🔍 *Active Blockers:*\n"
            digest_message += "• No active blockers found\n\n"
            digest_message += "✅ *Resolved Today:*\n"
            digest_message += "• No blockers resolved today\n\n"
            digest_message += "📈 *Summary:*\n"
            digest_message += "• Total blockers: 0\n"
            digest_message += "• Resolved: 0\n"
            digest_message += "• Still active: 0\n\n"
            digest_message += "Great job team! Keep up the momentum! 🚀"
            
            self.bot.client.chat_postMessage(
                channel=self.bot.channel_id,
                text=digest_message
            )
            
            print("✅ Daily blocker digest sent")
            
        except SlackApiError as e:
            print(f"Error sending daily blocker digest: {e.response['error']}")
    
    def send_daily_standup_digest(self):
        """Send daily standup digest to the team."""
        try:
            digest_message = "📊 *Daily Standup Digest*\n\nHere's a summary of today's standup responses:\n\n"
            digest_message += "👥 *Response Summary:*\n"
            digest_message += "• Total responses: 0\n"
            digest_message += "• On track: 0\n"
            digest_message += "• Need help: 0\n"
            digest_message += "• No response: 0\n\n"
            digest_message += "📋 *Key Updates:*\n"
            digest_message += "• No updates to report\n\n"
            digest_message += "🎯 *Next Steps:*\n"
            digest_message += "• Continue with current priorities\n"
            digest_message += "• Reach out if you need support\n\n"
            digest_message += "Keep up the great work! 💪"
            
            self.bot.client.chat_postMessage(
                channel=self.bot.channel_id,
                text=digest_message
            )
            
            print("✅ Daily standup digest sent")
            
        except SlackApiError as e:
            print(f"Error sending daily standup digest: {e.response['error']}")
    
    def clear_followup_tracking(self):
        """Clear follow-up tracking to prevent duplicates."""
        self.bot.last_followup_sent = {}
        print("✅ Follow-up tracking cleared")
    
    def run_scheduler(self):
        """Run the scheduler loop."""
        while True:
            schedule.run_pending()
            time.sleep(3600)  # Check every hour instead of every minute 