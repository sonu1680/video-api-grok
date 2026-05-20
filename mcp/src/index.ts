import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import axios from "axios";
import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";

// --- Configuration ---
dotenv.config({ quiet: true });
const WEBHOOK_URL = process.env.WEBHOOK_URL || 'https://n8n.sonupandit.in';
const TIMEOUT = parseInt(process.env.WEBHOOK_TIMEOUT || '30000', 10);
const PORT = parseInt(process.env.PORT || '5000', 10);

// --- n8n webhook paths (kept in sync with app/config.py) ---
const PATHS = {
  // object_talking
  OBJECT_STORE_SCRIPT: "c24ec734-cf0c-40cd-b168-58779fcde463",
  OBJECT_STORE_NAME:   "ff045203-6928-4375-85af-208cf22b4d4c",
  OBJECT_GET_MEMORY:   "b475f8a7-00b1-4c61-be5e-25c2ea9ec393",
  // food_discovery
  FOOD_STORE_SCRIPT:   "8f08ec11-d1ad-45d8-ae8f-4f9c37f72612",
  FOOD_STORE_NAME:     "ff045203-6928-4375-85af-208cf22b4d4a",
  FOOD_GET_MEMORY:     "b475f8a7-00b1-4c61-be5e-25c2ea9ec391",
} as const;

const webhookUrl = (path: string) => `${WEBHOOK_URL}/webhook/${path}`;

// --- HTTP Client ---
const httpClient = axios.create({
  timeout: TIMEOUT,
  headers: { 'Content-Type': 'application/json' }
});

// --- MCP Server & Tools Factory ---
function createAndConfigureServer() {
  const server = new McpServer({
    name: "n8n-mcp-server",
    version: "2.1.0",
  });

  const storySchema = z.array(z.object({
    id: z.number().describe("Unique identifier for the story"),
    title: z.string().describe("Title of the story"),
    description: z.string().describe("Description of the story"),
    tags: z.string().describe("Tags associated with the story"),
    duration: z.string().describe("Estimated duration of the story"),
    modules: z.array(z.object({
      module_number: z.number().describe("Number of the module within the story"),
      time: z.string().describe("Timestamp or duration for the module"),
      image_generation_prompt: z.string().describe("Prompt for generating images for this module"),
      video_generation_prompt: z.string().describe("Prompt for generating video for this module")
    })).describe("List of modules that make up the story")
  })).describe("The array of story objects to be sent");

  // ─── object_talking tools ──────────────────────────────────────────────

  server.tool(
    "send_stories",
    "Send object_talking stories with their modules to n8n for processing",
    { stories: storySchema },
    async ({ stories }) => {
      try {
        const { data } = await httpClient.post(webhookUrl(PATHS.OBJECT_STORE_SCRIPT), { stories });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (error: any) {
        return { isError: true, content: [{ type: "text", text: `Error: ${error.message}` }] };
      }
    }
  );

  server.tool(
    "add_memory",
    "Store an object_talking memory entry (e.g. an object name already used)",
    { data: z.string().describe("The text or information to be stored as memory") },
    async ({ data }) => {
      try {
        const { data: result } = await httpClient.post(webhookUrl(PATHS.OBJECT_STORE_NAME), { data });
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (error: any) {
        return { isError: true, content: [{ type: "text", text: `Error: ${error.message}` }] };
      }
    }
  );

  server.tool(
    "get_memory",
    "Fetch all stored object_talking memory entries from n8n",
    {},
    async () => {
      try {
        const { data: result } = await httpClient.post(webhookUrl(PATHS.OBJECT_GET_MEMORY), {});
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (error: any) {
        return { isError: true, content: [{ type: "text", text: `Error: ${error.message}` }] };
      }
    }
  );

  // ─── food_discovery tools ──────────────────────────────────────────────

  server.tool(
    "send_food_stories",
    "Send food_discovery stories with their modules to n8n for processing",
    { stories: storySchema },
    async ({ stories }) => {
      try {
        const { data } = await httpClient.post(webhookUrl(PATHS.FOOD_STORE_SCRIPT), { stories });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (error: any) {
        return { isError: true, content: [{ type: "text", text: `Error: ${error.message}` }] };
      }
    }
  );

  server.tool(
    "add_food_memory",
    "Store a food_discovery memory entry (e.g. a dish already used)",
    { data: z.string().describe("The text or information to be stored as memory") },
    async ({ data }) => {
      try {
        const { data: result } = await httpClient.post(webhookUrl(PATHS.FOOD_STORE_NAME), { data });
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (error: any) {
        return { isError: true, content: [{ type: "text", text: `Error: ${error.message}` }] };
      }
    }
  );

  server.tool(
    "get_food_memory",
    "Fetch all stored food_discovery memory entries from n8n",
    {},
    async () => {
      try {
        const { data: result } = await httpClient.post(webhookUrl(PATHS.FOOD_GET_MEMORY), {});
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (error: any) {
        return { isError: true, content: [{ type: "text", text: `Error: ${error.message}` }] };
      }
    }
  );

  return server;
}

// --- Express SSE Server ---
const app = express();
app.use(cors());
const transports: Map<string, SSEServerTransport> = new Map();

app.get("/sse", async (req, res) => {
  console.log("[HTTP] Establishing SSE connection");
  const transport = new SSEServerTransport("/messages", res);
  const server = createAndConfigureServer();
  await server.connect(transport);
  transports.set(transport.sessionId, transport);
  res.on("close", () => transports.delete(transport.sessionId));
});

app.post("/messages", async (req, res) => {
  const transport = transports.get(req.query.sessionId as string);
  if (!transport) return res.status(404).send("Session expired");
  await transport.handlePostMessage(req, res);
});

app.listen(PORT, () => {
  console.log(`MCP Server running on port ${PORT}`);
  console.log(`Grok AI URL: http://localhost:${PORT}/sse`);
});
