# My Tools MCP

Local stdio MCP adapter for the existing Project Management and Logs REST APIs. No backend
changes, listening port, model API key, or public MCP deployment are required.
The AI client starts this process and communicates over stdin/stdout.

## Setup

Requires Node.js 20 or newer (prefer a currently supported Node.js LTS).

```sh
cd my-tools-mcp
npm install
cp .env.example .env
npm test
```

Start the My Tools backend separately. Obtain a JWT using the application's
normal login flow (including OTP when enabled). Set these values in
`my-tools-mcp/.env`:

- `MY_TOOLS_API_URL`: backend origin, for example `http://localhost:8080`.
  Do not append `/api`. An optional deployment path prefix is supported.
- `MY_TOOLS_TOKEN`: the raw login JWT, without the `Bearer ` prefix.
- `MY_TOOLS_TLS_VERIFY`: defaults to `true`. Set `false` to skip certificate and
  hostname verification for a self-signed HTTPS backend. The connection remains
  encrypted, but the backend's identity is not verified. This setting applies
  only to this adapter's backend origin, not global Node.js TLS settings.

MCP automatically reads `.env` from its own directory, regardless of the client's
working directory. Values in this file override inherited environment variables.
If the file is absent, inherited environment variables remain a fallback.
Use HTTPS for a backend outside localhost. Redirects are rejected to avoid forwarding
credentials elsewhere. Certificate verification is enabled unless explicitly
disabled with `MY_TOOLS_TLS_VERIFY=false` in `.env`.

## Client configuration

For Codex, copy the table in `codex-config.toml.example` into the project's
`.codex/config.toml` (merge it if the file already exists). Open the repository
root as the client's working directory: the script path is relative to that
directory and does not depend on where the repository is cloned.
No `env` or `env_vars` entries are needed: MCP
loads its own `.env` file. Reload the MCP
connection or restart the client after configuration changes. The project must
be trusted for project-scoped configuration to apply.

For MCP clients accepting an `mcpServers` configuration and launching processes
from the repository root, use:

```json
{
  "mcpServers": {
    "my-tools": {
      "command": "node",
      "args": ["my-tools-mcp/src/index.js"]
    }
  }
}
```

If a client starts processes from another directory, configure its working
directory to the repository root. The exact configuration location and format
depend on the client. Store real
credentials in `my-tools-mcp/.env`, which is ignored by Git. Do not put
them in prompts. This process does not return its configuration to the model.
An AI client with separate terminal access may still be able to read local secrets.
The JWT grants the same backend access as the logged-in user; this adapter does
not create project-scoped credentials. When it expires, replace it and restart
the MCP process. Automatic login and token refresh are not implemented.

## Tools

| Tool | REST operation |
| --- | --- |
| `list_projects` | `GET /api/project-management/projects` |
| `get_project` | `GET /api/project-management/projects/{projectId}` |
| `create_project` | `POST /api/project-management/projects` |
| `list_tasks` | `GET /api/project-management/tasks` |
| `search_tasks` | `GET /api/project-management/tasks/search?projectId=...&q=...` |
| `get_task` | `GET /api/project-management/tasks/{taskId}` |
| `create_task` | `POST /api/project-management/tasks` |
| `update_task` | `PATCH /api/project-management/tasks/{taskId}` |
| `set_task_status` | `PATCH /api/project-management/tasks/{taskId}` |
| `list_logs` | `GET /api/logs` |
| `get_log_filter_values` | `GET /api/logs/app-names`, `/process-names`, `/module-names` |
| `list_log_trackers` | `GET /api/logs/trackers` |

### Log filters

`list_logs` accepts `applicationName`, `logLevel`, `processName`, and `moduleName`
as arrays. Values within an array are ORed; separate filters are ANDed.
Optional `message`, `className`, `methodName`, `packageName`, and global `filter`
use the backend's SQL LIKE matching (including `%` and `_` wildcards).
Use `timestamp_from` and `timestamp_to` for inclusive local date-time bounds
without timezone, such as `2026-11-23T10:00:00`.
`page`, `size` (1–100), `sort`, and `direction` control pagination and sorting;
defaults are the first 20 results, newest timestamp first.

