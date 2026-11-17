---
title: Installing tml
description: "Get the `tml` client and point it at your switchboard."
weight: 20
---

## With Nix

The Treadmill repository is a Nix flake, and `tml` is its default package. Install it into your profile:

```shell
nix profile install github:treadmill-tb/treadmill#tml
```

Or run it once without installing:

```shell
nix run github:treadmill-tb/treadmill#tml -- --help
```

## From source

`tml` is the `treadmill-cli` crate in the [repository](https://github.com/treadmill-tb/treadmill). The client features alone build with plain Cargo:

```shell
git clone https://github.com/treadmill-tb/treadmill
cd treadmill
cargo install --path cli --no-default-features --features user
```

The `user` feature is the client on your machine (login, contexts, SSH). The `daemon` feature is the agent that runs inside job images as `tml daemon`; you do not need it on your workstation.

## Configure

`tml` reads a TOML config file, by default `config.toml` in the `treadmill` XDG config directory (usually `~/.config/treadmill/config.toml`). Each top-level table is a profile, selected with `--profile`. The default profile points at the hosted switchboard:

{{< repo-file "cli/config.example.toml" >}}

Every key can also be set as a `TML_<KEY>` environment variable, which takes precedence over the file — for example `TML_SWITCHBOARD` or `TML_TOKEN`. The `--switchboard`, `--profile` and `--config` options override them for a single command.

## Check it works

```shell
tml --version
tml login
tml whoami
```

Next, follow the [Quickstart](/docs/get-started/quickstart/), or browse every command in the [CLI reference](/docs/reference/cli/).
