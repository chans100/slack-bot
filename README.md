# Slack Bot with Coda Integration

A Slack bot that sends daily mood check prompts and stores responses in a Coda table.

## Features

- 🤖 Sends daily mood check prompts to a Slack channel
- 📊 Stores responses in a Coda table for analysis
- 🔄 Fallback to in-memory storage if Coda is unavailable
- ⏰ Configurable timing for daily prompts
- 🎯 Interactive buttons for easy response collection

## Setup

### 1. Environment Variables

Create a `.env` file in the `slack-bot` directory with the following variables:

```env
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
SLACK_CHANNEL_ID=C0123456789

# Coda Configuration
CODA_API_TOKEN=your-coda-api-token-here
CODA_DOC_ID=your-coda-doc-id-here
CODA_TABLE_ID=your-coda-table-id-here
```

### 2. Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Create a new app or use an existing one
3. Add the following OAuth scopes:
   - `chat:write`
   - `channels:read`
   - `users:read`
4. Install the app to your workspace
5. Copy the Bot User OAuth Token and Signing Secret

### 3. Coda Setup

1. Create a new Coda doc or use an existing one
2. Create a table with these columns:
   - **User ID** (Text)
   - **Response** (Text) 
   - **Timestamp** (DateTime)
3. Get your API token from [coda.io/account](https://coda.io/account)
4. Get your Doc ID from the URL: `https://coda.io/d/_d{CODA_DOC_ID}`
5. Get your Table ID from the table URL or API

### 4. Install Dependencies

```bash
npm install
```

### 5. Test the Integration

```bash
node test-coda.js
```

### 6. Run the Bot

```bash
npm start
```

## Usage

The bot will:
1. Send a daily mood check prompt at startup
2. Send prompts every 24 hours
3. Store responses in Coda when users click buttons
4. Provide fallback storage if Coda is unavailable

### Commands

Users can interact with the bot using slash commands (`/`) or exclamation commands (`!`):

- `/checkin` or `!checkin` - Start a standup check-in
- `/blocked` or `!blocked` - Report a blocker (mentor check first)
- `/kr [search]` or `!kr [search]` - Search for Key Results
- `/kr` or `!kr` - Get KR help (mentor check first)
- `/health` or `!health` - Start a health check
- `/help` or `!help` - Show help message with available commands

Commands can be used in direct messages with the bot.

## API Reference

### CodaIntegration Class

- `addResponse(userId, response, timestamp)` - Add a new response to Coda
- `getResponses()` - Retrieve all responses from Coda
- `getTableSchema()` - Get table metadata
- `isConfigured()` - Check if Coda is properly configured

## Troubleshooting

- **"Coda not configured"** - Check your environment variables
- **"Failed to store response"** - Verify your Coda API token and table permissions
- **"Missing signing secret"** - Add SLACK_SIGNING_SECRET to your .env file

## Development

```bash
npm run dev  # Run with nodemon for development
``` 