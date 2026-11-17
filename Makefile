# Build the Treadmill website.
#
#   make            fetch upstream, generate data, build the site into public/
#   make serve      the same, then serve with live reload
#   make data       only regenerate data/upstream/ from the upstream checkout
#
# Requires: git, python3 + PyYAML, hugo (extended, see .hugo-version), and a
# Rust toolchain to build `tml` for the CLI reference (skip with NO_CLI=1).

UPSTREAM ?= .treadmill
HUGO     ?= hugo
TML      := $(UPSTREAM)/target/release/tml

.PHONY: all build serve data fetch clean

all: build

fetch:
	scripts/fetch-upstream.sh

$(TML): fetch
	cargo build --release --manifest-path $(UPSTREAM)/Cargo.toml -p treadmill-cli

ifdef NO_CLI
data: fetch
	python3 scripts/gen_upstream.py --repo $(UPSTREAM)
else
data: fetch $(TML)
	python3 scripts/gen_upstream.py --repo $(UPSTREAM) --tml $(TML)
endif

build: data
	$(HUGO) --gc --minify

serve: data
	$(HUGO) server

clean:
	rm -rf public resources/_gen data/upstream
