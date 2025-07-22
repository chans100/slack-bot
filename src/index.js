require('dotenv').config();
const { WebClient } = require('@slack/web-api');
const { App } = require('@slack/bolt');
const CodaIntegration = require('./coda-integration');

// Verify environment variables
if (!process.env.SLACK_BOT_TOKEN || !process.env.SLACK_SIGNING_SECRET || !process.env.SLACK_CHANNEL_ID) {
  console.error('Missing required environment variables. Please check your .env file.');
  process.exit(1);
}

// Initialize Slack clients
const web = new WebClient(process.env.SLACK_BOT_TOKEN);
const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
  socketMode: false
});

// Initialize Coda integration
const coda = new CodaIntegration();

// Store responses (fallback if Coda is not configured)
const responses = new Map();

// Send daily prompt
async function sendDailyPrompt() {
  try {
    const result = await web.chat.postMessage({
      channel: process.env.SLACK_CHANNEL_ID,
      text: "How are you feeling today? (1-5, where 1 is not great and 5 is excellent, or 'blocked' if you need help)",
      blocks: [
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: "How are you feeling today? (1-5, where 1 is not great and 5 is excellent, or 'blocked' if you need help)"
          }
        },
        {
          type: "actions",
          elements: [
            {
              type: "button",
              text: {
                type: "plain_text",
                text: "1",
                emoji: true
              },
              value: "1",
              action_id: "button_click_1"
            },
            {
              type: "button",
              text: {
                type: "plain_text",
                text: "2",
                emoji: true
              },
              value: "2",
              action_id: "button_click_2"
            },
            {
              type: "button",
              text: {
                type: "plain_text",
                text: "3",
                emoji: true
              },
              value: "3",
              action_id: "button_click_3"
            },
            {
              type: "button",
              text: {
                type: "plain_text",
                text: "4",
                emoji: true
              },
              value: "4",
              action_id: "button_click_4"
            },
            {
              type: "button",
              text: {
                type: "plain_text",
                text: "5",
                emoji: true
              },
              value: "5",
              action_id: "button_click_5"
            },
            {
              type: "button",
              text: {
                type: "plain_text",
                text: "🚨 Blocked",
                emoji: true
              },
              value: "blocked",
              action_id: "button_click_blocked",
              style: "danger"
            }
          ]
        }
      ]
    });
    console.log('Daily prompt sent successfully');
  } catch (error) {
    console.error('Error sending daily prompt:', error);
  }
}

