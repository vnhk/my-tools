import { requestError } from './request-error.js';
import { Pool } from 'undici';

export function createApiClient(env = process.env, fetchImpl = fetch) {
  const base = new URL(env.MY_TOOLS_API_URL || 'http://localhost:8080');
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) {
    throw new Error('MY_TOOLS_API_URL must be an HTTP(S) URL without credentials, query or fragment.');
  }
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname);
  if (base.protocol === 'http:' && !loopback) {
    throw new Error('Use HTTPS for a non-local backend.');
  }
  const token = env.MY_TOOLS_TOKEN?.trim();
  if (!token || /\s/.test(token)) throw new Error('Set MY_TOOLS_TOKEN to a valid login JWT.');
  const tlsVerify = env.MY_TOOLS_TLS_VERIFY ?? 'true';
  if (!['true', 'false'].includes(tlsVerify)) {
    throw new Error('MY_TOOLS_TLS_VERIFY must be true or false.');
  }
  // A pool is bound to this backend origin. Never change global TLS settings.
  const dispatcher = base.protocol === 'https:' && tlsVerify === 'false'
    ? new Pool(base.origin, { connect: { rejectUnauthorized: false } })
    : undefined;

  return async function request(path, { method = 'GET', query = {}, body, scope = 'project-management' } = {}) {
    if (!['project-management', 'logs'].includes(scope)) throw new Error('Unsupported API scope.');
    const url = new URL(`${base.href.replace(/\/$/, '')}/api/${scope}${path ? `/${path}` : ''}`);
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) {
        for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(item));
      }
    }
    let response;
    try {
      response = await fetchImpl(url, {
        method,
        redirect: 'error',
        ...(dispatcher ? { dispatcher } : {}),
        signal: AbortSignal.timeout(30_000),
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/json',
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch (error) {
      throw requestError(error, method, url);
    }
    if (!response.ok) {
      const hints = {
        400: 'Invalid request data. Check field constraints and filters.',
        401: 'JWT missing, invalid or expired. Replace MY_TOOLS_TOKEN and restart MCP.',
        403: 'Access denied.',
        404: 'Resource not found or inaccessible.',
        409: 'Update conflict. Read the task again before retrying.',
      };
      // Never forward backend error bodies: they can contain credentials or internal details.
      throw new Error(`Backend HTTP ${response.status}: ${hints[response.status] || 'Request failed. Check backend logs.'}`);
    }
    if (response.status === 204) return { success: true };
    try {
      return await response.json();
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error('Backend returned an invalid JSON response. Verify the result before retrying writes.');
      }
      throw requestError(error, method, url);
    }
  };
}
