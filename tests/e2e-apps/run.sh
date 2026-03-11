#!/usr/bin/env bash
# Run the E2E application recording tests.
#
# Everything runs in a single Docker container because Thea, Xvfb,
# and the application being recorded must be co-located.
#
# Output (videos + report) is written to tests/e2e-apps/output/
set -euo pipefail

cd "$(dirname "$0")"

# Clean previous output
rm -rf output
mkdir -p output

echo "Building test image..."
docker compose build

echo "Running E2E application tests..."
if docker compose up --abort-on-container-exit --exit-code-from test; then
    echo ""
    echo "All E2E application tests passed."
    echo "Output files:"
    ls -la output/ 2>/dev/null || echo "  (no output mounted)"
else
    echo ""
    echo "E2E application tests FAILED."
    docker compose logs test
    exit 1
fi

docker compose down
