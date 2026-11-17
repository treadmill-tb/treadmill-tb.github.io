---
title: "Grants & groups"
description: "Owners, permissions and grants on hosts, jobs, image sources and image sets, and the subjects they apply to."
weight: 50
---

Access in Treadmill is decided per resource. Each host, job, image source and image set has an **owner** and a set of **grants**, each of which gives one permission to one **subject**. An owner holds every permission on its resource implicitly, and so does a global admin.

## Subjects

A subject is anything that can own a resource or hold a grant. The API reports a subject's kind as one of:

| Kind | What it is |
|---|---|
| `user` | A human account, or a bot user (see below). |
| `group` | A group of users. |
| `system` | Built-in subjects, such as the `system` subject that can own standard image sets. |
| `job` | A running job, acting with its own job token. |

Two well-known subjects matter in practice:

- **`everyone`**: a built-in group that every subject is implicitly a member of. Granting a permission to `everyone` makes it public, on any kind of resource (hosts, jobs, image sets, image sources). A public image source is one that grants `everyone` `use`. `everyone` owns nothing; it exists only to be a grantee.
- **`system`**: only a global admin may hand an image set to `system`, which marks it as a standard image maintained by the switchboard's admins.

Owners may be `null`. An orphaned resource is manageable only by global admins.

## Groups

A user can belong to groups, including transitively, through nested groups or a linked GitHub organization. `GET /users/me` lists every group you belong to, with how each membership arose in `source` (for example `direct` or `github_org`).

Groups matter in three places:

- A group can own a host, job or image set and hold grants like a user.
- A job's `owner` may be the caller or any group the caller belongs to; ownership decides who can later read, stop and manage the job.
- `tml job list --groups` lists jobs owned by one of your groups, and `--shared` lists jobs granted to you or your groups.

## Permissions by resource

### Hosts

| Permission | Allows |
|---|---|
| `read` | Reading the host: its info, listing and spec. |
| `start` | Enqueuing jobs that run on the host. |
| `manage` | Privileged operations: changing its operational state (maintenance), writing a new spec revision, changing its owner, managing its grants. |

The scheduler only places a job on hosts the job's owner may `start` on. `POST /hosts/match` counts only those hosts too, so a caller cannot probe hosts it has no access to.

Some host grants are fixed in place by the switchboard (`revocable: false` in `GET /hosts/{id}/grants`). Nobody can revoke them; they are removed only with the host.

### Jobs

| Permission | Allows |
|---|---|
| `read` | Reading the job: its info, listing and console logs. |
| `stop` | Requesting the job's termination. |
| `manage` | Privileged operations, such as resuming or restarting it. Minting service tokens (and so SSH to the job) and sending serial console input also require `manage`. |

A job's own token holds `read` and `stop` on that job, which is how `tml job terminate` works from inside a job.

### Image sources

| Permission | Allows |
|---|---|
| `use` | Pulling the image from this source, and so running jobs that resolve to it. |
| `manage` | Managing the source's grants and deleting it. |

### Image sets

| Permission | Allows |
|---|---|
| `use` | Running a job that references the set, and so its member images. |
| `manage` | Creating generations and managing grants. |

A set grant is necessary but not sufficient: to run a member image you also need `use` on some source of that image. The generation inspect route flags members that some grantee cannot reach (`usable_by_grantees: false`). See [Images & image sets](/docs/concepts/images/#usability).

## Managing grants

Grants are managed through the API, by a subject holding `manage` on the resource:

| Resource | List / grant | Revoke |
|---|---|---|
| Host | `GET`/`POST /hosts/{id}/grants` | `DELETE /hosts/{id}/grants/{subject_id}/{permission}` |
| Image source | `GET`/`POST /images/{digest}/sources/{source_id}/grants` | `DELETE /images/{digest}/sources/{source_id}/grants/{subject_id}/{permission}` |
| Image set | `GET`/`POST /image-sets/{id}/grants` | `DELETE /image-sets/{id}/grants/{subject_id}/{permission}` |

A grant request carries a `subject_id` and a `permission`:

```json
{ "subject_id": "<user-or-group-uuid>", "permission": "start" }
```

Ownership changes go through `PUT /hosts/{id}/owner` and `PUT /image-sets/{id}/owner`. The viewer's own permissions on a resource are reported in its `permissions` field. See the [hosts](/docs/reference/api/hosts/) and [images](/docs/reference/api/images/) API pages.

## Bot users and API tokens

Human accounts are created by interactive login. For automation such as CI, a global admin creates a **bot user**: a non-human account that never logs in and authenticates only with API tokens.

1. `POST /users` with `{ "name": "...", "bot": true }` creates the bot (global admins only; `bot` must be `true`).
2. `POST /users/{id}/tokens` mints a token for it, with an optional `comment` and `expires_at`. Omitting `expires_at` mints a token that never expires and stays valid until revoked. The secret is returned only in this response.
3. `DELETE /users/{id}/tokens/{token_id}` revokes a token.

`GET /users/{id}/tokens` (or `/users/me/tokens`) lists a user's sessions and API tokens without their secrets. A bot is granted access like any other user: add it to grants, or make it the owner of resources.

{{< callout title="Running in CI?" >}}`tml` reads a token from the `token` key of its config profile or, preferably, from the `TML_TOKEN` environment variable. Every config key can be set as `TML_<KEY>`, and environment variables take precedence over the config file.{{< /callout >}}
