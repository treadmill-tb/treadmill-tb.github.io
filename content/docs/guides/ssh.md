---
title: "SSH, SFTP & exec"
description: "Reach a running job over SSH through the job gateway, with tml subcommands or your system ssh client."
weight: 30
---

Jobs are not directly reachable from the internet. SSH to a job runs over a WebSocket: the job announces a service with protocol `sshws`, `tml` mints a short-lived service token from the switchboard, and connects through the [job gateway](/docs/concepts/architecture/#user-gateways) to the job's own proxy, which hands off to its SSH server. All of this is wrapped up in `tml`, either as `tml job ssh` and friends or as a `ProxyCommand` for the system `ssh`.

You need OpenSSH (`ssh`, and `sftp` for file transfer) on your `PATH`. Minting a service token requires `manage` on the job, which a job's owner holds.

## Choosing the job

Every command below takes `--job <JOB>`, either a full UUID or `^<hex>`, a suffix of one. Without `--job` they use the **active job**. `tml job create` sets the job it creates as active unless you pass `--no-set-active`. To change it:

```shell
tml job set-active ^3fa9
tml context job set ^3fa9
tml context job clear
tml context show
```

`tml job set-active` is an alias for `tml context job set`. The active job is stored per configuration profile.

## `tml job ssh`

```shell
tml job ssh
tml job ssh --job ^3fa9
tml job ssh uname -a
```

With no arguments it opens an interactive session. Anything after the options is passed to `ssh`, for example a command to run.

## `tml job exec`

```shell
tml job exec make test
```

Runs a command in the job over SSH and returns its exit status.

## `tml job sftp`, `upload` and `download`

```shell
tml job sftp
tml job upload ./firmware.bin
tml job upload ./firmware.bin /tmp/fw.bin
tml job download /var/log/test.log
tml job download /var/log/test.log ./logs/test.log
```

`upload` and `download` drive `sftp` with a one-line batch script. If you omit the destination, the file keeps its base name (in the remote working directory for `upload`, the current directory for `download`).

## Common options

All of `ssh`, `exec`, `sftp`, `upload` and `download` accept:

| Option | Meaning |
|---|---|
| `--job <JOB>` | Target job; defaults to the active job. |
| `--service <NAME>` | The announced service to connect to. Without it, `tml` picks the job's single `sshws` service, and fails if there are none or several. |
| `-l`, `--user <USER>` | Remote SSH user. Defaults to the profile's `user`, which defaults to `tml`. |
| `--ssh-opt <ARG>` | Extra argument for the `ssh`/`sftp` subprocess, inserted before the destination. Repeatable. |

```shell
tml job ssh -l root --ssh-opt -A
```

`tml` runs `ssh` with `-F /dev/null` so your own SSH config does not interfere, and with host-key checking and known-hosts files disabled (`StrictHostKeyChecking=no`, `UserKnownHostsFile=/dev/null`), batch mode, no connection sharing and `LogLevel=ERROR`. These fixed options take precedence over anything passed with `--ssh-opt`.

These commands produce a byte stream, so `-o json` and `-o jsonl` are not supported for them.

## Using your own `ssh` with `tml ssh setup`

`tml ssh setup` lets plain `ssh`, `scp`, `sftp` and tools built on them reach jobs by hostname:

```shell
tml ssh setup
ssh tml@<job-uuid>.job.treadmill.dev
```

It writes a tml-managed SSH config file (`ssh_config` in tml's XDG config directory, e.g. `~/.config/treadmill/ssh_config`) with one block per profile, between `# BEGIN tml profile <name>` and `# END tml profile <name>` markers. Each block matches `Host *.<domain>` for every domain in the profile's `ssh_domains`, sets `User` and a `ProxyCommand` of `tml ... ssh proxy '%h'`, and applies the same options as `tml job ssh`.

It then needs `~/.ssh/config` to `Include` that file. It shows the change as a diff and asks before applying it. If `~/.ssh/config` already exists, it keeps a copy of the original next to it with a `.tml-backup` extension.

| Flag | Effect |
|---|---|
| `-y`, `--yes` | Edit `~/.ssh/config` without asking. |
| `--print` | Only print the snippet; leave `~/.ssh/config` untouched. |

`--yes` and `--print` conflict. Without a terminal and without `--yes`, it prints the change and leaves `~/.ssh/config` alone. `tml ssh setup` also warns if `tml` is not on your `PATH`, since `ssh` has to be able to run the `ProxyCommand`.

### `ssh_domains`

The domains come from the profile's `ssh_domains` key in `config.toml`:

```toml
[default]
switchboard = "https://swb.treadmill.dev"
ssh_domains = ["job.treadmill.dev", "user-gw.treadmill.dev"]
```

`tml ssh setup` fails if the profile configures no `ssh_domains`. The hostname you connect to can take two forms:

- `<job-uuid>.<domain>`: connect to the job's single `sshws` service.
- `<service>-<job-uuid>.<domain>`: connect to a named service.

If the domain is that of one of the gateways the service is published under, `tml` connects through that gateway; if it is one of your `ssh_domains`, it uses the job's primary gateway.

## Bridging a port with `tml job ws-proxy`

`tml job ws-proxy <SERVICE>` is the bridge the commands above use. It connects stdio to a job service over a WebSocket, with the service token in an `X-Tml-Token` header. With `--listen-addr IP:PORT` it instead listens on a local TCP port and bridges each connection in turn, which is useful for tools that want a TCP endpoint:

```shell
tml job ws-proxy --listen-addr 127.0.0.1:2222 shell
```

Here `shell` is the name of the service, as the job announced it.

## Troubleshooting

- **"announces no sshws service"**: the job has not announced an SSH service (yet). `tml job status` lists its services; `tml job wait` waits until it is ready and reachable over SSH.
- **"has no network address yet"**: the job has not been placed or booted. Run `tml job wait`.
- **"has no job service gateway"**: this switchboard has no gateways configured, so jobs cannot be reached over SSH.

Service tokens are cached per job and service until they expire. See [Exposing job services](/docs/guides/job-services/) for how services and tokens work.
