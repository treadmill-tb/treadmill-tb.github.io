---
title: tml CLI
description: "Every `tml` command and option, generated from the CLI's own help."
weight: 10
layout: cli
source: cli/src/cli.rs
---

`tml` is the Treadmill command-line client. The same binary is also the agent that runs inside job images (`tml daemon`), which is where the in-job commands such as `tml job set-exit-status` come from. Options under **Global Options** apply to every command, and every config key can also be set as a `TML_<KEY>` environment variable.
