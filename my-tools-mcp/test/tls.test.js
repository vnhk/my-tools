import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:https';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { once } from 'node:events';
import { createApiClient } from '../src/api-client.js';

test('self-signed HTTPS requires explicit opt-out and does not disable TLS globally', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'my-tools-mcp-tls-'));
  const keyPath = join(directory, 'key.pem');
  const certPath = join(directory, 'cert.pem');
  let server;
  try {
    execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes',
      '-keyout', keyPath, '-out', certPath, '-days', '1', '-subj', '/CN=localhost'], { stdio: 'ignore' });
    server = createServer({ key: readFileSync(keyPath), cert: readFileSync(certPath) }, (req, res) => {
      assert.equal(req.url, '/api/project-management/projects');
      assert.equal(req.headers.authorization, 'Bearer test-token');
      res.setHeader('Content-Type', 'application/json');
      res.end('{"content":[]}');
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const env = { MY_TOOLS_API_URL: `https://127.0.0.1:${server.address().port}`, MY_TOOLS_TOKEN: 'test-token' };
    const globalSetting = process.env.NODE_TLS_REJECT_UNAUTHORIZED;
    await assert.rejects(createApiClient(env)('projects'), /self-signed/);
    const insecure = createApiClient({ ...env, MY_TOOLS_TLS_VERIFY: 'false' });
    assert.deepEqual(await insecure('projects'), { content: [] });
    await assert.rejects(createApiClient({ ...env, MY_TOOLS_TLS_VERIFY: 'true' })('projects'), /self-signed/);
    assert.equal(process.env.NODE_TLS_REJECT_UNAUTHORIZED, globalSetting);
  } finally {
    if (server?.listening) {
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
    }
    rmSync(directory, { recursive: true, force: true });
  }
});
