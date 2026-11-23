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
  assert.throws(() => createApiClient({ ...env, MY_TOOLS_TLS_VERIFY: 'flase' }), /must be true or false/);
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

test('does not retry failed writes or expose raw network errors', async () => {
  let count = 0;
  const api = createApiClient(env, async () => { count++; throw new Error('private-token'); });
  await assert.rejects(api('tasks', { method: 'POST', body: {} }), /Do not automatically retry writes/);
  assert.equal(count, 1);
});

test('distinguishes nested TLS, DNS, connection and timeout failures without leaking secrets', async (t) => {
  const cases = [
    ['ECONNREFUSED', /Connection refused/],
    ['ENOTFOUND', /DNS lookup failed/],
    ['EAI_AGAIN', /DNS lookup temporarily failed/],
    ['UND_ERR_CONNECT_TIMEOUT', /Connection timed out/],
    ['ECONNRESET', /connection was reset/],
    ['UNABLE_TO_GET_ISSUER_CERT_LOCALLY', /unable to get local issuer certificate/],
    ['UNABLE_TO_VERIFY_LEAF_SIGNATURE', /intermediate certificate chain/],
    ['DEPTH_ZERO_SELF_SIGNED_CERT', /self-signed server certificate/],
    ['CERT_HAS_EXPIRED', /certificate has expired/],
    ['ERR_TLS_CERT_ALTNAME_INVALID', /does not match/],
  ];
  for (const [code, expected] of cases) {
    await t.test(code, async () => {
      const api = createApiClient(env, async () => {
        throw new TypeError('private-token', { cause: Object.assign(new Error('private-token'), { code }) });
      });
      await assert.rejects(api('projects', { query: { filter: 'confidential-query' } }), (error) => {
        assert.match(error.message, expected);
        assert.ok(error.message.includes(code));
        assert.ok(error.message.includes('GET http://localhost:8080/api/project-management/projects'));
        assert.doesNotMatch(error.message, /private-token|confidential-query|automatically retry writes/);
        return true;
      });
    });
  }
});

test('reports AbortSignal timeouts, aggregate connection failures and cyclic causes safely', async () => {
  const refusal = Object.assign(new Error('secret'), { code: 'ECONNREFUSED' });
  refusal.cause = refusal;
  for (const [failure, expected] of [
    [new DOMException('secret', 'TimeoutError'), /timed out after 30 seconds/],
    [new TypeError('secret', { cause: new AggregateError([refusal, refusal], 'secret') }), /ECONNREFUSED/],
  ]) {
    const api = createApiClient(env, async () => { throw failure; });
    await assert.rejects(api('projects'), (error) => expected.test(error.message) && !error.message.includes('secret'));
  }
});

test('preserves transport errors while reading a response and distinguishes invalid JSON', async () => {
  const api = createApiClient(env, async () => ({
    ok: true, status: 200,
    json: async () => { throw Object.assign(new Error('secret'), { code: 'UND_ERR_BODY_TIMEOUT' }); },
  }));
  await assert.rejects(api('projects'), /UND_ERR_BODY_TIMEOUT/);
  const invalid = createApiClient(env, async () => new Response('not json'));
  await assert.rejects(invalid('projects'), /invalid JSON response/);
});
