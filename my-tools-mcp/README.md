# My Tools MCP

Local stdio MCP adapter for the existing Project Management and Logs REST APIs. No backend
changes, listening port, model API key, or public MCP deployment are required.
The AI client starts this process and communicates over stdin/stdout.

## Setup

Requires Node.js 20 or newer (prefer a currently supported Node.js LTS).

```sh
cd my-tools-mcp
npm install
npm test
```

Start the My Tools backend separately. Obtain a JWT using the application's
normal login flow (including OTP when enabled). Set these variables in the MCP
client's process environment:

- `MY_TOOLS_API_URL`: backend origin, for example `http://localhost:8080`.
  Do not append `/api`. An optional deployment path prefix is supported.
- `MY_TOOLS_TOKEN`: the raw login JWT, without the `Bearer ` prefix.

`.env.example` documents the variables; `.env` files are **not automatically loaded**.
Use HTTPS for a backend outside localhost. Redirects are rejected to avoid forwarding
credentials elsewhere. Keep normal TLS certificate validation enabled.

## Client configuration

For MCP clients accepting an `mcpServers` configuration, adapt this example using
the absolute path to your checkout and your installed Node.js executable:

```json
{
  "mcpServers": {
    "my-tools": {
      "command": "node",
      "args": ["/absolute/path/to/my-tools/my-tools-mcp/src/index.js"],
      "env": {
        "MY_TOOLS_API_URL": "http://localhost:8080",
        "MY_TOOLS_TOKEN": "YOUR_LOGIN_JWT"
      }
    }
  }
}
```

The exact configuration location and format depend on the client. Store real
credentials in private client configuration outside version control. Do not put
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

Creation requires `projectId` and `name`; defaults are `Open`, `Task`, and `Medium`.
Updates accept a `taskId` and a non-empty `changes` object. Optional fields include
description, assignee, priority, type, tags (a string), estimatedHours and dueDate.
Dates use backend local date-time without timezone, e.g. `2026-11-23T14:30:00`.
Explicit null clearing is unavailable because the backend PATCH ignores nulls.
Task moving, deletion, project modification and relationship writes are not exposed.

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

`npm test` runs HTTP adapter tests and an in-memory MCP client/server test against
a stub API. It does not connect to your live backend. To validate live integration,
connect a compatible MCP client, list projects, then create and update a disposable
task in a test project. No live writes are performed automatically.
