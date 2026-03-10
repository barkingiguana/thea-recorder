# thea-recorder

Python SDK for the **thea-recorder** HTTP server. Zero external dependencies — uses only the Python standard library (`urllib.request`).

## Install

```bash
pip install thea-recorder
```

Or install from source:

```bash
pip install -e sdks/python
```

## Quick start

```python
from thea import RecorderClient

client = RecorderClient("http://localhost:8080")

# Start the virtual display (auto-waits for server readiness)
client.start_display()

# Record a session
with client.recording("my-demo") as info:
    with client.panel("editor", "Code", 80) as panel:
        client.update_panel("editor", "print('hello')", focus_line=1)

# List saved recordings
for rec in client.list_recordings():
    print(rec["name"], rec["size"])

# Download a recording
client.download_recording("my-demo", "/tmp/my-demo.mp4")
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `url` | `THEA_URL` env var | Base URL of the recorder server |
| `timeout` | `30.0` | Default request timeout in seconds |

## API reference

### Display

- `start_display()` — Start the virtual display.
- `stop_display()` — Stop the virtual display.

### Panels

- `add_panel(name, title, width)` — Create a panel.
- `update_panel(name, text, focus_line=None)` — Update panel content.
- `remove_panel(name)` — Remove a panel.
- `list_panels()` — List all panels.

### Recording

- `start_recording(name)` — Start recording.
- `stop_recording()` — Stop the current recording. Returns path, elapsed, and name.
- `recording_elapsed()` — Get seconds elapsed for the current recording.
- `recording_status()` — Get full recording status.

### Recordings archive

- `list_recordings()` — List all saved recordings.
- `download_recording(name, path)` — Download an MP4 file to a local path.
- `recording_info(name)` — Get metadata for a recording.

### Health and cleanup

- `health()` — Server health check.
- `cleanup()` — Remove temporary resources.
- `wait_until_ready(timeout=30, interval=0.5)` — Poll `/health` until the server is reachable. Called automatically on first API call.

### Context managers

- `recording(name)` — Starts and stops a recording automatically.
- `panel(name, title, width)` — Creates and removes a panel automatically.

## Error handling

All errors raise `RecorderError`, which includes an optional `status` attribute for HTTP status codes.

```python
from thea import RecorderClient, RecorderError

try:
    client.start_recording("demo")
except RecorderError as e:
    print(f"Failed: {e} (HTTP {e.status})")
```
