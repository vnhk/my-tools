import test from 'node:test';
import assert from 'node:assert/strict';
import { createApiClient } from '../src/api-client.js';

const env = { MY_TOOLS_API_URL: 'http://localhost:8080', MY_TOOLS_TOKEN: 'private-token' };

test('maps API URL, query, bearer token and partial PATCH without redirects', async () => {
  const api = createApiClient(env, async (url, options) => {
    assert.equal(url.href, 'http://localhost:8080/api/project-management/tasks/123?page=0');
    assert.equal(options.headers.Authorization, 'Bearer private-token');
    assert.equal(options.method, 'PATCH');
    assert.equal(options.body, '{"status":"Done"}');
    assert.equal(options.redirect, 'error');
    return new Response('{"status":"Done"}', { status: 200 });
  });
  assert.deepEqual(await api('tasks/123', { method: 'PATCH', query: { page: 0, absent: undefined }, body: { status: 'Done' } }), { status: 'Done' });
});

test('requires credentials and encrypted remote connections', () => {
  assert.throws(() => createApiClient({}), /MY_TOOLS_TOKEN/);
  assert.throws(() => createApiClient({ ...env, MY_TOOLS_API_URL: 'http://example.com' }), /HTTPS/);
});

test('routes log requests with repeated filters and preserves deployment prefix', async () => {
  const api = createApiClient({ ...env, MY_TOOLS_API_URL: 'https://example.com/tools/' }, async (url, options) => {
    assert.equal(url.pathname, '/tools/api/logs');
    assert.deepEqual(url.searchParams.getAll('logLevel'), ['WARN', 'ERROR']);
    assert.equal(url.searchParams.get('message'), 'failed & retried');
    assert.equal(options.headers.Authorization, 'Bearer private-token');
    return new Response('{"content":[]}');
  });
  await api('', { scope: 'logs', query: { logLevel: ['WARN', 'ERROR'], message: 'failed & retried' } });
});

test('redacts backend errors and explains expired credentials', async () => {
  const api = createApiClient(env, async () => new Response('private-token internal stack', { status: 401 }));
  await assert.rejects(api('tasks'), (error) => /expired/.test(error.message) && !/private-token/.test(error.message));
});

test('does not retry failed writes or expose network error details', async () => {
  let count = 0;
  const api = createApiClient(env, async () => { count++; throw new Error('private-token'); });
  await assert.rejects(api('tasks', { method: 'POST', body: {} }), /Do not automatically retry writes/);
  assert.equal(count, 1);
});
