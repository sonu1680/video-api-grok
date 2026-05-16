import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { httpClient } from "../utils/httpClient.js";
import { config } from "../config/index.js";

/**
 * Registers the fetch_webhook_data tool with the MCP server.
 * This tool calls the configured n8n webhook and returns the response.
 */
export function registerWebhookTools(server: McpServer) {
  server.registerTool(
    "fetch_webhook_data",
    {
      description: "Fetch data from the n8n webhook",
      inputSchema: z.object({
        endpoint: z.string().optional().describe("Optional sub-path to append to the base webhook URL (e.g., '/status')"),
        method: z.enum(["GET", "POST", "PUT", "DELETE", "PATCH"]).default("POST").describe("HTTP method to use"),
        query: z.record(z.string(), z.string()).optional().describe("Query parameters to append to the URL"),
        body: z.record(z.string(), z.any()).optional().describe("JSON body payload for POST/PUT/PATCH requests"),
        headers: z.record(z.string(), z.string()).optional().describe("Custom HTTP headers (e.g., Authorization)"),
      }),
    },
    async ({ endpoint, method, query, body, headers }) => {
      if (!config.webhookUrl) {
        return {
          isError: true,
          content: [
            {
              type: "text",
              text: "Error: WEBHOOK_URL is not configured on the server. Please check your environment variables.",
            },
          ],
        };
      }

      try {
        let finalUrl = config.webhookUrl;
        if (endpoint) {
          // Ensure no double slashes if webhookUrl has trailing slash and endpoint has leading slash
          const baseUrl = finalUrl.replace(/\/$/, "");
          const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
          finalUrl = `${baseUrl}${path}`;
        }

        const requestConfig = {
          url: finalUrl,
          method,
          params: query,
          data: body,
          headers,
        };

        const data = await httpClient.request(requestConfig);

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(data, null, 2),
            },
          ],
        };
      } catch (error: any) {
        let errorMessage = error.message;

        // If it's an Axios error, try to extract more details from the response
        if (error.response && error.response.data) {
          const detail = typeof error.response.data === 'string' 
            ? error.response.data 
            : JSON.stringify(error.response.data, null, 2);
          errorMessage = `HTTP ${error.response.status}: ${detail}`;
        }

        return {
          isError: true,
          content: [
            {
              type: "text",
              text: `Error fetching data from webhook: ${errorMessage}`,
            },
          ],
        };
      }
    }
  );
}
