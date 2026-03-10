#!/usr/bin/env bash
# Run the full E2E test suite.
# Each SDK container runs its test against the live recorder server.
# Tests run sequentially because they share a single recorder server.
set -euo pipefail

cd "$(dirname "$0")"

echo "Building images..."
docker compose build

echo "Starting recorder server..."
docker compose up -d recorder

echo "Waiting for recorder to be healthy..."
for i in $(seq 1 30); do
    if docker compose exec recorder curl -sf http://localhost:9123/health > /dev/null 2>&1; then
        echo "Recorder is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "Recorder failed to start."
        docker compose logs recorder
        docker compose down
        exit 1
    fi
    sleep 1
done

FAILED=0

for lang in go python ruby node java; do
    echo ""
    echo "═══ Running test-${lang} ═══"
    if docker compose run --rm "test-${lang}"; then
        echo "✓ test-${lang} passed"
    else
        echo "✗ test-${lang} FAILED"
        FAILED=1
    fi
done

echo ""
docker compose down

if [ "$FAILED" -eq 1 ]; then
    echo "Some E2E tests FAILED."
    exit 1
fi

echo "All E2E tests passed."
