# Operator deployment preparation

This recipe creates no infrastructure. Approve the [budget](../docs/HOSTING-COSTS.md)
first. Visitors need only a browser and optionally their MCP client.

## Install the runtime

Use dedicated Linux x86-64, Docker Engine, gVisor `runsc`, Python 3.11+, Caddy
and persistent disk. Follow official [Docker](https://docs.docker.com/engine/install/),
[gVisor](https://gvisor.dev/docs/user_guide/install/) and [Caddy](https://caddyserver.com/docs/install)
instructions. Retain gVisor's sidecar binaries. Ordinary Docker is not the
production sandbox used here.

Extract a verified source release into `/opt/openkatana`:

```sh
cd /opt/openkatana
python3 -m venv .venv
.venv/bin/python -m pip install '.[hosted,vision,text]'
docker build -f deploy/Dockerfile.worker -t openkatana-worker:0.1.0rc2 .
```

The image installs Debian Chromium/FFmpeg and the complete official Blender
4.5.14 LTS runtime, verified against its published SHA-256. Their licences remain
under `/usr/share/doc` and `/opt/blender`. The Debian Blender build lacks the
Cycles denoiser and does not match the reusable material helpers. No generation
weights are downloaded. Retain
OpenKatana notices and record the tested image digest/package inventory. Use that
digest in `worker_image` for deployment instead of a mutable tag.

Create users `openkatana` and `openkatana-worker`, shared group `openkatana`, and
group-owned `/srv/openkatana` with mode 2770. Only the worker belongs to Docker's
privileged group. Copy `hosting.example.json` to `/etc/openkatana/hosting.json`,
readable only by operator/group, and set the real HTTPS origin. Keep secrets out
of Git. Allow space for snapshots and RAM for tmpfs plus the renderer.

```sh
sudo -u openkatana-worker /opt/openkatana/.venv/bin/openkatana-hosted \
  --config /etc/openkatana/hosting.json check
```

Preflight checks Docker/runtime/image and single-account model network isolation.
Per-account networks are checked on model jobs. It does not validate DNS, OAuth,
all models or real clients.

## HTTPS, accounts and MCP

Review/install the supplied systemd units and substitute the Caddy domain. Start
them only after deployment approval. The app binds 127.0.0.1:8090 and checks the
public Host/Origin preserved by Caddy. Expose HTTPS/HTTP and restricted SSH only,
never Docker, app or Comfy ports. One web process and one runner are supported.
The default pilot limits are ten accounts, one active job, 2 GiB workspaces and
256 MiB uploads. Add edge abuse controls before unrestricted registration.

```sh
sudo -u openkatana /opt/openkatana/.venv/bin/openkatana-hosted \
  --config /etc/openkatana/hosting.json invite --name Reviewer \
  --out /srv/openkatana/reviewer-invitation.json
```

Deliver `access_key` privately. It is single-use and expires in seven days.
Sessions last twelve hours; Connect AI manages seven-day MCP keys. Returning
users need a fresh invitation or OAuth. To preserve an existing invite account,
use `invite --user ACCOUNT_ID --out NEW_PRIVATE_FILE` instead of `--name`.
This invalidates that account's earlier unused invitations. Keep the account ID
from its original invitation. OAuth and invite accounts are separate identities;
automatic linking/migration between them is not implemented.

OAuth requires issuer/JWKS/authorization/token URLs and a public PKCE browser
client ID. Register `PUBLIC_URL/auth/callback`, audience `PUBLIC_URL/mcp`, RS256
and scope `openkatana`. Allow the browser origin at the token endpoint. MCP
clients require their own compatible registration/discovery; a browser client
ID does not register every AI client. Verify actual target clients.

Auth0 is one candidate with a free pilot tier. When using it, configure the API
identifier as the exact `PUBLIC_URL/mcp` audience and enable its RFC 8707 Resource
Parameter Compatibility Profile. Our browser and MCP clients send `resource`;
an opaque token without the correct audience is rejected. Decide between
pre-registered clients and dynamic client registration, with provider abuse
controls. See [Auth0's MCP authorization guidance](https://auth0.com/blog/adding-ui-auth0-secured-mcp-server-skybridge/).
No Auth0 tenant or client has been created or verified by this preparation.

## Optional model services

Multiple accounts require `{user}` in each setting:

```json
{
  "comfy_proxy": "http://comfy-{user}:8000",
  "comfy_native": "http://comfy-{user}:8188",
  "model_network": "openkatana-model-{user}"
}
```

It expands to the account's 32-character ID. Provision an internal Docker network
and Comfy service for each account with no other tenants or shared input/output
directories. GPU allocation, model lifecycle, reviewed nodes and licensed weights
remain operator work. Missing services fail clearly. Remote GPU providers need
a private gateway and validation. Paid cloud jobs are disabled; never inject
provider credentials into authored-code workers.

For package-local inference such as transcription, build a separate reviewed
image with the optional package and licensed cached weights. Its cache must be
readable in the image; the worker does not inherit the operator's home directory.
Run `get_capabilities` and a real fixture in that image. Generic workflow schemas
are not evidence that weights, nodes, VRAM capacity or provider access are ready.

## Validation and operations

Run `python scripts/test_hosted_live.py --out work/hosted-check` with disposable
data. Review screenshots/video and repeat an edit through actual HTTPS and MCP.
Check cancellation, restart, quotas, account separation and installed model jobs.
Restart marks unfinished jobs interrupted and stops orphan workers; no blind retry.

For consistent backups, stop both services and confirm no worker is running.
Back up all `/srv/openkatana` and private configuration, including SQLite and WAL
files together. Encrypt backups and rehearse restore on an isolated host before
accepting valuable media. Resume after the snapshot.

Publish retention/deletion terms before onboarding. No automatic deletion is
performed; operator-assisted removal must cover workspace, database records and
expired backups. Monitor storage, latency, errors and model spending. Keep small
limits until load tests establish capacity. The configuration is not a security audit.
