---
title: Quickstart
description: "Sign in, start a job on a real board, and get a shell on it. This takes about ten minutes and assumes you have an account on a Treadmill switchboard."
weight: 10
numbered: true
---

## Install tml

`tml` is the Treadmill command-line client. It is packaged in the project's Nix flake:

```shell
nix profile install github:treadmill-tb/treadmill#tml
```

See [Installing tml](/docs/get-started/installing/) for other ways to get it and for pointing it at your switchboard.

## Sign in and set up SSH

`tml login` opens your browser to authenticate with the switchboard. `tml ssh setup` then hooks Treadmill into your system SSH client, so every job becomes a hostname.

```shell
tml login
tml whoami
tml ssh setup
```

{{< callout title="Running in CI?" >}}Skip the browser and set `TML_TOKEN` to an API token (see the [Users API](/docs/reference/api/users/)). Every config key can be set as a `TML_<KEY>` environment variable.{{< /callout >}}

## Start a job

In the console, choose **Enqueue Job**, or use `tml job create`. A job needs an image to boot and a host predicate: a CEL expression over each host's spec. This one asks for any host with an nRF52840 DK attached:

```cel
host.duts.exists(d, d.board == 'nrf52840dk')
```

Before you enqueue, the console checks the predicate against the fleet and tells you which hosts match. Labels are a map, so guard optional keys: `'rack' in host.labels`.

From the command line, the same job is:

```shell
tml job create --image [IMAGE-SET] --host "host.duts.exists(d, d.board == 'nrf52840dk')"
```

Without `--image`, `tml job create` asks for the missing options in your terminal. By default it waits until the job is ready and makes it your active job.

| Field | What it does |
| --- | --- |
| `init_spec` | The image to boot, or a previous job to resume or restart. |
| `host_cel_predicate` | Which hosts may run the job. |
| `lease_duration` | How long you hold the host, measured from the job's start. |
| `restart_policy` | Whether, and how often, a job dropped by its host is restarted. |

## Connect

Once the job is running, make it your active job and work on it. Commands that take a job default to the active one.

```shell
tml job set-active [JOB-ID]
tml job upload build/app.hex
tml job exec -- ./run-tests.sh
tml job ssh

# or, with plain ssh after `tml ssh setup`:
ssh tml@[JOB-ID].job.treadmill.dev
```

## Finish up

The job ends when its lease expires. To give the hardware back sooner, terminate it with `tml job terminate`. Inside the job, report whether the workload passed with `tml job set-exit-status success` (or `failure`) so it shows up next to the job in the console.
