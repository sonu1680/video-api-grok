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

// --- HTTP Client ---
const httpClient = axios.create({
  timeout: TIMEOUT,
  headers: { 'Content-Type': 'application/json' }
});

// --- MCP Server & Tools Factory ---
function createAndConfigureServer() {
  const server = new McpServer({
    name: "n8n-mcp-server",
    version: "2.0.0",
  });

  // Tool: send_stories
  server.tool(
    "send_stories",
    {
      stories: z.array(z.object({
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
      })).describe("The array of story objects to be sent")
    },
    async ({ stories }) => {
      try {
        const { data } = await httpClient.post(`${WEBHOOK_URL}/webhook/c24ec734-cf0c-40cd-b168-58779fcde463`, { stories });
        return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
      } catch (error: any) {
        return { isError: true, content: [{ type: "text", text: `Error: ${error.message}` }] };
      }
    }
  );

  // Tool: add_memory
  server.tool(
    "add_memory",
    {
      data: z.string().describe("The text or information to be stored as memory")
    },
    async ({ data }) => {
      try {
        const { data: result } = await httpClient.post(`${WEBHOOK_URL}/webhook/ff045203-6928-4375-85af-208cf22b4d4c`, { data });
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (error: any) {
        return { isError: true, content: [{ type: "text", text: `Error: ${error.message}` }] };
      }
    }
  );

  // Tool: get_memory
  server.tool(
    "get_memory",
    {},
    async () => {
      try {
        const { data: result } = await httpClient.post(`${WEBHOOK_URL}/webhook/b475f8a7-00b1-4c61-be5e-25c2ea9ec393`, {});
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
