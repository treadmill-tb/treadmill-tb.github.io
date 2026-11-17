---
title: "Jobs, leases & restarts"
description: "What a job request contains, how a job moves through its lifecycle, and how leases, expiry actions, restarts and resumes work."
weight: 40
---

A **job** is one run of an image on one host. You enqueue it with a job request; the scheduler places it on a host whose spec satisfies the job's host predicate and that carries an admissible image; the supervisor boots it; and it runs until it ends, is terminated, or its lease runs out.

## The job request

`POST /jobs` takes a `JobRequest`. `tml job create` builds one from its flags.

| Field | Meaning |
|---|---|
| `init_spec` | What kind of job this is (see below). Required. |
| `host_cel_predicate` | A CEL expression evaluated with the candidate host's spec bound as `host`. Defaults to `true`, matching every host. See [Writing host predicates](/docs/guides/host-predicates/). |
| `lease_duration` | The job's protected window, measured from its start. Absent, the deployment default applies (`GET /jobs/defaults` reports it as `lease_duration_secs`). |
| `lease_expiry_action` | `terminate` or `preempt`. Absent, `terminate`. |
| `restart_policy` | `{ "max_restarts": N }`. Required; `0` disables automatic restarts. |
| `parameters` | Map of name to `{ "value", "secret" }`, handed to the job. Required (may be empty). |
| `annotations` | Up to 64 key/value pairs of metadata, never handed to the job and changeable after enqueue. |
| `label` | Optional display label, 1 to 256 characters of ASCII letters, digits, spaces and `()_,.#-`. |
| `owner` | The caller or one of the caller's groups. Absent, the caller. |

### `init_spec`

`init_spec` is tagged by `type`:

- `image_set` with `set_id` and optional `generation`: run a member of an image set. Without `generation`, the latest generation is frozen onto the job at enqueue, and the member is chosen at dispatch for the selected host.
- `image` with `manifest_digest`: run a concrete catalog image.
- `resume` with `job_id`: resume a previously started job on its host, from its working directory. A resumed job's restart budget is always 0.
- `restart` with `job_id`: start afresh from a previously started job's image reference.

See [Images & image sets](/docs/concepts/images/) for how members are selected.

### Parameters

The job reads its parameters from `GET /jobs/{id}/environment` using its own job token; `tml daemon` writes each one to a file under `/run/tml/parameters/`. Flag a parameter `secret` to have its value redacted wherever the job is read back (it appears with a `null` value). `tml job create --param KEY=VALUE` sends non-secret parameters.

## Lifecycle

A job's `state` moves through:

```text
queued -> assigned -> initializing -> ready -> terminating -> finalized
```

| State | Meaning |
|---|---|
| `queued` | Enqueued, awaiting placement by the scheduler. |
| `assigned` | Placed on a host but not yet reported as executing. |
| `initializing` | The host is bringing the job up. `initializing_stage` is one of `starting`, `fetching_image`, `allocating`, `provisioning`, `booting`. |
| `ready` | The job is running and ready. |
| `terminating` | The job is shutting down. |
| `finalized` | Terminal; see `termination_reason`. |

`termination_reason` records why a job stopped: `workload_exited`, `workload_self_terminated`, `user_terminated`, `preempted`, `queue_timeout`, `execution_timeout`, `image_error`, `host_match_error`, `host_start_failure`, `host_dropped_job`, `host_unreachable`, `resume_failed` or `internal_error`.

Separately, `task_exit_status` (`pending`, `success`, `failure`, or `null` if never reported) is the workload's own verdict. Inside the job, report it with:

```shell
tml job set-exit-status success "all tests passed"
```

It may be reported any number of times while the job runs; each report replaces the last.

When you enqueue, the response includes `host_requirements`: how many hosts you may start on, how many match the predicate, how many errored, and which hosts could run the job. A job with no schedulable host is still accepted but stays queued. `tml job create` warns in that case and, unless you pass `--no-wait`, terminates the job instead of leaving it queued.

## Leases

The lease is the job's protected window, measured from `started_at`. `lease_expires_at` is `null` until the job starts. What happens at expiry depends on `lease_expiry_action`:

- **`terminate`**: a hard deadline. The job is stopped (`execution_timeout`).
- **`preempt`**: the job keeps running unprotected and becomes reclaimable. The scheduler may stop it (`preempted`) to place a job that has no idle host available. Absent that demand it runs on past its lease.

`tml job create --lease 2h` sets the duration; `--reclaimable` sets the expiry action to `preempt`.

### Changing a lease

`PATCH /jobs/{id}` changes a job's `label`, `annotations`, `lease` and `lease_expiry_action` together, or not at all. A lease change is a length from the job's start (`"30m"`), an adjustment (`"+30m"`, `"-10m"`), or an RFC 3339 end time. The switchboard may refuse it with `409` and a code: `job_terminating`, `not_started` (an absolute end for a job that has not started), `policy_limit` or `resource_pressure`, sometimes with the latest expiry it would grant.

```shell
tml job lease +30m
tml job lease 2h --job ^3fa9
tml job lease --until now+20m
tml job update --lease-until 2026-08-28T14:00:00Z --expiry-action preempt
tml job update --label "nightly run" --annotation ci.run=1234 --remove-annotation stale
```

`tml job lease` is shorthand for `tml job update --lease`/`--lease-until`. Both ask for confirmation before a change that would leave less than five minutes (skip it with `-y`). Every job carries a `revision`, bumped on each applied change and served as the `ETag` of `GET /jobs/{id}`. Pass `--if-revision N` to apply only if the job is still at that revision. The CLI exits with status 3 on a revision mismatch and 4 when the switchboard refuses the lease change.

## Restarts and resumes

A **restart policy** grants a job a number of automatic restarts after its host drops it. Each automatic restart enqueues a successor that inherits one fewer; `restart_policy.remaining_restarts` on the job reports what is left. `tml job create` always sends `max_restarts: 0`; set it through the API if you need automatic restarts.

A **resume** continues a terminated job on its host, from its working directory:

```shell
tml job create --resume ^3fa9
```

`--resume` cannot be combined with `--image` or `--host`. A resumed or restarted job records the job it continues as `predecessor`, and carries its predecessor's image reference.

## Working with jobs from the CLI

```shell
tml job create --image ubuntu-24.04 --lease 1h --label demo
tml job status
tml job wait
tml job list --mine --active
tml job terminate
```

`tml job create` waits until the job is ready and makes it the **active job**, which later commands use when `--job` is omitted. Pass `--no-set-active` to leave the active job unchanged. Run without `--image` or `--resume` in a terminal, it asks for the missing options. See the [CLI reference](/docs/reference/cli/) and the [jobs API](/docs/reference/api/jobs/).
