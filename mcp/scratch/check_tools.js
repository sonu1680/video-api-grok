import axios from 'axios';
import { EventSource } from 'eventsource';

const baseUrl = 'https://mcp.sonupandit.in';
const sseUrl = `${baseUrl}/sse`;

console.log(`Connecting to ${sseUrl}...`);
const es = new EventSource(sseUrl);

es.addEventListener('endpoint', async (event) => {
  const messageUrl = `${baseUrl}${event.data}`;
  console.log(`Received message endpoint: ${messageUrl}`);

  try {
    console.log('Sending initialize request...');
    await axios.post(messageUrl, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2024-11-05",
        capabilities: {},
        clientInfo: { name: "tool-checker", version: "1.0.0" }
      }
    });

    console.log('Sending tools/list request...');
    const response = await axios.post(messageUrl, {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/list",
      params: {}
    });

    console.log('Successfully sent requests. Waiting for responses on SSE...');
  } catch (error) {
    console.error('Error sending requests:', error.message);
    if (error.response) console.error('Response:', error.response.data);
    process.exit(1);
  }
});

es.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  console.log('Received from SSE:', JSON.stringify(data, null, 2));

  if (data.id === 2) {
    const tools = data.result.tools;
    console.log(`\nSUCCESS! Found ${tools.length} tools:`);
    tools.forEach(t => console.log(`- ${t.name}: ${t.description}`));
    es.close();
    process.exit(0);
  }
});

es.onerror = (err) => {
  console.error('EventSource error:', err);
  es.close();
  process.exit(1);
};

// Timeout after 15 seconds
setTimeout(() => {
  console.error('Timeout waiting for tools list');
  es.close();
  process.exit(1);
}, 15000);
