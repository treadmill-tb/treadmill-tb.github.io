---
title: "Images & image sets"
description: "OCI disk images pinned by digest, the registry sources they are pulled from, and image sets with generations per platform."
weight: 30
---

Every Treadmill job boots from an **image**: an OCI artifact holding disk or file-system layers. Jobs usually reference an **image set**, a mutable, named handle whose members are concrete images for different platforms.

## Images

A Treadmill image is an OCI image manifest in pure-artifact form: an empty config plus an `artifactType` (`application/vnd.treadmill.image.v2+json`). Each layer's media type names only its format:

- `application/vnd.treadmill.qcow2`
- `application/vnd.treadmill.raw`

What a layer is *used for* is its **role**, carried in the `dev.treadmill.role` annotation on the head layer of each chain. A qcow2 layer names the layer it backs onto with `dev.treadmill.qcow2.lower` and records its size in `dev.treadmill.qcow2.virtual-size`. Only the base of a chain may be raw.

Roles mean nothing to the format itself; each supervisor defines the roles it understands:

| Supervisor | Roles |
|---|---|
| `qemu` | `disk`: a whole, partitioned disk |
| `nbd-netboot` | `rootfs` (root file system) and `bootfs` (FAT boot file system) |

### Pinned by digest

The switchboard identifies an image by its OCI manifest digest, `sha256:<64 hex>`, never by a tag. A job that runs a concrete image names it with `manifest_digest`, and at dispatch the switchboard resolves the digest to registry locations for the supervisor. Tags appear only in tooling outside the switchboard; for example, the standalone supervisor resolves `--image repo:tag` to a digest before running it.

### Image sources

An image is registered by adding a **source** for its digest: `POST /images/{digest}/sources` with a `registry` (`host:port`) and `repository`. The first source registers the image; later ones add more places to pull it from. The switchboard checks that the source serves the image (`502` if it cannot be reached or does not).

The image itself is not owned. Ownership and permissions live on its sources: the caller owns the source it adds, and can grant `use` (pull the image from this source) or `manage` on it. A public source is one that grants `use` to the `everyone` subject. A source's `status` is `external`, `canonical` or `system`. See [Grants & groups](/docs/concepts/grants/).

## Image sets

An image set (`POST /image-sets`) is a mutable catalog entity with a `display_name` and, optionally, a globally unique `canonical_name` such as `ubuntu-24.04`. Only a global admin may give a set a canonical name. The creator owns the set; a global admin may hand it to the `system` subject, which marks it as a standard image maintained by the switchboard's admins.

`tml job create --image` takes an image set by UUID or canonical name.

### Generations

A set's membership changes only by appending a **generation** (`POST /image-sets/{id}/generations`): an immutable, full-replacement snapshot of its members. Each member has:

- `manifest_digest`: an already-registered image.
- `platform_profile`: the machine configuration the image is built for, e.g. `q35-virtio-uefi` or `rpi4-uboot-sd`. It is matched by equality against the host spec's `platform.profiles`.
- `predicate` (optional): a CEL refinement narrowing the member within its profile, e.g. `host.resources.memory_mb >= 16384`.

A member is admissible for a host if the host advertises its `platform_profile` and its `predicate`, if any, holds. The first admissible member in order is selected.

When a job references a set without a `generation`, the set's latest generation is resolved and frozen onto the job at enqueue. After a host is chosen, the switchboard selects the admissible member for that host and dispatches that concrete image. A job's `image.resolved_digest` records which image it actually ran.

### Architectures and platforms

Images are not tagged with an architecture directly. A member's `platform_profile` names a complete machine configuration "the way a target triple does", and a host's `platform.arch` records its CPU architecture. To serve several architectures from one set, add one member per profile. `ImageSetInfo.platforms` lists the profiles of the latest generation's members.

### Usability

The generation inspect route reports, per member, whether the viewer can reach some source of the image (`usable`) and whether every subject holding `use` on the set can (`usable_by_grantees`). The latter is the owner-facing health signal: `false` means some grantees cannot use that member in practice, because a set grant is necessary but not sufficient.

`POST /hosts/match` with an `init_spec` naming the set tells you, before you submit a job, how many hosts carry an admissible member. See [Writing host predicates](/docs/guides/host-predicates/#dry-run-with-hostsmatch).

## Building images with `image-util`

Images are built in a separate repository, which consumes this repository's flake for the `image-util`, `tml-static-*` and `tml-caddy-static-*` packages. `image-util` is the producer-side CLI over the image format:

- `image-util assemble -o <layout> --title <title> --layer ROLE=FORMAT:PATH ...` assembles blob files into a validated OCI image layout. The first blob of a role is its chain's base; each later one backs onto the one before it. Optional `--version`, `--description`, `--created`, `--revision` and `--documentation` set the standard `org.opencontainers.image.*` annotations.
- `image-util append --lower <layout> -o <layout> [--layer ROLE=FORMAT:PATH ...]` appends layers on top of an existing layout's chains, carrying its layers through by digest. Metadata is inherited from the lower image unless overridden; `org.opencontainers.image.base.name` defaults to the lower layout's manifest digest.
- `image-util verify <layout> [--chain ROLE=LAYERS ...] [--title ...]` checks a built layout's structural invariants, optionally asserting the exact roles and chain lengths.

```shell
image-util assemble -o ./out --title my-image --layer disk=qcow2:./disk.qcow2
image-util verify ./out --chain disk=1
```

After pushing the layout to a registry, register it with the switchboard by adding a source for its digest, then add it as a member of an image set generation. See the [images API](/docs/reference/api/images/).
