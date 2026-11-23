import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createApiClient } from './api-client.js';
import { createServer } from './server.js';

try {
  await createServer(createApiClient()).connect(new StdioServerTransport());
} catch (error) {
  // stdout is reserved exclusively for MCP protocol messages.
  console.error(`MCP startup failed: ${error.message}`);
  process.exitCode = 1;
}
