#!/usr/bin/env python3
"""Generate the site's upstream data from a checkout of treadmill-tb/treadmill.

Everything under `data/upstream/` is produced by this script and is not
committed: the reference docs (switchboard API, host spec schema, tml CLI,
configuration) and a few facts on the landing page (versions, license,
components) are read from the upstream repository at build time, so the site
never drifts from the code.

Usage:
    scripts/gen_upstream.py --repo .treadmill [--tml path/to/tml] [--out data/upstream]

Inputs, all paths relative to the upstream repository:
    switchboard/api-spec/openapi.yaml                        -> api.json
    treadmill-rs/protocol-schema/host_spec_latest.schema.json -> hostspec.json
    cli/config.example.toml, switchboard/config.example.toml,
    supervisor/*/config.example.toml                          -> config.json
    AGENTS.md (section 1 component table)                     -> components.json
    Cargo.toml files, git metadata                            -> meta.json
    `tml help ...` output (when --tml is given)               -> cli.json

Requires Python 3.9+ and PyYAML.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tomllib

import yaml

# --------------------------------------------------------------------------
# Helpers


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


RUSTDOC_LINK = re.compile(r"\[([^\]]+)\]\(([A-Za-z0-9_:]+(?:::[A-Za-z0-9_]+)+)\)")
RUSTDOC_SHORTCUT = re.compile(r"\[(`[^`\]]+`)\](?![(\[])")


def clean_md(text: str | None) -> str:
    """Tidy a description taken from Rust doc comments for Markdown rendering.

    Intra-doc links such as [`JobInfo::x`](jobs::JobInfo::x) point into the Rust
    crate, not at anything on this site, so they become plain code spans.
    """
    if not text:
        return ""
    text = RUSTDOC_LINK.sub(r"\1", text)
    text = RUSTDOC_SHORTCUT.sub(r"\1", text)
    return escape_angles(text).strip()


def escape_angles(text: str) -> str:
    """Escape `<placeholder>` outside code spans so Markdown keeps it as text."""
    parts = re.split(r"(`[^`]*`)", text)
    return "".join(p if p.startswith("`") else re.sub(r"<(?=[A-Za-z_-]+>)", "&lt;", p) for p in parts)


def first_para(text: str) -> str:
    return text.split("\n\n", 1)[0].replace("\n", " ").strip()


def write_json(out: pathlib.Path, name: str, data) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"  wrote {out / name}")


# --------------------------------------------------------------------------
# JSON Schema -> displayable models
#
# A "type" is a list of parts the templates join together: {"t": "text"} or
# {"ref": "SchemaName"}, which the templates turn into a link.


class SchemaModels:
    def __init__(self, defs: dict, ref_prefix: str):
        self.defs = defs
        self.ref_prefix = ref_prefix
        self.used: set[str] = set()

    def ref_name(self, ref: str) -> str:
        assert ref.startswith(self.ref_prefix), ref
        return ref[len(self.ref_prefix):]

    def type_of(self, s: dict | bool) -> list[dict]:
        if s is True or s == {}:
            return [{"t": "any"}]
        if s is False:
            return [{"t": "never"}]
        if "$ref" in s:
            name = self.ref_name(s["$ref"])
            self.used.add(name)
            return [{"ref": name}]
        if "allOf" in s and len(s["allOf"]) == 1:
            return self.type_of(s["allOf"][0])
        for key in ("anyOf", "oneOf"):
            if key in s:
                parts: list[dict] = []
                for i, sub in enumerate(s[key]):
                    if i:
                        parts.append({"t": " | "})
                    parts.extend(self.type_of(sub))
                return parts
        if "const" in s:
            return [{"t": json.dumps(s["const"])}]
        if "enum" in s:
            return [{"t": " | ".join(json.dumps(v) for v in s["enum"])}]
        t = s.get("type")
        if isinstance(t, list):
            parts = []
            for i, tt in enumerate(t):
                if i:
                    parts.append({"t": " | "})
                parts.extend(self.type_of({**s, "type": tt}))
            return parts
        if t == "array":
            return [{"t": "array of "}] + self.type_of(s.get("items", {}))
        if t == "object":
            ap = s.get("additionalProperties")
            if "properties" not in s and ap not in (None, False):
                return [{"t": "map of string → "}] + self.type_of(ap)
            return [{"t": "object"}]
        fmt = s.get("format")
        if t and t != "null" and fmt:
            return [{"t": f"{t} ({fmt})"}]
        return [{"t": t or "any"}]

    def fields(self, s: dict) -> list[dict]:
        req = set(s.get("required", []))
        out = []
        for name, p in (s.get("properties") or {}).items():
            f = {
                "name": name,
                "type": self.type_of(p),
                "required": name in req,
                "description": clean_md(p.get("description")),
            }
            if "default" in p and p["default"] is not None:
                f["default"] = json.dumps(p["default"])
            # Inline object without a name: flatten its fields one level.
            if p.get("type") == "object" and p.get("properties"):
                f["fields"] = self.fields(p)
            out.append(f)
        # Required fields first, then alphabetical, as a reader scans for them.
        out.sort(key=lambda f: (not f["required"], f["name"]))
        return out

    def model(self, name: str, s: dict) -> dict:
        m: dict = {"name": name, "description": clean_md(s.get("description"))}
        if "oneOf" in s or "anyOf" in s:
            m["kind"] = "union"
            variants = []
            for sub in s.get("oneOf") or s.get("anyOf"):
                v: dict = {"description": clean_md(sub.get("description"))}
                if sub.get("properties"):
                    v["fields"] = self.fields(sub)
                    # Name tagged variants by their discriminator constant.
                    for fname, p in sub["properties"].items():
                        if "const" in p and fname in sub.get("required", []):
                            v["tag"] = f'{fname}: {json.dumps(p["const"])}'
                            break
                else:
                    v["type"] = self.type_of(sub)
                variants.append(v)
            m["variants"] = variants
        elif "enum" in s:
            m["kind"] = "enum"
            m["values"] = [json.dumps(v) for v in s["enum"]]
        elif s.get("properties"):
            m["kind"] = "object"
            m["fields"] = self.fields(s)
            ap = s.get("additionalProperties")
            if ap not in (None, False):
                m["additional"] = self.type_of(ap)
        else:
            m["kind"] = "scalar"
            m["type"] = self.type_of(s)
        return m

    def all_models(self) -> dict:
        return {n: self.model(n, s) for n, s in sorted(self.defs.items())}


# --------------------------------------------------------------------------
# Switchboard OpenAPI


def gen_api(repo: pathlib.Path) -> dict:
    spec = yaml.safe_load((repo / "switchboard/api-spec/openapi.yaml").read_text())
    schemas = spec.get("components", {}).get("schemas", {})
    sm = SchemaModels(schemas, "#/components/schemas/")
    security_schemes = spec.get("components", {}).get("securitySchemes", {})

    tags = [
        {
            "name": t["name"],
            "slug": slug(t["name"]),
            "description": clean_md(t.get("description")),
            "operations": [],
        }
        for t in spec.get("tags", [])
    ]
    by_name = {t["name"]: t for t in tags}

    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in ("get", "put", "post", "delete", "patch", "head", "options"):
                continue
            params = []
            for p in op.get("parameters", []):
                params.append({
                    "name": p["name"],
                    "in": p["in"],
                    "required": bool(p.get("required")),
                    "type": sm.type_of(p.get("schema", {})),
                    "description": clean_md(p.get("description") or p.get("schema", {}).get("description")),
                })
            body = None
            if "requestBody" in op:
                rb = op["requestBody"]
                content = rb.get("content", {})
                ctype, media = next(iter(content.items())) if content else (None, {})
                body = {
                    "content_type": ctype,
                    "required": bool(rb.get("required")),
                    "description": clean_md(rb.get("description")),
                    "type": sm.type_of(media.get("schema", {})) if media else [],
                }
            responses = []
            for code, r in op.get("responses", {}).items():
                content = r.get("content", {})
                rtype = None
                if content:
                    ctype, media = next(iter(content.items()))
                    rtype = sm.type_of(media.get("schema", {}))
                responses.append({
                    "code": str(code),
                    "description": clean_md(r.get("description")),
                    "type": rtype,
                })
            security = [k for req in op.get("security", []) for k in req]
            operation = {
                "id": op.get("operationId") or slug(f"{method} {path}"),
                "method": method.upper(),
                "path": path,
                "summary": clean_md(op.get("summary")),
                "description": clean_md(op.get("description")),
                "deprecated": bool(op.get("deprecated")),
                "security": security,
                "params": params,
                "body": body,
                "responses": responses,
            }
            for tname in op.get("tags", ["Other"]):
                if tname not in by_name:
                    by_name[tname] = {"name": tname, "slug": slug(tname), "description": "", "operations": []}
                    tags.append(by_name[tname])
                by_name[tname]["operations"].append(operation)

    return {
        "title": spec["info"].get("title"),
        "version": spec["info"].get("version"),
        "openapi": spec.get("openapi"),
        "source": "switchboard/api-spec/openapi.yaml",
        "security_schemes": [
            {"name": k, "scheme": v.get("scheme"), "description": clean_md(v.get("description"))}
            for k, v in security_schemes.items()
        ],
        "tags": [t for t in tags if t["operations"]],
        "schemas": sm.all_models(),
    }


# --------------------------------------------------------------------------
# Host spec JSON Schema


def gen_hostspec(repo: pathlib.Path) -> dict:
    rel = "treadmill-rs/protocol-schema/host_spec_latest.schema.json"
    schema = json.loads((repo / rel).read_text())
    sm = SchemaModels(schema.get("$defs", {}), "#/$defs/")
    root = sm.model(schema.get("title", "HostSpec"), schema)
    return {
        "source": rel,
        "title": schema.get("title"),
        "root": root,
        "defs": sm.all_models(),
    }


# --------------------------------------------------------------------------
# Example configuration files


CONFIG_FILES = [
    ("cli/config.example.toml", "tml CLI", "Client configuration, read by `tml`."),
    ("switchboard/config.example.toml", "Switchboard", "Server configuration for the central coordinator."),
]


def gen_config(repo: pathlib.Path) -> dict:
    files = list(CONFIG_FILES)
    for p in sorted(repo.glob("supervisor/*/config.example.toml")):
        crate = p.parent.name
        files.append((str(p.relative_to(repo)), f"Supervisor: {crate}", f"Configuration for the `{crate}` supervisor."))
    out = []
    for rel, title, blurb in files:
        path = repo / rel
        if not path.exists():
            print(f"  warning: {rel} not found, skipping", file=sys.stderr)
            continue
        out.append({"path": rel, "title": title, "slug": slug(title), "description": blurb, "content": path.read_text()})
    return {"files": out}


# --------------------------------------------------------------------------
# AGENTS.md component table


def gen_components(repo: pathlib.Path) -> list[dict]:
    """Parse the component table in AGENTS.md section 1.

    Rows whose first cell is empty continue the previous row (the table wraps
    long cells onto several lines).
    """
    text = (repo / "AGENTS.md").read_text()
    m = re.search(r"\| *Component *\|.*?\n\|[-| ]+\|\n((?:\|.*\|\n)+)", text)
    if not m:
        print("  warning: no component table in AGENTS.md", file=sys.stderr)
        return []
    rows: list[list[str]] = []
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if rows and not cells[0]:
            for i, c in enumerate(cells):
                if c:
                    rows[-1][i] = (rows[-1][i] + " " + c).strip()
        else:
            rows.append(cells)
    out = []
    for cells in rows:
        name, crates, role = (cells + ["", "", ""])[:3]
        out.append({
            "name": name.replace("**", "").strip(),
            "crates": re.findall(r"`([^`]+)`", crates),
            "role": role.strip(),
        })
    return out


# --------------------------------------------------------------------------
# tml CLI help


SECTION = re.compile(r"^([A-Z][A-Za-z ]+):$")
ENTRY = re.compile(r"^  (\S.*?)(?:\s{2,}(\S.*))?$")


def run_help(tml: str, path: list[str]) -> str:
    env = {"PATH": "/usr/bin:/bin", "NO_COLOR": "1", "TERM": "dumb", "HOME": "/nonexistent"}
    return subprocess.run([tml, *path, "--help"], capture_output=True, text=True, env=env, check=True).stdout


def parse_help(text: str) -> dict:
    """Parse clap's long `--help` output into description, usage and sections."""
    lines = text.rstrip("\n").splitlines()
    i = 0
    desc: list[str] = []
    while i < len(lines) and not lines[i].startswith("Usage:"):
        desc.append(lines[i])
        i += 1
    usage = lines[i][len("Usage:"):].strip() if i < len(lines) else ""
    i += 1
    sections: list[dict] = []
    cur = None
    entry = None
    for line in lines[i:]:
        sm = SECTION.match(line)
        if sm:
            cur = {"title": sm.group(1), "entries": []}
            sections.append(cur)
            entry = None
            continue
        if cur is None:
            continue
        if not line.strip():
            if entry is not None:
                entry["help"].append("")
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent in (2, 6) and (cur["title"] == "Commands" or line.lstrip().startswith(("-", "<", "["))):
            em = ENTRY.match(line[indent - 2:] if indent == 6 else line)
            entry = {"term": em.group(1).strip(), "help": [em.group(2)] if em.group(2) else []}
            cur["entries"].append(entry)
        elif entry is not None:
            entry["help"].append(line.strip())

    possible = re.compile(r"\[possible values: ([^\]]+)\]")
    default = re.compile(r"\[default: ([^\]]+)\]")
    for s in sections:
        for e in s["entries"]:
            body = "\n".join(e["help"]).strip()
            pv = possible.search(body)
            dv = default.search(body)
            body = default.sub("", possible.sub("", body))
            e["help"] = escape_angles(re.sub(r"\n{3,}", "\n\n", body).strip())
            if pv:
                e["values"] = [v.strip() for v in pv.group(1).split(",")]
            if dv:
                e["default"] = dv.group(1)
            if s["title"] == "Commands":
                e["name"] = e["term"].split(",")[0].strip()
    return {"description": escape_angles("\n".join(desc).strip()), "usage": usage, "sections": sections}


