---
title: "Architecture"
description: "How the switchboard, supervisors, the in-image daemon, the CLI and the web console fit together."
weight: 10
---

Treadmill is a distributed hardware testbed. A central **switchboard** schedules jobs onto real or virtual **hosts**, each controlled by a **supervisor**, and users get an image-based, reproducible way to run workloads on them.

{{< repo-image path="doc/img/treadmill_architecture.drawio.svg" alt="Treadmill architecture diagram" >}}

## Components

{{< components-table >}}

## Switchboard

The switchboard (`switchboard/`, built as the `swx` binary) is the central coordinator. It owns the PostgreSQL database and serves the HTTP API under `/api/v1` that the CLI, the web console and running jobs all talk to. It is responsible for:

- authentication (OAuth login, session tokens, bot API tokens) and permission grants;
- the host inventory, including each host's versioned [host spec](/docs/concepts/hosts/);
- the image catalog: registered images, their registry sources, and [image sets](/docs/concepts/images/);
- the job queue and scheduler, which places queued [jobs](/docs/concepts/jobs/) on hosts whose spec satisfies the job's CEL host predicate;
- minting short-lived credentials for log streaming (NATS) and for reaching job services through gateways.

The full API is documented per tag under [API reference](/docs/reference/api/jobs/).

## Supervisors

A supervisor controls one host and runs the jobs the switchboard dispatches to it. The repository ships two:

- **`qemu`** (`supervisor/qemu`) runs each job in a QEMU virtual machine. Its images provide one role, `disk`: a whole, partitioned disk. The supervisor layers a per-job writable overlay of `working_disk_max_bytes` on top and attaches it through the configured QEMU arguments.
- **`nbd-netboot`** (`supervisor/nbd-netboot`) boots a physical host over the network. The host fetches its boot files over TFTP and mounts its file systems over NBD. Its images provide two roles: `rootfs` (the root file system) and `bootfs` (the FAT boot file system, also served over TFTP).

Both use a local OCI store: a per-server Zot registry that the supervisor asks to make a dispatched manifest digest present, and whose blobs it then opens directly from its storage root. Shared supervisor code (job lifecycle, console capture, log publishing, working-directory retention, the daemon API) lives in `supervisor/lib`.

See [Running a supervisor](/docs/guides/supervisor/) for how to start one.

## Connectors

A supervisor talks to its coordinator through a connector, selected with `coord_connector` in the supervisor's `[base]` config:

- **`ws_connector`** (`supervisor/connector/ws`) connects to the switchboard over a WebSocket at `/hosts/{id}/connect`, authenticating with the host's supervisor token. That token is returned once, when the host is created with `POST /hosts`.
- **`local`** (`supervisor/connector/local`) is a one-shot, switchboard-less connector for development. It synthesizes a single job from command-line flags (manifest digest, repository, `--stop-after`), streams the guest console to the terminal, and tears down on guest exit or Ctrl-C. No Postgres, NATS or switchboard is involved.

## Daemon API and `tml daemon`

Inside a running job, the `tml` binary runs as an agent: `tml daemon`. It connects to the supervisor's **daemon API** (`supervisor/lib`), a small HTTP API with two operations:

- `GET /job` returns the job's id and, when the supervisor has a switchboard, the switchboard base URL and a job token.
- `PUT /job/ready` reports that the job is ready.

The daemon finds the supervisor with `--supervisor-url`, or, under QEMU, from the `opt/dev.treadmill.supervisor-url` fw_cfg entry that the supervisor's QEMU arguments set. With the job token it fetches the job's environment from the switchboard and writes it under `--job-info-dir` (default `/run/tml`): `job-id`, `host-id`, `host-spec.json`, a `parameters/` directory, and the gateway key material. It then serves a D-Bus interface (`dev.treadmill.Daemon`) and announces the job's services from `--services-dir` (default `/etc/tml/services.d`). See [Exposing job services](/docs/guides/job-services/).

Inside a job, `tml job terminate`, `tml job reload-services` and `tml job set-exit-status success|failure [MESSAGE]` act on the job through the daemon.

The CLI crate has two features: `user` (login, contexts, SSH) for a user's machine and `daemon` for images. The `tml` package builds only `user`; the static `tml-static-*` packages build only `daemon`.

## The CLI and the web console

- **`tml`** (`cli/`) is the user-facing client: `tml login`, `tml job create|status|wait|list|update|lease|terminate`, `tml host list|show`, and the SSH family (`tml job ssh|exec|sftp|upload|download`, `tml ssh setup`). See the [CLI reference](/docs/reference/cli/).
- The **web console** (`console/`) is a React single-page app for the same API: jobs, hosts (including editing a host's spec), images, users and settings. It is hosted separately from the switchboard and calls it cross-origin, so the switchboard must list the console origin in `server.cors_allowed_origins` and `<console-origin>/login/callback` in `oauth.return_to_allowlist`.

## Log streaming over NATS

Supervisors capture each job's console output and publish it to a NATS server with JetStream, under subjects `logs.<job-id>.<channel>` (for example `serial` and `supervisor`) into a per-job stream `logs-<job-id>`. The switchboard holds a NATS account signing seed and mints short-lived, per-job bearer JWTs: a write token for the supervisor at dispatch, read tokens for viewers, and publish-only console-input tokens. Browsers connect through NATS's WebSocket listener (`log_streaming.websocket_url`); native clients use `nats_url`. See [Logs & the serial console](/docs/guides/logs/).

## User gateways

Jobs are not reachable from the internet directly. A job announces named services, and a request for one arrives at a stateless **gateway** as `<service>-<job-id>.<base_domain>`. The gateway admits it only with a switchboard-minted, EdDSA-signed token for that service, then proxies it to the job's address. The job's own reverse proxy validates the same token again, so reaching a service takes a valid token at both ends. SSH to jobs uses this path too, as an `sshws` service bridged by `tml job ws-proxy`. See [SSH, SFTP & exec](/docs/guides/ssh/) and [Exposing job services](/docs/guides/job-services/).
