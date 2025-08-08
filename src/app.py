import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from .bot import DailyStandupBot

load_dotenv('.env')

app = Flask(__name__)
bot = DailyStandupBot()

# Import and register routes from commands and events modules
from .commands import register_command_routes
from .events import register_event_routes

register_command_routes(app, bot)
register_event_routes(app, bot)

def main():
    """Main function to run the Flask app."""
    print("🤖 Starting Daily Standup Bot Flask App...")
    
    # Start the bot's scheduled tasks
    bot.start()
    
    # Run the Flask app
    app.run(host=bot.config.FLASK_HOST, port=bot.config.FLASK_PORT, debug=bot.config.FLASK_DEBUG)

if __name__ == "__main__":
    main() 