# Hosting budget — 21 October 2026

Nothing is deployed or purchased. Figures are USD before tax, domain, identity
provider and usage overages. Recheck region/checkout prices before provisioning.
These estimates are not an approved spending limit.

| Component | Specification | Published price |
| --- | --- | --- |
| Suggested pilot | DigitalOcean Basic: 8 vCPU, 16 GiB RAM, 320 GiB SSD | $96/month; $0.14286/hour |
| Optional backup bucket | Spaces: 250 GiB storage, 1 TiB outbound | $5/month |
| Optional identity provider | Auth0 Free, subject to its plan and connection limits | $0/month |
| Sustained CPU alternative | CPU-Optimized: 8 vCPU, 16 GiB RAM, 100 GiB SSD | $168/month; $0.25/hour |

Sources: [Droplets](https://www.digitalocean.com/pricing/droplets),
[Spaces](https://www.digitalocean.com/pricing/spaces-object-storage).
Auth0's [current Free plan](https://auth0.com/pricing) includes up to 25,000
monthly active users. Provider configuration and actual MCP-client compatibility
have not been validated for this deployment. OpenKatana's pilot remains limited
to ten accounts regardless of the provider's larger allowance.
Basic suits a small queued pilot with bursty rendering. Dedicated CPUs suit
continuous workloads. Smaller $48/month 8 GiB hosts require reduced worker
limits and benchmarking. No render-speed guarantee has been established.

Budget **about $101/month for CPU hosting and optional backups**. Ten days of
VM time is about $34.29 before other items. Storage may remain billable with
compute stopped. Domains are separate. Workspaces use persistent local disk;
Spaces is a possible encrypted backup destination, not an implemented live filesystem.

| GPU example | VRAM | Pod rate | 20 active hours |
| --- | --- | --- | --- |
| RTX 4090 | 24 GB | $0.89/hour | $17.80 |
| L40S | 48 GB | $1.09/hour | $21.80 |
| A100 PCIe | 80 GB | $1.79/hour | $35.80 |

Source: [Runpod pricing](https://www.runpod.io/pricing), updated 8 October 2026.
Region, cloud type, availability, storage and networking affect the actual bill.
These are examples, not a configured Runpod adapter or proof a model fits.
They budget one active GPU instance, not a separate always-on GPU for every account.
An always-on RTX 4090 for 720 hours would cost $640.80 before storage.

Choose models and measure VRAM before renting. Remote GPU providers also need
a validated private gateway; current workers expect an account-specific internal
network. No automatic GPU provisioning is implemented. Paid image/video APIs
are a separate alternative, disabled online pending a credential/spending broker.
The user's AI subscription is separate too.

Before deployment, choose domain/region, CPU plan, account/storage limits,
identity provider, enabled models and a hard budget. Verify actual HTTPS/MCP
clients, backup restore and model jobs on that infrastructure before opening it.
