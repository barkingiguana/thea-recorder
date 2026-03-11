#!/usr/bin/env bash
# Usage: scripts/bump-version.sh <new-version>
# Updates the VERSION file and all package manifests to the given version.
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <new-version>" >&2
  exit 1
fi

VER="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "$VER" > "$ROOT/VERSION"

# Python main package
sed -i.bak "s/^version = \".*\"/version = \"$VER\"/" "$ROOT/pyproject.toml" && rm -f "$ROOT/pyproject.toml.bak"

# Director package
if [ -f "$ROOT/director/pyproject.toml" ]; then
  sed -i.bak "s/^version = \".*\"/version = \"$VER\"/" "$ROOT/director/pyproject.toml" && rm -f "$ROOT/director/pyproject.toml.bak"
fi

# Python SDK
sed -i.bak "s/^version = \".*\"/version = \"$VER\"/" "$ROOT/sdks/python/pyproject.toml" && rm -f "$ROOT/sdks/python/pyproject.toml.bak"

# Python CLI hardcoded version
sed -i.bak "s/\"version\": \"[0-9][^\"]*\"/\"version\": \"$VER\"/" "$ROOT/src/thea/cli.py" && rm -f "$ROOT/src/thea/cli.py.bak"

# Node SDK
cd "$ROOT/sdks/node" && npm version "$VER" --no-git-tag-version --allow-same-version > /dev/null

# Ruby SDK
sed -i.bak "s/VERSION = \".*\"/VERSION = \"$VER\"/" "$ROOT/sdks/ruby/lib/recorder.rb" && rm -f "$ROOT/sdks/ruby/lib/recorder.rb.bak"

# Java SDK (replace only the first <version> tag — the project version)
awk -v ver="$VER" '!done && /<version>/ { sub(/<version>[^<]*<\/version>/, "<version>" ver "</version>"); done=1 } 1' \
  "$ROOT/sdks/java/pom.xml" > "$ROOT/sdks/java/pom.xml.tmp" && mv "$ROOT/sdks/java/pom.xml.tmp" "$ROOT/sdks/java/pom.xml"

echo "All versions updated to $VER"
