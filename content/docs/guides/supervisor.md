---
title: "Running a supervisor"
description: "Boot an image on a standalone QEMU supervisor, run the full local dev stack, and find the supervisor configuration examples."
weight: 60
---

There are three ways to run a supervisor from this repository, from least to most infrastructure:

1. **Standalone**: one QEMU supervisor boots one image, with no switchboard, database or NATS.
2. **Devstack**: the whole control plane (switchboard, web console, NATS, gateway) plus a QEMU supervisor, locally.
3. **Against a real switchboard**: a supervisor with a config file and the `ws_connector`.

All commands run through the Nix flake. See [Architecture](/docs/concepts/architecture/) for how the pieces fit.

## Standalone QEMU supervisor

To boot an image and watch its console without the control plane:

```shell
nix run .#qemu-supervisor-local -- --image ghcr.io/<org>/<repo>:<tag>
```

The wrapper (`tools/local-supervisor.sh`):

1. starts a per-developer Zot registry on `127.0.0.1:5050`;
2. copies the image into it from the upstream registry with `skopeo`;
3. resolves the tag to a manifest digest;
4. renders a supervisor config with `coord_connector = "local"` and runs the QEMU supervisor, which boots exactly one job.

The guest console streams to your terminal. The job ends when the guest exits or when you press Ctrl-C, after which the registry is stopped and, unless `--keep` was given, the state directory is removed.

`--image` must include a registry host (for example `ghcr.io/...`), and may end in `:<tag>` or `@sha256:<hex>`. Without either, the tag `latest` is used.

### Options

| Option | Default | Meaning |
|---|---|---|
| `--image REF` | required | Image to run. |
| `--arch {x86_64\|aarch64}` | `x86_64` | Guest architecture. |
| `--no-kvm` | | Force TCG even when `/dev/kvm` is available. |
| `--mem SIZE` | `4G` | Guest RAM. |
| `--disk-max-bytes N` | `34359738368` (32 GiB) | Ceiling for the per-job writable overlay. |
| `--stop-after DURATION` | | Stop the job automatically, e.g. after `5m`. Otherwise it runs until the guest exits or Ctrl-C. |
| `--qemu-arg ARG` | | Extra raw QEMU argument. Repeatable. |
| `--keep` | | Do not wipe the state directory on exit. |

KVM is used when the guest architecture matches the host's, `/dev/kvm` is readable and `--no-kvm` is not given; otherwise QEMU uses TCG. The guest boots UEFI firmware supplied by Nix.

The state directory (registry store, configs, per-job overlays) is `$XDG_CACHE_HOME/treadmill-local-sup`, or `~/.cache/treadmill-local-sup`. Override it with `TML_LOCAL_SUP_DIR`, and the registry port with `TML_ZOT_PORT`.

Guest port 22 is forwarded to host port 2222, so once an image with an SSH server boots:

```shell
ssh -p 2222 <user>@127.0.0.1
```

The guest's `tml daemon` reaches the supervisor's daemon API at `http://10.0.2.2:3859` (QEMU's user-mode network address for the host), passed in through fw_cfg. With the `local` connector there is no switchboard, so the daemon runs without switchboard access.

## The full devstack

For the whole stack:

```shell
nix run .#devstack
```

`tools/devstack.sh` brings up, with state under `$XDG_CACHE_HOME/treadmill-devstack` (override with `TML_DEVSTACK_DIR`):

- PostgreSQL on a private Unix socket, initialized on first run;
- NATS with JetStream and a WebSocket listener, for log streaming;
- the switchboard on `http://localhost:8000` (`TML_SB_PORT`), which applies migrations on start;
- the job service gateway at `https://<service>-<job-id>.jobgw.localhost:8443`, with a self-signed certificate;
- the web console on `http://localhost:8080` (`TML_CONSOLE_PORT`);
- on Linux only: a Zot registry and a QEMU supervisor, seeded with a `tiny-efi` test image, a host, and a public `tiny-efi` image set whose member targets the host's `q35-virtio-uefi` profile.

The devstack enables a development-only mock login with built-in identities (`alice` is an admin; `bob` and `carol` are users). Open the web console, or point `tml` at the stack:

```shell
tml --switchboard http://localhost:8000 login --identity alice
```

GitHub login is enabled only if `TML_DEV_GITHUB_CLIENT_ID` and `TML_DEV_GITHUB_CLIENT_SECRET` are set, with the OAuth app's callback at `http://localhost:8000/api/v1/auth/github/callback`.

Press Ctrl-C to stop. To reset everything, delete the state directory. `nix run .#devstack-e2e` brings the stack up, runs a smoke test and shuts it down again.

{{< callout title="Changing the switchboard port" >}}The console's API origin is baked in at build time as `http://localhost:8000`. If you override `TML_SB_PORT`, the devstack warns that the console's API calls will fail.{{< /callout >}}

## Configuring a supervisor for a switchboard

A supervisor in production reads a TOML config file. The repository has a commented example for each supervisor:

- `supervisor/qemu/config.example.toml`
- `supervisor/nbd-netboot/config.example.toml`

Both share these sections:

- **`[base]`**: `supervisor_id` (the host's id), `coord_connector` (`ws_connector` or `local`), `job_switchboard_api_url` (the switchboard URL as the supervisor's jobs reach it), and optionally `job_address`, the job's IP address announced to the switchboard.
- **`[ws_connector]`**: `switchboard_uri`, and the host's supervisor `token` (32 bytes, base64), or `token_file` to read it from a file. The token is returned once by `POST /hosts`; see [Hosts & host specs](/docs/concepts/hosts/#writing-and-validating-specs).
- **`[oci_store]`**: `registry` and `store_root` of the local Zot daemon the supervisor pulls images through.
- **`[log_streaming]`** (optional): `chunk_bytes`, `flush_interval` and `job_log_level`; see [Logs & the serial console](/docs/guides/logs/#supervisor-side-tuning).

### QEMU

`[qemu]` sets `qemu_binary`, `qemu_img_binary`, `state_dir`, `daemon_api_listen_addr`, `working_disk_max_bytes`, an optional `start_script` and `stop_script`, and `qemu_args`. The arguments may use the placeholders `{job_id}`, `{job_workdir}` and `{disk_node}`; the supervisor prepends the `-blockdev` nodes for the image's backing chain, and you attach the disk by referencing `{disk_node}`. The example passes the daemon API address to the guest with `-fw_cfg name=opt/dev.treadmill.supervisor-url,string=http://10.0.2.2:3859`.

`[qemu.job_retention]` (optional) controls cleanup: when a job is removed, its working directory moves to `<state_dir>/retired` and is deleted by a later sweep once older than `grace_period`.

### NBD netboot

`[nbd_netboot]` sets `state_dir`, `daemon_api_listen_addr`, `nbd_server_listen_addr` (for `qemu-storage-daemon`, serving the `rootfs` and `bootfs` exports), `tftp_listen_addr` (for `nbdfatftpd`), `working_disk_max_bytes`, optional binary paths, and optional `start_script`/`stop_script` hooks, for example to power the board on and off. TFTP on port 69 needs `CAP_NET_BIND_SERVICE` or a lowered `net.ipv4.ip_unprivileged_port_start`. The optional `[nbd_netboot.serial_console]` section (`device`, `baud_rate`) streams the host's serial console.

The generated [configuration reference](/docs/reference/configuration/) lists every key.
