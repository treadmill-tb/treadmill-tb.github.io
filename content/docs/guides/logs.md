---
title: "Logs & the serial console"
description: "How a job's console output is streamed over NATS, how the web console shows it, and how to type into a job's serial console."
weight: 40
---

A job's console output, such as its serial console and the supervisor's own log messages, is captured by the supervisor and streamed through a NATS server with JetStream. The web console replays the stored history and then follows it live. Users with `manage` on a job can also type into its serial console.

Log streaming is optional for a deployment. When it is off, the token endpoints below return `503`.

## How logs flow

1. When the switchboard dispatches a job, it creates a JetStream stream for it, `logs-<job-id>`, and hands the supervisor a write token.
2. The supervisor publishes captured output to subjects `logs.<job-id>.<channel>`. A channel is a short lower-case name such as `serial` or `supervisor`.
3. A viewer asks the switchboard for a read token and runs an ordered consumer against the job's stream: it replays stored history, then follows live.

Tokens are short-lived bearer JWTs minted from the switchboard's NATS account signing seed. Each is scoped to one job and denies by default anything it does not explicitly grant. A token only needs to be valid when a connection is opened: an established connection is not dropped when the token expires, and clients request new credentials when they reconnect.

### Channels and views

Besides output channels, a supervisor writes a `meta` channel declaring **views**: the tabs a client shows, each fed by one or more channels, with a label, an order, whether it is the default, and whether it accepts input. Declarations are cumulative; a later one with the same id replaces the earlier one.

The supervisors in this repository declare:

| Supervisor | Views |
|---|---|
| `qemu` | **Serial console** (terminal, accepts input, default), **QEMU process** (QEMU's stdout and stderr) |
| `nbd-netboot` | **Serial console** (terminal, accepts input, default), **Storage daemon**, **TFTP server** |
| all | **Supervisor**: the supervisor's own tracing events for the job, as JSON lines |

A view is only shown if the job actually produced one of its channels. For `nbd-netboot`, the serial console comes from the optional `[nbd_netboot.serial_console]` section (`device`, `baud_rate`) of the supervisor config. For `qemu`, the supervisor wires up the serial console automatically when log streaming is enabled for the dispatch.

### Supervisor-side tuning

The optional `[log_streaming]` section of a supervisor's config controls how console output is cut into NATS messages: a message closes at `chunk_bytes` of output or `flush_interval` after its first byte, whichever comes first. `job_log_level` sets the threshold at or above which the supervisor's own tracing events are forwarded to a job's `supervisor` channel, independent of `RUST_LOG`. See the [configuration reference](/docs/reference/configuration/).

## Viewing logs in the web console

A job's page in the web console shows its log once the job has been placed on a host. There is nothing to connect to before that, since the stream is created at dispatch. It shows one tab per declared view: terminal views are rendered with a terminal emulator, so escape sequences in the output are interpreted, and text views as scrolling lines.

On connect, the console replays up to about 1 MiB of stored history by default, then follows live. Add `?replay=` to the job page URL to change that bound: a byte count with an optional `k` or `M` suffix (`?replay=256k`), or `0` for a live tail only. Across reconnects it resumes after the last message it received, so nothing is replayed twice or lost.

{{< callout title="Browser needs the WebSocket listener" >}}Browsers can only reach NATS over WebSocket. The switchboard's `log_streaming.websocket_url` must point at the NATS server's `websocket` listener (`wss://` in production, with the console's origin in that listener's `allowed_origins`). Without it, the console cannot stream logs even though log streaming is otherwise enabled.{{< /callout >}}

## Typing into the serial console

A view that accepts input, such as **Serial console**, offers to start an input session if you hold `manage` on the job and it has not finished. Keystrokes are published to the job's console-input subject over a separate, publish-only connection. There is no local echo: what you type comes back through the log stream like any other console output.

Console input is monitored. The switchboard provisions a recording stream for a job's console input before it mints an input token, so every byte sent is captured, and every token mint is recorded as an audit event on the job.

## Reading logs from your own client

Two endpoints hand out NATS credentials. Both are in the [jobs API](/docs/reference/api/jobs/).

### `POST /jobs/{id}/nats-log-token`

Requires `read` on the job. Returns:

| Field | Meaning |
|---|---|
| `token` | Bearer user JWT. Connect with the token alone, no nkey seed. |
| `websocket_url` | NATS WebSocket URL for browsers; absent if the deployment exposes none. |
| `nats_url` | Plain-TCP NATS URL for native clients; may be null. |
| `subject` | `logs.<job-id>.>`, covering all the job's channels. |
| `stream` | `logs-<job-id>`, the JetStream stream to consume. |
| `inbox_prefix` | `_INBOX.logs-<job-id>`. You must set this inbox prefix on your connection; the token does not cover the default `_INBOX.>`. |
| `jetstream_domain` | The JetStream domain, if the server has one. Usually absent. |
| `expires_in_secs` | Seconds until the token expires; request new credentials after this before opening a new connection. |

### `POST /jobs/{id}/nats-console-input-token`

Requires `manage` on the job. Returns a `token` that may only publish to `subject` (`console-in.<job-id>`), plus `websocket_url`, `nats_url` and `expires_in_secs` as above. Console input is kept outside the `logs.<job-id>.>` hierarchy, so read-token holders cannot see what was typed.

The `tml` CLI does not currently stream logs; use the web console or a NATS client with these credentials.
