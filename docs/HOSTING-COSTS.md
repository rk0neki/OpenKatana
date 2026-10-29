# Competition demo budget — 29 October 2026

Scenario: up to ten invited reviewers, one queued render at a time, no live AI
generation. Nothing is deployed or purchased. Estimates are USD before tax,
domain registration, backup storage and transfer overages; verify the selected
region and plan at checkout.

## CPU-only demo

| DigitalOcean bundled Basic plan | Hourly | 3 days | 7 days | 10 days | Monthly cap |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 vCPU / 8 GiB / 160 GiB SSD | $0.07143 | $5.14 | $12.00 | $17.14 | $48 |
| 8 vCPU / 16 GiB / 320 GiB SSD | $0.14286 | $10.29 | $24.00 | $34.29 | $96 |

Prices: [DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets),
checked 29 October 2026. Short-run estimates multiply the hourly rate by elapsed
hours. These are bundled Basic plans, not separately priced v5 configurations.

**Suggested starting point: 16 GiB for the competition.** This is a capacity
estimate, not a measured rendering benchmark. The current worker has a 6 GiB
memory limit, four CPU equivalents and a 2 GiB workspace held in memory. The
larger host leaves room for the web service, operating system, Docker and snapshot
handling. Shared CPUs can vary in speed; heavy Blender scenes may queue for much
longer than ordinary timeline edits. Test representative scenes before inviting
judges. The 8 GiB option needs smaller job limits and a successful load test.

Budget about **$35 for ten days**, or **$96 for a full month**, for compute.
An optional backup bucket starts at **$5/month**, including 250 GiB storage and
1 TiB outbound transfer: [Spaces pricing](https://www.digitalocean.com/pricing/spaces-object-storage).
Allow about **$40 for ten days or $101/month** if reserving a full $5 for backups.
Backup copying, encryption and restore verification remain operator work.

The app already supports invitation keys, so this browser-only reviewer pilot
does not require a paid identity provider. OAuth-only AI clients require separate
identity-provider configuration and testing. Users' own AI subscriptions are
separate. No GPU or model-provider budget is needed for this selected scenario.

Billing continues while a Droplet is powered off; it ends when the Droplet is
destroyed. Preserve anything needed first. Snapshots and other retained storage
can remain billable. See [billing details](https://docs.digitalocean.com/products/droplets/details/pricing/).
Create the host near the judging window and set billing alerts. Alerts are not
an automatic spending cap.

## Limits and readiness

Keep the ten-account cap, one active worker, 256 MiB uploads and 2 GiB workspaces.
Use short demo clips: extracted frames can fill storage quickly. A static site
host alone cannot run this renderer; it needs Linux, Docker, gVisor, FFmpeg,
Chromium and optional Blender. Domain/DNS, HTTPS, invitation delivery, actual
remote clients, backup restore and representative rendering still need validation
on the deployed host. This budget is not production or competition eligibility
certification. See [deployment preparation](../deploy/README.md).

## If live AI generation is added later

Keep it outside the CPU-only demo budget. Runpod currently lists RTX 4090 at
$0.89/hour (24 GB VRAM), L40S at $1.09/hour (48 GB), and A100 PCIe at $1.79/hour
(80 GB): [Runpod pricing](https://www.runpod.io/pricing), checked 29 October 2026.
Twenty billed hours would add $17.80, $21.80 or $35.80 respectively before storage
and networking. Availability and model fit need checking. GPU billing covers
allocated time, not just successful generation.

Remote GPUs are not a drop-in configured service here: workers expect private,
account-isolated model networks. A private gateway and real model tests would
be additional work. Paid cloud execution remains disabled in the hosted pilot
until credential handling, per-user authorization and spending limits exist.
