import express from "express";
import cors from "cors";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { createServer } from "./server.js";
import { config } from "./config/index.js";

/**
 * HTTP entry point for the MCP server.
 * Uses SSEServerTransport to handle requests via Express.
 */
async function main() {
  const app = express();
  
  // Basic security and CORS
  app.use(cors());
  
  // We need to store transports for active sessions
  const transports: Map<string, SSEServerTransport> = new Map();

  // 1. SSE Endpoint to establish the connection
  app.get("/sse", async (req, res) => {
    try {
      console.log(`[HTTP] New SSE connection established`);
      
      // Initialize the transport and tell it where clients should POST messages
      const transport = new SSEServerTransport("/messages", res);
      
      // Create a dedicated server instance for this connection
      const mcpServer = createServer();
      // connect() automatically calls transport.start()
      await mcpServer.connect(transport);
      
      // Store the transport for routing incoming messages
      transports.set(transport.sessionId, transport);
      
      res.on("close", () => {
        console.log(`[HTTP] SSE connection closed for session: ${transport.sessionId}`);
        transports.delete(transport.sessionId);
      });
    } catch (error) {
      console.error("[HTTP] Error establishing SSE connection:", error);
      res.status(500).send("Internal Server Error");
    }
  });

  // 2. Message Endpoint to receive JSON-RPC calls
  app.post("/messages", async (req, res) => {
    // The SSE transport automatically appends ?sessionId=... to the endpoint URL
    const sessionId = req.query.sessionId as string;
    const transport = transports.get(sessionId);

    if (!transport) {
      res.status(404).send("Session not found or expired");
      return;
    }

    try {
      // The transport will handle parsing the request and sending the response
      await transport.handlePostMessage(req, res);
    } catch (error) {
      console.error("[HTTP] Error handling POST message:", error);
      if (!res.headersSent) {
        res.status(500).send("Internal Server Error");
      }
    }
  });

  const port = config.port || 3000;
  app.listen(port, () => {
    console.log(`MCP HTTP Server successfully started on port ${port}`);
    console.log(`SSE Endpoint available at: http://localhost:${port}/sse`);
  });
}

main().catch((error) => {
  console.error("Fatal error in main:", error);
  process.exit(1);
});
