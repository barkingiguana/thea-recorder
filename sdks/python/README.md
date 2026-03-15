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

# Record with GIF output
with client.recording("my-demo", gif=True, gif_fps=10) as info:
    with client.panel("editor", "Code", 80) as panel:
        client.update_panel("editor", "print('hello')", focus_line=1)
print(info.gif_path)       # GIF path on server
print(info.extra_paths)    # {"gif": "/path/to.gif"}

# Download GIF/WebM variants
client.download_recording("my-demo", "/tmp/my-demo.gif", format="gif")
client.download_recording("my-demo", "/tmp/my-demo.webm", format="webm")

# Convert an existing recording to GIF
client.convert_to_gif("my-demo", fps=10, width=720)
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
- `stop_recording(*, gif=False, gif_fps=10, gif_width=720, output_formats=None)` — Stop the current recording. Returns path, elapsed, name, and optionally `gif_path` and `extra_paths`. Set `gif=True` to also produce a GIF. Use `output_formats=["gif", "webm"]` for multiple output formats.
- `convert_to_gif(name, *, fps=10, width=720)` — Convert an existing recording to GIF.
- `recording_elapsed()` — Get seconds elapsed for the current recording.
- `recording_status()` — Get full recording status.

### Recordings archive

- `list_recordings()` — List all saved recordings.
- `download_recording(name, path, *, format="mp4")` — Download a recording to a local path. Use `format="gif"` or `format="webm"` to download alternative formats.
- `recording_info(name)` — Get metadata for a recording.

### Health and cleanup

- `health()` — Server health check.
- `cleanup()` — Remove temporary resources.
- `wait_until_ready(timeout=30, interval=0.5)` — Poll `/health` until the server is reachable. Called automatically on first API call.

### Context managers

- `recording(name, *, gif=False, gif_fps=10, gif_width=720, output_formats=None)` — Starts and stops a recording automatically. Pass `gif=True` to produce a GIF alongside the MP4. The result object exposes `gif_path` and `extra_paths` attributes.
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
