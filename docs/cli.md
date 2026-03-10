# CLI Reference

The `thea` command has two modes:

1. **Server mode** — starts a long-running HTTP server (`thea serve`)
2. **Client mode** — sends commands to a running server (all other subcommands)

## Installation

```bash
pip install thea-recorder
```

The `thea` command is automatically available after installation.

## Server Mode

```bash
thea serve --port 9123 --output-dir ./recordings
```

See [Server Reference](server.md) for all server options and the full API.

## Client Mode

Every client command talks to a running server via HTTP.

### Configuration

| Method | Example |
|---|---|
| `--server` flag | `thea --server http://host:9123 health` |
| `RECORDER_URL` env | `export RECORDER_URL=http://host:9123` |
| Default | `http://localhost:9123` |

### Output Flags

| Flag | Effect |
|---|---|
| (default) | JSON output, one line |
| `--pretty` | Indented JSON |
| `--quiet` | No output (exit code only) |

Non-zero exit code on any error.

## Commands

### Display

```bash
# Start the virtual display
thea start-display

# Stop the virtual display
thea stop-display
```

### Panels

```bash
# Add a panel
thea add-panel --name status --title Status --width 120

# Update panel content
thea update-panel --name status --text "Running step 3" --focus-line 5

# Remove a panel
thea remove-panel --name status
```

### Recording

```bash
# Start recording
thea start-recording --name login_test

# Check elapsed time
thea elapsed

# Stop recording (prints path and elapsed)
thea stop-recording
```

### File Operations

```bash
# List all recordings
thea list-recordings

# Download a recording
thea download --name login_test --output ./login_test.mp4
```

### Utility

```bash
# Health check
thea health

# Full teardown
thea cleanup

# Version
thea version
```

## Scripting Examples

### Record a test from bash

```bash
#!/bin/bash
set -euo pipefail

export RECORDER_URL=http://localhost:9123

thea start-display
thea add-panel --name status --title Status --width 120
thea start-recording --name "my_test"
thea update-panel --name status --text "Running"

# ... run your test here ...

thea update-panel --name status --text "PASSED"
RESULT=$(thea stop-recording)
echo "Video: $(echo $RESULT | jq -r .path)"

thea cleanup
```

### List recordings as a table

```bash
thea list-recordings --pretty | jq -r '.[] | "\(.name)\t\(.size)\t\(.created)"'
```

### Pipeline: record + download

```bash
thea start-recording --name smoke_test
sleep 10  # run tests
thea stop-recording --quiet
thea download --name smoke_test --output ./smoke_test.mp4
```

## Error Messages

When the server is unreachable:
```
Error: cannot reach recorder server at http://localhost:9123 — is 'thea serve' running?
```

When a resource doesn't exist:
```
Error: panel 'foo' not found
```

When there's a conflict:
```
Error: already recording
```
