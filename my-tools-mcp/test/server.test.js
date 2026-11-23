import test from 'node:test';
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { fileURLToPath } from 'node:url';
import { createServer } from '../src/server.js';

test('MCP discovers tools, validates input and maps create/status operations', async () => {
  const calls = [];
  const server = createServer(async (path, options) => {
    calls.push({ path, options });
    return { id: 'saved-task', ...options?.body };
  });
  const client = new Client({ name: 'test-client', version: '1.0.0' });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  try {
    assert.equal((await client.listTools()).tools.length, 11);
    const taskId = 'ae6ade44-e2fe-4e55-bdb3-3a442d01f654';
    const created = await client.callTool({ name: 'create_task', arguments: { projectId: taskId, name: 'Test task' } });
    assert.equal(created.isError, undefined);
    assert.equal(calls[0].path, 'tasks');
    assert.equal(calls[0].options.method, 'POST');
    assert.equal(calls[0].options.body.status, 'Open');
    await client.callTool({ name: 'set_task_status', arguments: { taskId, status: 'Done' } });
    assert.deepEqual(calls[1], { path: `tasks/${taskId}`, options: { method: 'PATCH', body: { status: 'Done' } } });
    const invalid = await client.callTool({ name: 'set_task_status', arguments: { taskId, status: 'Invalid' } });
    assert.equal(invalid.isError, true);
    const empty = await client.callTool({ name: 'update_task', arguments: { taskId, changes: {} } });
    assert.equal(empty.isError, true);
    assert.equal(calls.length, 2);
    await client.callTool({ name: 'list_logs', arguments: {
      applicationName: ['frontend'], logLevel: ['WARN', 'ERROR'],
      timestamp_from: '2026-11-23T10:00:00', message: 'playback', className: 'Player',
    } });
    assert.deepEqual(calls[2], { path: '', options: { scope: 'logs', query: {
      page: 0, size: 20, sort: 'timestamp', direction: 'desc',
      applicationName: ['frontend'], logLevel: ['WARN', 'ERROR'],
      timestamp_from: '2026-11-23T10:00:00', message: 'playback', className: 'Player',
    } } });
    await client.callTool({ name: 'get_log_filter_values', arguments: { field: 'moduleName' } });
    assert.deepEqual(calls[3], { path: 'module-names', options: { scope: 'logs', query: {} } });
    await client.callTool({ name: 'list_log_trackers', arguments: { appName: 'backend', methodName: 'save' } });
    assert.equal(calls[4].path, 'trackers');
    assert.equal(calls[4].options.query.methodName, 'save');
    for (const args of [
      { size: 101 }, { logLevel: ['INVALID'] }, { timestamp_from: 'yesterday' },
      { timestamp_from: '2026-11-23T12:00:00', timestamp_to: '2026-11-23T10:00:00' },
    ]) {
      const result = await client.callTool({ name: 'list_logs', arguments: args });
      assert.equal(result.isError, true);
    }
    assert.equal(calls.length, 5);
  } finally {
    await client.close();
    await server.close();
  }
});

test('starts over stdio and advertises tools without contacting the backend', async () => {
  const client = new Client({ name: 'stdio-test', version: '1.0.0' });
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [fileURLToPath(new URL('../src/index.js', import.meta.url))],
    env: { MY_TOOLS_TOKEN: 'test-only-token', MY_TOOLS_API_URL: 'http://localhost:8080' },
    stderr: 'pipe',
  });
  try {
    await client.connect(transport);
    const { tools } = await client.listTools();
    assert.ok(tools.some((tool) => tool.name === 'create_task'));
    assert.ok(tools.some((tool) => tool.name === 'set_task_status'));
  } finally {
    await client.close();
  }
});
