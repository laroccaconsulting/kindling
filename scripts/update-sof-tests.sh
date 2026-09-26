#!/usr/bin/env bash
# Refresh the vendored SQL on FHIR conformance suite from FHIR/sql-on-fhir.js.
set -euo pipefail

ref="${1:-main}"
dest="packages/kindling-sof/tests/conformance"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git clone -q --depth 1 --branch "$ref" https://github.com/FHIR/sql-on-fhir.js "$tmp/sof"
sha="$(git -C "$tmp/sof" rev-parse HEAD)"
rm -f "$dest"/*.json
cp "$tmp"/sof/tests/*.json "$dest"/
cp "$tmp"/sof/LICENSE.md "$dest"/LICENSE.md
sed -i.bak -E "s/commit \`[0-9a-f]{40}\`/commit \`$sha\`/" "$dest/README.md" && rm -f "$dest/README.md.bak"
echo "Updated conformance tests to $sha"
