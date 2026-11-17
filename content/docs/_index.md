---
title: Introduction
linkTitle: Introduction
description: "Treadmill is a distributed hardware testbed: book real boards and virtual machines, boot them from reproducible images, and work on them over SSH."
---

Treadmill uses a central **switchboard** to schedule jobs onto real or virtual hardware **hosts**, and gives you an image-based, reproducible way to run workloads on them. You say what to boot and which hosts qualify; the switchboard places the job, a **supervisor** next to the hardware brings the host up from your image, and the host is yours until the job's lease runs out.

## What you can do with it

- Run firmware and system tests on real boards wired to a host — the devices under test, or **DUTs** — without having the hardware on your desk.
- Ask for hardware by what it is, with a [CEL predicate](/docs/guides/host-predicates/) over each host's spec.
- Get a shell, SFTP and remote command execution on a running job with [`tml`](/docs/reference/cli/) or plain `ssh`.
- Stream a job's logs and serial console, and report whether the workload passed.
- Share hosts and images with other users and groups through [grants](/docs/concepts/grants/).

## Where to go next

- New here? Follow the [Quickstart](/docs/get-started/quickstart/) to start a job and connect to it.
- To understand the moving parts, read [Architecture](/docs/concepts/architecture/).
- Looking up a command, an endpoint or a field? The [reference](/docs/reference/) is generated from the Treadmill repository, so it matches the code.
