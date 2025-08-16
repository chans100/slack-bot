import os
from dotenv import load_dotenv
from .bot import DailyStandupBot

load_dotenv('.env')

# Initialize bot with Socket Mode
app_token = os.environ.get("SLACK_APP_TOKEN")
if not app_token:
    print("❌ ERROR: SLACK_APP_TOKEN not found! Socket Mode cannot work.")
    exit(1)

bot = DailyStandupBot(
    socket_mode=True,
    app_token=app_token
)

def main():
    """Main function to run the bot in Socket Mode."""
    print("🤖 Starting Daily Standup Bot in Socket Mode...")
    
    # Run the bot (Socket Mode will handle events)
    bot.run()

if __name__ == "__main__":
    main() 