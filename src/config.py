"""
Configuration settings for the Daily Standup Bot.
Modify these settings to customize the bot behavior.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv('.env')

class BotConfig:
    """Configuration class for the Daily Standup Bot."""
    
    # Slack Configuration
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
    SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")  # Fallback channel for general bot messages
    SLACK_ESCALATION_CHANNEL = os.environ.get("SLACK_ESCALATION_CHANNEL", "leads")
    SLACK_BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "U0912DJRNSF")  # Bot user ID
    # Add more channel variables as needed
    
    # Timing Configuration
    STANDUP_TIME = os.environ.get("STANDUP_TIME", "09:00")
    RESPONSE_DEADLINE = os.environ.get("RESPONSE_DEADLINE", "10:00")
    REMINDER_TIME = os.environ.get("REMINDER_TIME", "09:30")
    
    # Workflow Configuration
    ESCALATION_EMOJI = os.environ.get("ESCALATION_EMOJI", "🆘")
    MONITOR_EMOJI = os.environ.get("MONITOR_EMOJI", "🕓")
    AUTO_ESCALATION_DELAY_HOURS = int(os.environ.get("AUTO_ESCALATION_DELAY_HOURS", "2"))
    
    # Flask Configuration
    FLASK_HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.environ.get("FLASK_PORT", "3000"))
    FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "False") == "True"
    
    # Coda Configuration
    CODA_API_TOKEN = os.environ.get("CODA_API_TOKEN")
    CODA_DOC_ID = os.environ.get("CODA_DOC_ID")
    # Coda table IDs
    MAIN_HEALTH_CHECK_TABLE = os.environ.get("Health_Check")
    BLOCKER_TABLE = os.environ.get("Blocker")
    STANDUP_TABLE = os.environ.get("Stand_Up")
    BLOCKER_RESOLUTION_TABLE = os.environ.get("Blocker_Resolution")
    KR_TABLE = os.environ.get("KR_Table")
    AFTER_HEALTH_CHECK_TABLE = os.environ.get("After_Health_Check")
    RESPONSE_TABLE = os.environ.get("Response")
    ERROR_TABLE = os.environ.get("ERROR_TABLE", "error_logs")  # Fallback if not set
    
    # AI Configuration
    MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
    
    # Message Templates
    STANDUP_MESSAGE_TEMPLATE = """
🌞 *Good morning team! Time for the daily standup!*

Please reply to this thread with:

1️⃣ *What did you do today?*
2️⃣ *Are you on track to meet your goals?* (Yes/No)
3️⃣ *Any blockers?*

*Example:*
• Today: Implemented cart UI
• On Track: Yes
• Blockers: Need final specs from design team

<!channel> please respond by {deadline}. Let's stay aligned! 💬
""".strip()
    
    FOLLOWUP_MESSAGE_TEMPLATE = """
<@{user_id}>, thanks for the update! Since you're either not on track or facing a blocker, would you like help?

*Your status:*
• On Track: {on_track}
• Blockers: {blockers}

React with one of the following:
• {escalation_emoji} = Need help now
• {monitor_emoji} = Can wait / just keeping team informed
""".strip()
    
    ESCALATION_MESSAGE_TEMPLATE = """
🚨 *Escalation Alert* 🚨

<@{user_id}> ({user_name}) reported a blocker or delay:

*Status:*
• On Track: {on_track}
• Blockers: {blockers}
• Today's Work: {today_work}

⏰ Urgency: HIGH
📆 Date: {timestamp}

<!here> please reach out to <@{user_id}> to provide assistance.
""".strip()
    
    # Response parsing patterns
    RESPONSE_PATTERNS = {
        'on_track': r'on\s*track\s*:\s*(yes|no)',
        'blockers': r'blockers?\s*:\s*(none|no|.*?)(?:\n|$)',
        'today_work': r'today\s*:\s*(.*?)(?:\n|$)',
    }
    
    # Valid "no blockers" responses
    NO_BLOCKERS_KEYWORDS = ['none', 'no', 'n/a', '']
    
    @classmethod
    def validate_config(cls):
        """Validate that all required configuration is present."""
        required_vars = ['SLACK_BOT_TOKEN', 'SLACK_CHANNEL_ID']
        missing_vars = [var for var in required_vars if not getattr(cls, var)]
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        # Check if Mistral API key is available (optional but recommended)
        if not cls.MISTRAL_API_KEY:
            print("⚠️ Warning: MISTRAL_API_KEY not found. AI features will be limited.")
        
        return True
    
    @classmethod
    def get_config_dict(cls):
        """Get configuration as a dictionary for easy access."""
        return {
            'mistral_api_key': cls.MISTRAL_API_KEY,
            'slack_bot_token': cls.SLACK_BOT_TOKEN,
            'slack_channel_id': cls.SLACK_CHANNEL_ID,
            'escalation_channel': cls.SLACK_ESCALATION_CHANNEL,
            'mongodb_uri': os.environ.get("MONGODB_URI"),
            'mongodb_db_name': os.environ.get("MONGODB_DB_NAME"),
            'standup_time': cls.STANDUP_TIME,
            'reminder_time': cls.REMINDER_TIME,
            'response_deadline': cls.RESPONSE_DEADLINE,
            'escalation_emoji': cls.ESCALATION_EMOJI,
            'monitor_emoji': cls.MONITOR_EMOJI,
            'auto_escalation_delay_hours': cls.AUTO_ESCALATION_DELAY_HOURS,
            'flask_host': cls.FLASK_HOST,
            'flask_port': cls.FLASK_PORT,
            'flask_debug': cls.FLASK_DEBUG,
        } 