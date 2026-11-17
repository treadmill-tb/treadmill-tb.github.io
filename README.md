# Treadmill website (treadmill.dev)

The marketing site and documentation for [Treadmill](https://github.com/treadmill-tb/treadmill), a distributed hardware testbed. Built with [Hugo](https://gohugo.io).

## Build

```bash
make          # fetch upstream, generate reference data, build into public/
make serve    # the same, then serve with live reload on :1313
NO_CLI=1 make # skip building tml (the CLI reference page will be empty)
```

Needs `git`, Python 3.11+ with PyYAML, Hugo extended (the version in `.hugo-version`), and a Rust toolchain to build `tml`.

## Staying in sync with Treadmill

The reference docs are not written by hand. `scripts/fetch-upstream.sh` checks out `treadmill-tb/treadmill` into `.treadmill/` (`TREADMILL_REF` picks a branch or tag), and `scripts/gen_upstream.py` turns it into `data/upstream/*.json`, which the templates render:

| Page | Source in the Treadmill repo |
| --- | --- |
| Reference › tml CLI | `tml --help` for every subcommand (built from `cli/`) |
| Reference › Switchboard API (one page per tag, plus Schemas) | `switchboard/api-spec/openapi.yaml` |
| Reference › Host spec schema | `treadmill-rs/protocol-schema/host_spec_latest.schema.json` |
| Reference › Configuration, Installing tml | `cli/`, `switchboard/`, `supervisor/*/config.example.toml` |
| Architecture: diagram and component table | `doc/img/treadmill_architecture.drawio.svg`, `AGENTS.md` |
| Footer: license and commit | `Cargo.toml`, git metadata |

The GitHub Actions workflow rebuilds nightly and on a `treadmill-updated` `repository_dispatch`, so upstream can trigger a rebuild on every merge.

## Layout

- `content/` — hand-written pages (Markdown). Front matter `description` is the lede under the title; `numbered: true` numbers the `##` headings (used by the Quickstart). Shortcodes: `callout`, `repo-file`, `repo-image`, `components-table`, `upstream`.
- `content/docs/reference/api/_content.gotmpl` — a content adapter that creates one page per OpenAPI tag.
- `data/landing.yaml` — landing page copy.
- `layouts/` — templates; `layouts/docs/` holds the docs shell and the reference layouts (`cli`, `api`, `api-tag`, `api-schemas`, `hostspec`, `config`).
- `assets/css/main.css` — all styles; the design tokens are the custom properties at the top.
- `assets/js/site.js` — copy buttons, the docs search (backed by `/search-index.json`), the mobile menu and TOC highlighting.

## Configuration

`hugo.toml` `[params]`: `consoleURL` (the hosted web console), `repo`, `siteRepo` (set it to show "Edit this page" links on hand-written pages), `upstreamBranch`. Any can be overridden at build time, e.g. `HUGO_PARAMS_CONSOLEURL=https://console.example make`.
