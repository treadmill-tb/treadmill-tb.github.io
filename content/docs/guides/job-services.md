---
title: "Exposing job services"
description: "Declare services inside an image, announce them to the switchboard, and reach them through the job gateway with service tokens."
weight: 50
---

A job can expose network services, such as a web IDE or SSH over WebSocket, to its users. The job declares them in a directory, the in-image `tml daemon` announces them to the switchboard, and users reach them through a **job gateway** with a short-lived service token. The job itself is never reachable from the internet directly.

## How a request reaches a service

```text
client --(token)--> gateway: <service>-<job-id>.<base_domain>
       --(token)--> job's own reverse proxy --> service upstream
```

1. A user with `manage` on the job mints a token for one service: `POST /jobs/{id}/services/{service}/token`. Each mint is recorded as an audit event on the job.
2. The client connects to `<service>-<job-id>.<base_domain>` at one of the gateways, presenting the token.
3. The gateway is stateless and does not know about jobs. It checks the token's EdDSA signature against the switchboard's public key, its issuer, and that its audience is exactly the `<service>-<job-id>` label of the requested host. It then proxies to the job address the token carries.
4. The job's own reverse proxy validates the same token again and forwards to the service's upstream.

Checking the token at both ends means a sibling job on the same network cannot reach a service directly without a token by skipping the gateway.

## Declaring services in an image

`tml daemon` reads service declarations from `--services-dir`, by default `/etc/tml/services.d`. Each `*.json` file declares one service:

```json
{
  "name": "webterm",
  "label": "Terminal",
  "protocol": "webapp",
  "upstream": "unix//run/tml-ttyd/ttyd.sock"
}
```

| Field | Meaning |
|---|---|
| `name` | Identifies the service within the job: 1 to 16 characters, lowercase letters and digits, starting with a letter. No hyphens, so `<service>-<job-id>` always splits back at its first hyphen. |
| `label` | Optional human-readable text to display. |
| `protocol` | A token the client interprets to decide how to connect, e.g. `webapp` or `sshws`. The switchboard stores it without interpreting it. |
| `upstream` | Optional. The local address the job's reverse proxy forwards to, as a Caddy upstream (the example uses a Unix socket). It stays on disk and is never announced. |

Files are read in path order. A malformed file, an invalid name, or a name already claimed by an earlier file is skipped with a warning; it costs the job that one service and nothing else. If the directory does not exist, the job announces no services.

`tml job ssh` and `tml ssh setup` look for a service with protocol `sshws`. See [SSH, SFTP & exec](/docs/guides/ssh/).

## Announcing services

On startup, after reporting ready to the supervisor, `tml daemon` scans the directory and announces the full set with `PUT /jobs/{id}/services`, using the job's own token. The announcement replaces the job's previous set.

After changing the directory inside a running job, rescan and re-announce:

```shell
tml job reload-services
```

This asks the daemon over D-Bus (`dev.treadmill.Daemon`, on the system bus by default; `--dbus-bus session` selects the session bus) to rescan and announce again.

The job's announced services appear on the job (`services` in `GET /jobs/{id}`, and `tml job status`), each with its `name`, `label` and `protocol`.

## The in-job reverse proxy

When the deployment runs gateways, the job's environment includes gateway material, which `tml daemon` writes under `/run/tml`:

| File | Contents |
|---|---|
| `gateway-issuer` | The `iss` every service token carries. |
| `gateway-key.pem` | The switchboard's public key for verifying service tokens (PEM). |
| `gateway-key-id` | The key's identifier, carried as a token's `kid`. |
| `gateway-endpoints` | The gateways' `base_domain:port`, one per line. |

If `tml daemon` runs with `--caddy-config <PATH>`, it also renders Caddy vhost definitions for every declared service that has an `upstream`, so the image's Caddyfile can import them. Each vhost admits requests for `<service>-<job-id>.<base_domain>` only with a valid token, taken from the `tml_token` query parameter, the `X-Tml-Token` header, or the `__Host-tml_token` cookie, and reverse-proxies to the upstream. `--caddy-reload-command` is run after the file changes. The proxy is configured before the services are announced, so a token can never be minted for a service the job cannot yet serve.

The flake's `tml-caddy-static-*` packages are static builds of the same Caddy-with-JWT-plugin used for the gateway, for images to include; the images themselves are built in a separate repository.

## Getting a service token

`POST /jobs/{id}/services/{service}/token` requires `manage` on the job and returns:

| Field | Meaning |
|---|---|
| `token` | The signed token admitting the caller to this one service. |
| `endpoints` | Every gateway `hostname` and `port` the service is published under, primary first. Hostnames already include `<service>-<job-id>`. The same token works at each. |
| `expires_at` | When the token stops being accepted. |

Errors: `404` if the job announces no such service, `409` if it has no network address yet, and `503` if this deployment has no gateways.

An issued token is not revoked early by anything, including the job ending or your access being revoked; it simply expires. Mint again for a fresh one.

## Connecting from the CLI

`tml job ws-proxy <SERVICE>` mints (and caches) a token and bridges stdio to the service over a WebSocket, passing the token in the `X-Tml-Token` header. With `--listen-addr IP:PORT` it listens on a local TCP port instead and bridges each connection in turn:

```shell
tml job ws-proxy --job ^3fa9 --listen-addr 127.0.0.1:8022 shell
```

The SSH commands are built on this bridge. For a browser-facing service, open the endpoint URL with the token in the `tml_token` query parameter; the development gateway in `nix run .#devstack` then moves it into a `__Host-tml_token` cookie and redirects, so the token does not stay in the address bar.

## Deployment notes

The switchboard's `[job_gateway]` section configures gateways: the token `issuer`, the `endpoints` (each a `base_domain` and `port`) and the token lifetime (`token_ttl`). The signing key is an Ed25519 seed, which `nix run .#devstack` passes through the environment (`TML_JOB_GATEWAY__SIGNING_KEY`) rather than the config file. The devstack runs a Caddy-based gateway with a JWT plugin (the `job-gateway-caddy` package) at `https://<service>-<job-id>.jobgw.localhost:8443`, with a self-signed certificate. See the [configuration reference](/docs/reference/configuration/).