def gen_cli(tml: str) -> dict:
    version = subprocess.run([tml, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    commands: list[dict] = []

    def walk(path: list[str]):
        h = parse_help(run_help(tml, path))
        subs = []
        for s in h["sections"]:
            if s["title"] == "Commands":
                subs = [e["name"] for e in s["entries"] if e["name"] != "help"]
                s["entries"] = [e for e in s["entries"] if e["name"] != "help"]
        # Global options repeat on every page; keep them on the root only.
        if path:
            h["sections"] = [s for s in h["sections"] if s["title"] != "Global Options"]
        for s in h["sections"]:
            if s["title"] == "Options":
                s["entries"] = [e for e in s["entries"] if not e["term"].startswith(("-h, --help", "-V, --version"))]
        h["sections"] = [s for s in h["sections"] if s["entries"]]
        name = " ".join(["tml", *path])
        commands.append({
            "name": name,
            "anchor": slug(name),
            "depth": len(path),
            "summary": first_para(h["description"]),
            "subcommands": [" ".join(["tml", *path, s]) for s in subs],
            **h,
        })
        for s in subs:
            walk([*path, s])

    walk([])
    return {"version": version, "source": "cli/src/cli.rs", "commands": commands}


# --------------------------------------------------------------------------
# Repository metadata


def gen_meta(repo: pathlib.Path) -> dict:
    def git(*args):
        try:
            return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def crate(rel):
        p = repo / rel
        if not p.exists():
            return None
        return tomllib.loads(p.read_text()).get("package", {})

    workspace = tomllib.loads((repo / "Cargo.toml").read_text()).get("workspace", {}).get("package", {})
    cli = crate("cli/Cargo.toml") or {}
    license_ = cli.get("license") if isinstance(cli.get("license"), str) else workspace.get("license")
    return {
        "commit": git("rev-parse", "HEAD"),
        "commit_short": git("rev-parse", "--short=10", "HEAD"),
        "commit_date": git("log", "-1", "--format=%cI"),
        "tml_version": cli.get("version"),
        "tml_description": cli.get("description"),
        "license": license_ or "MIT OR Apache-2.0",
        "licenses": sorted(p.name for p in repo.glob("LICENSE*")),
    }


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, type=pathlib.Path, help="treadmill repository checkout")
    ap.add_argument("--tml", help="a built tml binary, to generate the CLI reference")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent.parent / "data/upstream")
    args = ap.parse_args()

    repo = args.repo.resolve()
    print(f"Generating from {repo}")
    meta = gen_meta(repo)
    write_json(args.out, "meta.json", meta)
    write_json(args.out, "api.json", gen_api(repo))
    write_json(args.out, "hostspec.json", gen_hostspec(repo))
    write_json(args.out, "config.json", gen_config(repo))
    write_json(args.out, "components.json", gen_components(repo))
    if args.tml:
        write_json(args.out, "cli.json", gen_cli(args.tml))
    elif not (args.out / "cli.json").exists():
        print("  note: no --tml given; the CLI reference will be empty", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
