---
title: "Hosts & host specs"
description: "What a host is, how its versioned host spec describes it, and the states a host can be in."
weight: 20
---

A **host** is one machine that runs Treadmill jobs: a QEMU virtual machine slot or a physical board setup, controlled by a [supervisor](/docs/concepts/architecture/#supervisors). The switchboard keeps two kinds of information about each host:

- **Operational state**, stored on the host's row: owner, liveness (last heartbeat), maintenance flag and the lease state of its current job.
- **The host spec**, an admin-authored, versioned JSON document describing what the host *is*: its site, platform, resources, attached devices under test (DUTs) and how they are wired.

The switchboard stores the spec, serves it to clients and to jobs (as `host-spec.json` in `/run/tml`, see [Architecture](/docs/concepts/architecture/#daemon-api-and-tml-daemon)), and binds it as `host` when evaluating a job's [CEL host predicate](/docs/guides/host-predicates/).

{{< callout title="No secrets in a spec" >}}Any subject holding `read` on a host sees the whole spec document. Do not put credentials or other secrets in it.{{< /callout >}}

## Host spec v2

The current version is `v2`. Writes must carry the latest version; stored documents written under an older version are upgraded on read, so clients, jobs and predicates only ever see `v2`. The full field-by-field schema is in the [host spec reference](/docs/reference/host-spec/), and the switchboard serves the same schema at `GET /hosts/spec-schema`.

At a high level, a `v2` document has these top-level fields:

| Field | Purpose |
|---|---|
| `spec_version` | Always `"v2"`. |
| `id` | Must equal the id of the host the document describes. |
| `name` | Display handle, e.g. `cam-rpi5-01`. Deliberately not unique. |
| `description` | Prose description, or `null`. |
| `site` | The site the host lives at, e.g. `cambridge`. |
| `location` | Free text within the site, e.g. `rack4/shelf2`, or `null`. |
| `platform` | The machine and the images it can boot (see below). |
| `resources` | `cpu_cores`, `memory_mb`, `storage_gb`: the ceiling available to a single job. |
| `labels` | Operator-defined string key/value labels. |
| `gpio_controllers` | GPIO controllers on the host, keyed by a name DUT pins refer to (e.g. `rp1`). |
| `duts` | The devices under test wired to the host, in operator order. May be empty. |

### Platform

`platform` is one of two variants, distinguished by `kind`:

- `physical`: `arch`, `profiles`, `vendor`, `model`.
- `virtual`: `arch`, `profiles`, `hypervisor` (e.g. `qemu`).

`profiles` lists the whole machine configurations the host can boot, such as `rpi4-uboot-sd`, `q35-virtio-uefi`, `q35-virtio-bios` or `netboot-nbd`. An image-set member matches a host by equality against one of these profiles; see [Images & image sets](/docs/concepts/images/). Profile names are governed by convention, not a registry.

### DUTs

Each entry in `duts` describes one board: `vendor`, `board` (a lowercase identifier such as `nrf52840dk`), optional `name` and `serial` (the board's own serial, not its probe's), `arch` (core architectures, e.g. `cortex-m4`), `connectivity` (e.g. `ble`, `usb`), an optional `debug` block (`protocol` such as `swd`, plus a `probe` with `vendor`, `model`, `serial`), an optional `console` (currently a `uart` with `device` and `baud`), `gpio` pins keyed by the DUT-side pin name (e.g. `P0.13`), and per-DUT `labels`.

GPIO controllers are declared once per host, under `gpio_controllers`, each with a `driver` (e.g. `linux-gpiochip`) and driver-specific `config`. A DUT pin names its controller and carries its own `config`, `modes` (`digital_in`, `digital_out`), `active` level, `inverted` and `drive` (`push_pull`, `open_drain`, `open_source`).

### Serialization rules

The spec is shaped so that predicates need few defensive guards:

1. Optional non-variant fields are always serialized, as `null` when absent.
2. Variant-specific fields are genuinely absent on the other variant (a `virtual` platform has no `model`), so reading one needs a `has()` guard.
3. Maps (`labels`, GPIO controllers and pins) may be empty, and indexing an absent key is an error, so guard with `'key' in host.labels`.

## Writing and validating specs

A host is created with `POST /hosts` (global admins only), which writes the host and revision 1 of its spec in one transaction and returns the supervisor's auth token. That token cannot be retrieved later. The spec's `id` becomes the host's id: the client supplies the UUID, so a spec is a self-contained document that can live in a git repository.

`PUT /hosts/{id}/spec` appends a new revision; the history keeps every revision and the newest is the one in force. Pass `?validate_only=true` to run the same checks without writing. A rejected document returns `422` with a dotted `path` to the offending field, such as `duts[0].debug.probe.serial`. Writing a spec requires `manage` on the host. See the [hosts API](/docs/reference/api/hosts/).

The web console also has a spec editor on each host's page.

## Host states

`tml host list` shows one state per host, derived from its operational fields:

| State | Meaning |
|---|---|
| `offline` | The supervisor has not heartbeat recently enough to be schedulable (`live` is false). |
| `maintenance` | An operator withheld the host from scheduling. It is neither dispatched onto nor preempted. |
| `busy` | Running a job that may not be reclaimed. |
| `reclaimable` | Running a job past its lease with expiry action `preempt`; the scheduler may stop it to place another job. |
| `idle` | Live, in service and with no job assigned. |

The API exposes the underlying fields on `GET /hosts` and `GET /hosts/{id}`: `live`, `maintenance`, `lease_state` (`idle`, `busy`, `reclaimable`), `last_seen_at`, and the current job's lease expiry. `PATCH /hosts/{id}` with `maintenance` takes a host out of or back into service.

## Inspecting hosts

```shell
tml host list
tml host list cambridge nrf52840dk
tml host show cam-rpi4-01
```

`tml host list` filters by terms that must all match: `^<hex>` for an id suffix, anything else for the name, state, site, platform, board or a `key=value` label. `--watch` refreshes the list. `tml host show` accepts a host name, UUID or `^<hex>` short id and prints the full spec.

Access to hosts is controlled by `read`, `start` and `manage` grants; see [Grants & groups](/docs/concepts/grants/).
