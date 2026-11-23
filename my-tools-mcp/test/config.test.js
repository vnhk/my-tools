import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadConfig } from '../src/config.js';

test('loads a local dotenv file and prefers it over inherited credentials', () => {
  const directory = mkdtempSync(join(tmpdir(), 'my-tools-mcp-config-'));
  try {
    const path = join(directory, '.env');
    writeFileSync(path, 'MY_TOOLS_TOKEN="local-test-token"\nMY_TOOLS_API_URL=http://localhost:9091\n');
    const env = loadConfig({ MY_TOOLS_TOKEN: 'inherited-test-token' }, path);
    assert.equal(env.MY_TOOLS_TOKEN, 'local-test-token');
    assert.equal(env.MY_TOOLS_API_URL, 'http://localhost:9091');
    assert.deepEqual(loadConfig({ MY_TOOLS_TOKEN: 'fallback' }, join(directory, 'missing')), { MY_TOOLS_TOKEN: 'fallback' });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
