import { config } from 'dotenv';
import { fileURLToPath } from 'node:url';

export function loadConfig(env = process.env, path = fileURLToPath(new URL('../.env', import.meta.url))) {
  // Resolve from this module, not the client's working directory. Never log values.
  const result = config({ path, processEnv: env, override: true, quiet: true });
  if (result.error && result.error.code !== 'ENOENT') {
    throw new Error('Cannot read my-tools-mcp/.env. Check file permissions.');
  }
  return env;
}
