import dotenv from 'dotenv';
dotenv.config({ quiet: true });

export const config = {
  webhookUrl: process.env.WEBHOOK_URL || '',
  webhookTimeout: parseInt(process.env.WEBHOOK_TIMEOUT || '30000', 10),
  port: parseInt(process.env.PORT || '3000', 10),
  serverName: 'n8n-webhook-mcp-server',
  serverVersion: '1.0.0',
};

if (!config.webhookUrl) {
  console.error('CRITICAL: WEBHOOK_URL is not set. The server will not function correctly.');
}
