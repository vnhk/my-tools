const reasons = new Map([
  ['ECONNREFUSED', 'Connection refused. Check whether the backend is running on the configured host and port.'],
  ['ENOTFOUND', 'DNS lookup failed. Check the backend hostname.'],
  ['EAI_AGAIN', 'DNS lookup temporarily failed. Check DNS connectivity.'],
  ['ETIMEDOUT', 'Connection timed out. Check backend availability, network access and firewall rules.'],
  ['UND_ERR_CONNECT_TIMEOUT', 'Connection timed out. Check backend availability, network access and firewall rules.'],
  ['UND_ERR_HEADERS_TIMEOUT', 'Timed out waiting for response headers.'],
  ['UND_ERR_BODY_TIMEOUT', 'Timed out reading the response body.'],
  ['ECONNRESET', 'The connection was reset by the server or an intermediary.'],
  ['UND_ERR_SOCKET', 'The connection closed unexpectedly. Check the server and reverse proxy.'],
  ['EHOSTUNREACH', 'Backend host is unreachable. Check network access or VPN connectivity.'],
  ['ENETUNREACH', 'Backend network is unreachable. Check network access or VPN connectivity.'],
  ['DEPTH_ZERO_SELF_SIGNED_CERT', 'TLS verification failed: self-signed server certificate. Configure a trusted CA certificate.'],
  ['SELF_SIGNED_CERT_IN_CHAIN', 'TLS verification failed: self-signed certificate in the chain. Configure a trusted CA certificate.'],
  ['UNABLE_TO_GET_ISSUER_CERT', 'TLS verification failed: issuer certificate is unavailable. Check the server certificate chain and trusted CA certificates.'],
  ['UNABLE_TO_GET_ISSUER_CERT_LOCALLY', 'TLS verification failed: unable to get local issuer certificate. Check the server certificate chain and trusted CA certificates.'],
  ['UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'TLS verification failed: unable to verify the server certificate. Check the server intermediate certificate chain.'],
  ['CERT_HAS_EXPIRED', 'TLS verification failed: certificate has expired. Renew the certificate and check the system clock.'],
  ['CERT_NOT_YET_VALID', 'TLS verification failed: certificate is not yet valid. Check the certificate and system clock.'],
  ['ERR_TLS_CERT_ALTNAME_INVALID', 'TLS verification failed: certificate does not match the backend hostname.'],
  ['ERR_SSL_WRONG_VERSION_NUMBER', 'TLS handshake failed. Check whether the configured port serves HTTPS.'],
]);

export function requestError(error, method, url) {
  const details = new Set();
  const seen = new Set();
  const pending = [error];
  // Native fetch wraps transport failures in cause, sometimes with IPv4/IPv6
  // AggregateErrors. Only expose known codes and static text, never raw messages.
  for (let count = 0; pending.length && count < 32; count++) {
    const current = pending.shift();
    if (!current || typeof current !== 'object' || seen.has(current)) continue;
    seen.add(current);
    if (reasons.has(current.code)) details.add(`${current.code}: ${reasons.get(current.code)}`);
    if (current.name === 'TimeoutError') details.add('Request timed out after 30 seconds (TimeoutError).');
    if (current.name === 'AbortError') details.add('Request was aborted (AbortError).');
    if (current.cause) pending.push(current.cause);
    if (Array.isArray(current.errors)) pending.push(...current.errors.slice(0, 16));
  }
  if (!details.size) details.add('Network request failed without a recognized error code. Check the API URL, backend availability and TLS configuration.');
  const retry = ['GET', 'HEAD'].includes(method) ? '' : ' Do not automatically retry writes; verify the backend state first.';
  // Omit query values, headers and request/response bodies from diagnostics.
  return new Error(`Backend ${method} ${url.origin}${url.pathname} failed: ${[...details].join(' ')}${retry}`);
}
