import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { createServer } from "./server.js";
import { config } from "./config/index.js";

/**
 * Main entry point for the MCP server.
 * Connects the server to Stdio transport.
 */
async function main() {
  const server = createServer();
  const transport = new StdioServerTransport();

  try {
    await server.connect(transport);
    console.error(`MCP Server "${config.serverName}" version ${config.serverVersion} started!`);
  } catch (error) {
    console.error("Failed to start MCP server:", error);
    process.exit(1);
  }
}

main().catch((error) => {
  console.error("Fatal error in main:", error);
  process.exit(1);
});
