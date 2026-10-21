# Local use and hosting

## Local Studio and MCP

Studio runs on the user's computer. An agent can use the CLI or the optional
stdio MCP server to access the same operation catalog and project workspace.
No public website, OAuth connector or OpenKatana account is needed. Follow
[setup](SETUP.md) and [MCP configuration](AGENT_INTERFACE.md#optional-mcp-setup).
The agent's MCP client must support launching local stdio servers.

The Studio Agent setup dialog provides the CLI bootstrap and an optional MCP
guide. Opening it does not register a server with an agent. The user or their
agent configures the client with the correct Python executable and workspace.

## Public website

A static host can serve a landing page, documentation and download links. It
cannot execute Python tools, FFmpeg, Chromium, Blender or access a visitor's
local media. Hosting the Studio HTML alone does not create a working editor or
a remote MCP endpoint. A public website can point visitors to the local setup.

## Hosted editor or remote MCP

This release does not implement a hosted multi-user editor or remote MCP
transport. The current server is intentionally bound to loopback. Do not expose
it with a public tunnel or change its bind address as a deployment shortcut.

A remote edition would need:

- An HTTPS service and a supported MCP Streamable HTTP transport, with client
  authentication and authorization appropriate to the selected clients.
- Per-user workspaces and storage, bounded uploads, retention and deletion.
- A durable render queue with resource limits, cancellation and job recovery.
- Isolated workers for authored scripts, plugins, browser rendering and Blender.
  Local trusted-script approval is not a multi-tenant sandbox.
- Server-side provider credentials, spending limits and explicit authorization
  for paid generation; credentials must never be shipped in the frontend.
- The required CPU/GPU runtime, FFmpeg and browser packages. GPU model workloads
  may run through configured Comfy endpoints instead of the web process.

Plan and test these services before accepting uploads or enabling remote tool
execution. Hosting costs depend on concurrency, render duration and storage;
no paid service is configured or started by the local setup script.

Protocol references: [local servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
and [remote servers](https://modelcontextprotocol.io/docs/develop/connect-remote-servers).