// Handle button clicks
app.action(/button_click_\d+/, async ({ ack, body, client }) => {
  await ack();
  
  const userId = body.user.id;
  const response = body.actions[0].value;
  const timestamp = new Date().toISOString();
  
  // Store initial response in Coda (primary storage)
  const codaSuccess = await coda.addResponse(userId, response, timestamp);
  
  // Fallback to in-memory storage if Coda fails
  if (!codaSuccess) {
  responses.set(userId, {
    response,
    timestamp
  });
    console.log('Stored response in memory as fallback');
  }
  
  // Log to console
  console.log(`User ${userId} responded with ${response} at ${timestamp}`);
  
  // Send confirmation and follow-up questions if blocked
  try {
    if (response === 'blocked') {
      // Send follow-up questions for blocked users
      await client.chat.postMessage({
        channel: body.channel.id,
        text: `Thanks for your response! You selected "I'm blocked". Let me help you get unblocked.`,
        blocks: [
          {
            type: "section",
            text: {
              type: "mrkdwn",
              text: `Thanks for your response! You selected "I'm blocked". Let me help you get unblocked.`
            }
          },
          {
            type: "section",
            text: {
              type: "mrkdwn",
              text: "Please provide the following information:"
            }
          },
          {
            type: "input",
            block_id: "blocker_description",
            label: {
              type: "plain_text",
              text: "What's blocking you?"
            },
            element: {
              type: "plain_text_input",
              action_id: "blocker_description_input",
              placeholder: {
                type: "plain_text",
                text: "Describe the blocker in detail..."
              },
              multiline: true
            }
          },
          {
            type: "input",
            block_id: "kr_name",
            label: {
              type: "plain_text",
              text: "Key Result (KR) Name"
            },
            element: {
              type: "plain_text_input",
              action_id: "kr_name_input",
              placeholder: {
                type: "plain_text",
                text: "e.g., KR1: Increase user engagement"
              }
            }
          },
          {
            type: "input",
            block_id: "urgency",
            label: {
              type: "plain_text",
              text: "Urgency Level"
            },
            element: {
              type: "static_select",
              action_id: "urgency_input",
              placeholder: {
                type: "plain_text",
                text: "Select urgency level"
              },
              options: [
                {
                  text: {
                    type: "plain_text",
                    text: "Low - Can wait a few days"
                  },
                  value: "low"
                },
                {
                  text: {
                    type: "plain_text",
                    text: "Medium - Need help this week"
                  },
                  value: "medium"
                },
                {
                  text: {
                    type: "plain_text",
                    text: "High - Blocking critical work"
                  },
                  value: "high"
                },
                {
                  text: {
                    type: "plain_text",
                    text: "Critical - Blocking entire team"
                  },
                  value: "critical"
                }
              ]
            }
          },
          {
            type: "actions",
            elements: [
              {
                type: "button",
                text: {
                  type: "plain_text",
                  text: "Submit Blocker Details",
                  emoji: true
                },
                value: "submit_blocker",
                action_id: "submit_blocker_details",
                style: "primary"
              }
            ]
          }
        ]
      });
    } else {
      // Send simple confirmation for non-blocked responses
    await client.chat.postMessage({
      channel: body.channel.id,
      text: `Thanks for your response! You selected ${response}.`
    });
    }
  } catch (error) {
    console.error('Error sending confirmation:', error);
  }
});

// Handle blocker details form submission
app.action('submit_blocker_details', async ({ ack, body, client }) => {
  await ack();
  
  const userId = body.user.id;
  const timestamp = new Date().toISOString();
  
  try {
    // Extract form data from the view
    const formData = body.state?.values || {};
    
    const blockerDescription = formData.blocker_description?.blocker_description_input?.value || 'Not provided';
    const krName = formData.kr_name?.kr_name_input?.value || 'Not provided';
    const urgency = formData.urgency?.urgency_input?.selected_option?.value || 'Not provided';
    
    // Store structured blocker data in Coda
    const codaSuccess = await coda.addBlockerDetails(userId, {
      blockerDescription,
      krName,
      urgency,
      timestamp
    });
    
    if (codaSuccess) {
      await client.chat.postMessage({
        channel: body.channel.id,
        text: `✅ Blocker details submitted successfully! I've logged this in our tracking system.`,
        blocks: [
          {
            type: "section",
            text: {
              type: "mrkdwn",
              text: `✅ *Blocker details submitted successfully!*\n\nI've logged this in our tracking system and will notify the team.`
            }
          },
          {
            type: "section",
            fields: [
              {
                type: "mrkdwn",
                text: `*KR:* ${krName}`
              },
              {
                type: "mrkdwn",
                text: `*Urgency:* ${urgency}`
              }
            ]
          },
          {
            type: "section",
            text: {
              type: "mrkdwn",
              text: `*Blocker:* ${blockerDescription}`
            }
          }
        ]
      });
    } else {
      await client.chat.postMessage({
        channel: body.channel.id,
        text: "❌ There was an issue saving your blocker details. Please try again or contact support."
      });
    }
    
  } catch (error) {
    console.error('Error handling blocker details submission:', error);
    await client.chat.postMessage({
      channel: body.channel.id,
      text: "❌ There was an error processing your submission. Please try again."
    });
  }
});

// Start the app
(async () => {
  try {
    await app.start(3000);
    console.log('⚡️ Bolt app is running!');
    
    // Send initial prompt
    await sendDailyPrompt();
    
    // Schedule daily prompt (every 24 hours)
    setInterval(sendDailyPrompt, 24 * 60 * 60 * 1000);
  } catch (error) {
    console.error('Error starting app:', error);
    process.exit(1);
  }
})(); 