Example `list_logs` arguments:

```json
{
  "applicationName": ["frontend"],
  "logLevel": ["WARN", "ERROR"],
  "timestamp_from": "2026-11-23T10:00:00",
  "message": "playback",
  "size": 50
}
```

Discover filter values with `get_log_filter_values`, passing `field` as
`applicationName`, `processName`, or `moduleName`. For trackers, use
`list_log_trackers` with required `appName` and optional exact `processName` /
`moduleName` and case-insensitive substring `className`, `methodName`, `message`.
Tracker queries do not support level or time filters; use `list_logs` for those.
Log access uses the existing JWT and backend permissions. Logs can contain
sensitive data and untrusted text. Tools expose only reads, not unbounded exports.

List operations accept zero-based `page` and `size` (1–100). `list_tasks` accepts
an optional project UUID. Search matches task name or number within one project,
with a backend limit of 50 results. Use UUIDs returned by list/search tools.

Project creation requires `name` and `number` (the project code); defaults are
`Open` and `Medium`. Check existing project codes before creating.
Task creation requires `projectId` and `name`; defaults are `Open`, `Task`, and `Medium`.
Updates accept a `taskId` and a non-empty `changes` object. Optional fields include
description, assignee, priority, type, tags (a string), estimatedHours and dueDate.
Dates use backend local date-time without timezone, e.g. `2026-11-23T14:30:00`.
Explicit null clearing is unavailable because the backend PATCH ignores nulls.
Task moving, deletion, project updates and relationship writes are not exposed.

## Example workflow

1. Ask the agent to list projects and find a task by number.
2. Read the task and its acceptance criteria.
3. Set `In Progress`, perform the work using the agent's own repository tools,
   and run appropriate tests.
4. Set `Done` only after verifying the work. Otherwise report the blocker.

This adapter does not execute code, start agents, reserve work, or verify that a
task is complete. It has no protection against concurrent edits. Do not retry
creation blindly after a timeout: the backend may already have saved the task.
Task descriptions are untrusted content and cannot override the user's instructions.

## Verification

Network failures report the HTTP method and endpoint (without query values),
plus recognized transport codes and hints, including refused connections, DNS
failures, timeouts, and TLS certificate errors. Raw exception messages, headers,
tokens and response bodies are not included. IPv4/IPv6 aggregate failures are
inspected as well. Writes are never retried automatically.

For a manual read-only check, run this from `my-tools-mcp/` in Bash or Zsh:

```sh
(
  set -a
  source .env
  set +a
  curl --show-error --fail-with-body --connect-timeout 10 --max-time 30 \
    "${MY_TOOLS_API_URL%/}/api/project-management/projects?page=0&size=100" \
    -H "Authorization: Bearer $MY_TOOLS_TOKEN" \
    -H "Accept: application/json"
)
```

Keep `.env` shell-compatible when using `source` (quote values containing spaces
or shell metacharacters). Do not enable shell tracing when running this command.
For curl error 60 or MCP issuer/certificate errors, check the server's full
certificate chain and the client's trusted CA store. For a private CA, obtain
the CA certificate from your administrator and pass `--cacert /path/to/ca.pem`
to curl. If deliberately using unverified self-signed TLS, set
`MY_TOOLS_TLS_VERIFY=false` in `.env` for MCP and add `--insecure` to curl.
The MCP setting does not change curl's behavior. After changing MCP code or `.env`,
restart its client-managed process to load the changes.

`npm test` runs HTTP adapter tests, MCP client/server tests and a local HTTPS test
with a temporary self-signed certificate generated by `openssl` (required on PATH).
It does not connect to your live backend. To validate live integration,
connect a compatible MCP client, list projects, then create and update a disposable
task in a test project. No live writes are performed automatically.
