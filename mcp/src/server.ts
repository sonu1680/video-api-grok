import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import { config } from "./config/index.js";
import { registerWebhookTools } from "./tools/fetchData.js";

/**
 * Initializes the MCP server instance and registers all tools and resources.
 */
export function createServer() {
  const server = new McpServer({
    name: config.serverName,
    version: config.serverVersion,
  });

  // Register tools
  registerWebhookTools(server);

  // Add more tool/resource registrations here as the project grows
  
  return server;
}
