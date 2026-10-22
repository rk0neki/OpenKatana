# Security

OpenKatana Studio and its ComfyUI adapter are intended for a trusted, single-user
local machine. Do not make their loopback ports accessible through a public tunnel.
Authored JavaScript, Blender scripts and custom nodes are executable code;
review them before running them. Browser network restrictions are not an OS sandbox.

The separately packaged hosted pilot is **experimental and not deployed**.
Its CI fixtures are not a production security audit. Operators must validate
authentication, tenant isolation, resource limits, backups and dependency
configuration before running a public service. No public hosted service is
provided by this repository.

For a suspected vulnerability, use GitHub's **Security → Report a vulnerability**
on this repository if private reporting is available. Otherwise open an issue
requesting a private reporting channel without including exploit details,
credentials, private project files or personal information. Do not post active
secrets in a public issue. This project currently has no guaranteed response SLA.

Report the affected version, operating system and a minimal reproduction using
non-sensitive test data. Fixes target the latest release; older versions have no
separate long-term support commitment.
