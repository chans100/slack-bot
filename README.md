# Python Slack Healthcheck Bot

A Python-based Slack bot that posts daily healthcheck prompts to a specified channel.

## Features

- Sends daily healthcheck messages at 9:00 AM
- Interactive buttons for team members to respond
- Easy configuration through environment variables

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables:
- Create a `.env` file with the following variables:
  ```
  SLACK_BOT_TOKEN=xoxb-your-bot-token
  SLACK_CHANNEL_ID=C0123456789
  ```

3. Run the bot:
```bash
python slack_healthcheck_bot.py
```

## Environment Variables

- `SLACK_BOT_TOKEN`: Your Slack Bot User OAuth Token
- `SLACK_CHANNEL_ID`: The ID of the channel where the bot will post messages

## Requirements

- Python 3.7+
- slack-sdk
- python-dotenv
- schedule

## Getting Started with Slack

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app
2. Add the following bot token scopes:
   - `chat:write`
   - `chat:write.public`
   - `reactions:write`
3. Install the app to your workspace
4. Copy the bot token and channel ID to your `.env` file
