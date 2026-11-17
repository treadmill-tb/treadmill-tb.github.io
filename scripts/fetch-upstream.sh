#!/usr/bin/env bash
# Fetch (or update) the Treadmill repository the docs are generated from.
#
#   TREADMILL_REPO  git URL      (default: https://github.com/treadmill-tb/treadmill.git)
#   TREADMILL_REF   branch/tag   (default: main)
#   TREADMILL_DIR   checkout dir (default: .treadmill)
set -euo pipefail

repo="${TREADMILL_REPO:-https://github.com/treadmill-tb/treadmill.git}"
ref="${TREADMILL_REF:-main}"
dir="${TREADMILL_DIR:-.treadmill}"

if [ -d "$dir/.git" ]; then
  git -C "$dir" fetch --depth 1 origin "$ref"
  git -C "$dir" checkout --quiet --detach FETCH_HEAD
else
  git clone --depth 1 --branch "$ref" "$repo" "$dir"
fi
echo "Upstream at $(git -C "$dir" rev-parse --short HEAD) ($ref)"
