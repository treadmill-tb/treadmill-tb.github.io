---
title: "Writing host predicates"
description: "Select hosts for a job with a CEL expression over the host spec, and dry-run it against the fleet before you submit."
weight: 20
---

A job chooses its hosts with a single CEL (Common Expression Language) expression, its **host predicate**. The switchboard evaluates it against each candidate host's spec, bound as `host`, and the host may run the job only if the expression evaluates to `true`. `host.duts` is in scope, so one expression covers both the host and its attached devices under test.

Without a predicate a job matches every host (the default is `true`).

## Passing a predicate

From the CLI:

```shell
tml job create --image ubuntu-24.04 --host "host.site == 'cambridge'"
```

Through the API, set `host_cel_predicate` in the `POST /jobs` request body. Image-set members can carry an extra `predicate` in the same language, which narrows the member within its platform profile; see [Images & image sets](/docs/concepts/images/#generations).

## What `host` looks like

`host` is the host's spec, normalized to the latest version (`v2`). The fields are listed in the [host spec reference](/docs/reference/host-spec/); [Hosts & host specs](/docs/concepts/hosts/) gives an overview. Use `tml host show <host>` to see a real document.

## Examples

Site and resources:

```cel
host.site == 'cambridge' && host.resources.memory_mb >= 4096
```

A platform profile, and a physical-only field:

```cel
'rpi4-uboot-sd' in host.platform.profiles
```

```cel
host.platform.kind == 'physical'
  && has(host.platform.model)
  && host.platform.model.contains('Raspberry Pi 4')
```

Labels, guarded against an absent key:

```cel
'bench' in host.labels && host.labels['bench'] == 'nordic-bringup'
```

A host with a particular board attached:

```cel
host.duts.exists(d, d.vendor.contains('Nordic') && d.board == 'nrf52840dk')
```

A board reachable over SWD through a SEGGER probe:

```cel
host.duts.exists(d, has(d.debug) && d.debug.protocol == 'swd'
  && d.debug.probe.vendor == 'SEGGER')
```

Counting DUTs, and excluding quarantined ones:

```cel
host.duts.filter(d, d.arch.exists(a, a == 'cortex-m4')).size() >= 2
  && host.duts.all(d, !('quarantined' in d.labels))
```

A DUT whose `P0.11` pin the host can drive, through a `linux-gpiochip` controller:

```cel
host.duts.exists(d, 'P0.11' in d.gpio
  && 'digital_out' in d.gpio['P0.11'].modes
  && host.gpio_controllers[d.gpio['P0.11'].controller].driver == 'linux-gpiochip')
```

## Rules that keep predicates working

The spec is serialized to avoid most defensive guards, but three rules apply:

1. **Optional non-variant fields are always present**, as `null` when unset. `host.description == null` works without a guard.
2. **Variant-specific fields are absent on the other variant.** A `virtual` platform has no `model`, a `physical` one has no `hypervisor`. Guard with `has(host.platform.model)`.
3. **Map indexing errors on an absent key.** Labels, GPIO controllers and pins are maps that may be empty. Guard with `'key' in host.labels` before `host.labels['key']`.

`resources` fields are unsigned, so CEL sees them as `uint`. Comparing against a plain literal works (`host.resources.memory_mb >= 4096`), but arithmetic needs an unsigned literal:

```cel
host.resources.memory_mb / 1024u >= 8
```

### Errors mean "no match"

An evaluation error on a host means that host does not match. It is never a job failure. This includes a misspelled field (`d.borad`), an unguarded map index and an expression that does not evaluate to a boolean (`host.duts.size()`). Because a forgotten guard otherwise looks exactly like an empty fleet, the switchboard reports evaluation errors separately from non-matches. A syntax error is reported when the predicate is compiled, before anything is evaluated.

## Dry-run with `/hosts/match`

`POST /hosts/match` evaluates a predicate against the fleet without enqueueing anything:

```json
{
  "host_cel_predicate": "host.site == 'cambridge'",
  "init_spec": { "type": "image_set", "set_id": "<image-set-uuid>" }
}
```

`init_spec` is optional. With it, the switchboard also checks which hosts carry an admissible image-set member, which separates the two ways a job goes unplaced: the predicate matched nothing, or no member admits the hosts it did match. `owner` may name the group the job would run as; absent, it is the caller.

The response (`HostRequirementsReport`) contains:

| Field | Meaning |
|---|---|
| `authorized` | Hosts the owner may `start` jobs on. Zero is a permissions problem, not a query problem. |
| `predicate_matched` | Of those, how many the predicate admits. |
| `image_matched` | How many carry an admissible image-set member (null without an image set). |
| `errored`, `errors` | How many hosts failed to evaluate, and the first few error messages. |
| `compile_error` | Set when the predicate does not compile. |
| `schedulable` | The hosts that could actually run the job, by id. |
| `hosts` | Every authorized host with its per-host result. |

Counts cover only hosts the job's owner may `start` on, the same set the scheduler considers, so you cannot probe hosts you have no access to.

`POST /jobs` returns the same report as `host_requirements`. A job with no schedulable host is still accepted and sits queued until the fleet changes. `tml job create` prints the counts as a warning and, unless `--no-wait` is given, terminates such a job rather than leave it queued.

{{< callout title="Treat predicates as trusted input" >}}The in-process CEL runtime is not hardened against hostile input: deeply nested expressions can exhaust the stack. Until source limits land, the code base notes that predicate submission must be treated as trusted.{{< /callout >}}

See the [hosts API](/docs/reference/api/hosts/) for the full request and response schemas.
