# HTTP Server Reference

The recorder server is a long-running process that wraps a single `Recorder` instance and exposes it via a REST API. SDKs and the CLI both talk to this server.

## Starting the server

```bash
recorder serve --port 9123 --output-dir ./recordings --display 99
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--port` | `9123` | Port to listen on |
| `--display` | `99` | X11 display number for Xvfb |
| `--output-dir` | `/tmp/recordings` | Where MP4 files are saved |
| `--display-size` | `1920x1080` | Application viewport resolution |
| `--framerate` | `15` | Recording FPS |
| `--cors` | off | Enable CORS headers |

### Docker

```bash
docker run --shm-size=2g -p 9123:9123 \
  -v $(pwd)/recordings:/app/recordings \
  my-recorder-image \
  recorder serve --port 9123 --output-dir /app/recordings
```

## API Reference

All endpoints return JSON unless noted. Error responses use `{"error": "message"}`.

### Display

#### Start display
```bash
curl -X POST http://localhost:9123/display/start
```

Optional body to override display resolution for this session:
```json
{"display_size": "1280x720"}
```

**Response** `201`:
```json
{"status": "started", "display": ":99"}
```
**Error** `409` if display already started.

#### Stop display
```bash
curl -X POST http://localhost:9123/display/stop
```
**Response** `200`:
```json
{"status": "stopped"}
```

#### Screenshot (live display)
Capture a single JPEG frame from the live display.
```bash
curl http://localhost:9123/display/screenshot -o screenshot.jpg
curl http://localhost:9123/display/screenshot?quality=50 -o screenshot.jpg
```
**Response** `200` with `Content-Type: image/jpeg`. The `quality` parameter (1-100, default 80) controls JPEG compression.

**Error** `409` if display not started.

#### Stream (raw MJPEG feed)
A continuous MJPEG byte stream of the live display. Use this for embedding in HTML (`<img src="/display/stream">`) or for programmatic consumption.
```bash
# Embed in HTML:
<img src="http://localhost:9123/display/stream?fps=5" />

# Or consume with curl (runs until you Ctrl-C):
curl http://localhost:9123/display/stream?fps=10 > /dev/null
```
**Response** `200` with `Content-Type: multipart/x-mixed-replace`. The `fps` parameter (1-15, default 5) controls frame rate.

**Error** `409` if display not started.

#### Viewer (HTML page)
A self-contained HTML page with a dark-themed live viewer, status indicator, and auto-reconnect. Open this URL directly in a browser.
```bash
# Open in your browser:
open http://localhost:9123/display/view
```
**Response** `200` with `Content-Type: text/html`.

All three display observation endpoints are also available under `/sessions/{name}/display/screenshot`, `/sessions/{name}/display/stream`, and `/sessions/{name}/display/view`.

### Panels

#### Create panel
```bash
curl -X POST http://localhost:9123/panels \
  -H "Content-Type: application/json" \
  -d '{"name": "status", "title": "Status", "width": 120, "height": 200}'
```
**Response** `201`:
```json
{"name": "status", "title": "Status", "width": 120, "height": 200}
```

| Field | Required | Description |
|---|---|---|
| `name` | yes | Unique panel identifier |
| `title` | no | Bold heading (default: empty string) |
| `width` | no | Fixed width in pixels (`null` = auto-width, `<= 0` treated as auto) |
| `height` | no | Panel height in pixels (`null` = use bar height default of 300px) |
| `bg_color` | no | Background colour as 6-digit hex string, e.g. `"1a1a2e"` (`null` = default) |
| `opacity` | no | Background opacity from `0.0` (transparent) to `1.0` (opaque) (`null` = default) |

The response includes a `warnings` array if there are layout validation issues:
```json
{"name": "huge", "title": "", "width": null, "height": 500, "warnings": ["Panel bar needs 500px but only 300px was allocated..."]}
```

**Error** `400` if `name` is missing, `width` is not an integer, or `height` is not a positive integer.

#### List panels
```bash
curl http://localhost:9123/panels
```
**Response** `200`:
```json
[{"name": "status", "title": "Status", "width": 120}]
```

#### Update panel
```bash
curl -X PUT http://localhost:9123/panels/status \
  -H "Content-Type: application/json" \
  -d '{"text": "Running step 3", "focus_line": 5}'
```
**Response** `200`:
```json
{"name": "status", "text": "Running step 3"}
```
`focus_line` defaults to `-1` (focus on last line).

**Error** `404` if panel doesn't exist.

#### Delete panel
```bash
curl -X DELETE http://localhost:9123/panels/status
```
**Response** `200`:
```json
{"status": "removed"}
```
**Error** `404` if panel doesn't exist.

### Recording

#### Start recording
```bash
curl -X POST http://localhost:9123/recording/start \
  -H "Content-Type: application/json" \
  -d '{"name": "login_test"}'
```
**Response** `201`:
```json
{"status": "recording", "name": "login_test"}
```

If there are layout validation issues, the response includes a `warnings` array:
```json
{"status": "recording", "name": "login_test", "warnings": ["Panel bar needs 500px but only 300px was allocated..."]}
```

**Error** `409` if already recording. `400` if `name` is missing.

#### Stop recording
```bash
curl -X POST http://localhost:9123/recording/stop
```
**Response** `200`:
```json
{"path": "/app/recordings/login_test.mp4", "elapsed": 45.2, "name": "login_test"}
```
**Error** `409` if not recording.

#### Get elapsed time
```bash
curl http://localhost:9123/recording/elapsed
```
**Response** `200`:
```json
{"elapsed": 12.5}
```
Returns `0.0` when not recording.

#### Get recording status
```bash
curl http://localhost:9123/recording/status
```
**Response** `200`:
```json
{"recording": true, "name": "login_test", "elapsed": 12.5}
```

### Annotations

Annotations are timestamped markers attached to the active recording. They are returned in the stop-recording response and emitted as events.

#### Add annotation
```bash
curl -X POST http://localhost:9123/recording/annotations \
  -H "Content-Type: application/json" \
  -d '{"label": "login_started", "details": "User clicked login button"}'
```
**Response** `201`:
```json
{"label": "login_started", "time": 3.456, "details": "User clicked login button"}
```

| Field | Required | Description |
|---|---|---|
| `label` | yes | Short annotation label |
| `time` | no | Time offset in seconds (default: current elapsed) |
| `details` | no | Optional longer description |

**Error** `400` if label is missing or time is negative. `409` if not recording.

#### List annotations
```bash
curl http://localhost:9123/recording/annotations
```
**Response** `200`:
```json
[
  {"label": "login_started", "time": 3.456},
  {"label": "assertion_passed", "time": 8.2, "details": "Login form submitted"}
]
```

**Error** `409` if not recording.

Annotations are included in the stop-recording response under the `annotations` key and cleared when the recording stops.

### File Access

#### List recordings
```bash
curl http://localhost:9123/recordings
```
**Response** `200`:
```json
[
  {
    "name": "login_test",
    "path": "/app/recordings/login_test.mp4",
    "size": 1234567,
    "created": "2026-03-10T14:30:00+00:00"
  }
]
```

#### Download recording
```bash
curl -O http://localhost:9123/recordings/login_test
```
**Response** `200` with `Content-Type: video/mp4` and `Content-Disposition: attachment`.

**Range requests** for video seeking:
```bash
curl -H "Range: bytes=0-1023" http://localhost:9123/recordings/login_test
```
Returns `206 Partial Content` with `Content-Range` header.

**Download with wget:**
```bash
wget http://localhost:9123/recordings/login_test -O login_test.mp4
```

**Error** `404` if recording doesn't exist. `400` if name contains path traversal characters.

#### Screenshot from recording
Extract a single JPEG frame from a saved recording at any time offset.
```bash
curl "http://localhost:9123/recordings/login_test/screenshot?t=12.5" -o frame.jpg
curl "http://localhost:9123/recordings/login_test/screenshot?t=0&quality=95" -o frame.jpg
```
**Response** `200` with `Content-Type: image/jpeg`.

| Parameter | Required | Description |
|---|---|---|
| `t` | yes | Time offset in seconds (e.g. `12.5`) |
| `quality` | no | JPEG quality 1-100 (default: 80) |

**Error** `400` if `t` is missing. `404` if recording doesn't exist.

#### Recording info
```bash
curl http://localhost:9123/recordings/login_test/info
```
**Response** `200`:
```json
{
  "name": "login_test",
  "path": "/app/recordings/login_test.mp4",
  "size": 1234567,
  "created": "2026-03-10T14:30:00+00:00"
}
```

### Layout Validation

#### Validate layout
```bash
curl http://localhost:9123/validate-layout
```
**Response** `200`:
```json
{"warnings": [], "valid": true}
```

Checks for overlapping panels, panels exceeding the canvas width, and panel bar height exceeding the allocated display space.

#### Testcard
```bash
curl http://localhost:9123/testcard > layout.svg
```
**Response** `200` with `Content-Type: image/svg+xml`.

Returns an SVG testcard image showing the spatial layout of the viewport and all panels, with dimensions and positions labelled. Any validation warnings are displayed at the bottom.

Both endpoints are also available under `/sessions/{name}/validate-layout` and `/sessions/{name}/testcard`.

### Utility

#### Health check
```bash
curl http://localhost:9123/health
```
**Response** `200`:
```json
{
  "status": "ok",
  "recording": false,
  "display": ":99",
  "panels": ["status", "scenario"],
  "uptime": 123.4
}
```

#### Cleanup
```bash
curl -X POST http://localhost:9123/cleanup
```
Stops any active recording, stops the display, removes all panels.
**Response** `200`:
```json
{"status": "cleaned"}
```

## Graceful Shutdown

The server handles `SIGTERM` gracefully:
1. Stops any in-progress ffmpeg recording (video is finalised)
2. Stops Xvfb
3. Removes panel temp files
4. Exits cleanly

This means `docker stop` will not lose a recording in progress.

## CORS

Enable CORS with `--cors` to allow web-based dashboards to access recordings:

```bash
recorder serve --port 9123 --cors
```

This adds `Access-Control-Allow-Origin: *` to all responses and handles preflight `OPTIONS` requests.

## Error Responses

All errors return JSON:

| Status | Meaning |
|---|---|
| `400` | Bad request (missing/invalid fields) |
| `404` | Resource not found (panel or recording) |
| `409` | Conflict (display already started, already recording, not recording) |
| `416` | Range not satisfiable |
| `405` | Method not allowed |

Example:
```json
{"error": "panel 'foo' not found"}
```

## Sessions (parallel recordings)

A single server can manage any number of independent recording sessions.  Each
session has its own Xvfb virtual display, ffmpeg process, and panel set.  This
lets you record multiple concurrent sessions without running multiple servers.

### Create a session

```bash
curl -X POST http://localhost:9123/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "alice"}'
```
**Response** `201`:
```json
{"name": "alice", "display": 100, "url_prefix": "/sessions/alice"}
```
`display` is auto-allocated if not supplied.  The `url_prefix` is the base for
all session-scoped calls.

**Error** `409` if the name already exists.  `400` if name is missing or
`"default"` (reserved for the implicit default session).

### List sessions

```bash
curl http://localhost:9123/sessions
```
**Response** `200`:
```json
[
  {"name": "default", "display": 99,  "recording": false, "recording_name": null},
  {"name": "alice",   "display": 100, "recording": true,  "recording_name": "alice_checkout"}
]
```

### Destroy a session

```bash
curl -X DELETE http://localhost:9123/sessions/alice
```
Stops any in-progress recording, stops Xvfb, removes panels.
**Response** `200`: `{"status": "removed"}`

### Session-scoped endpoints

Every display, panel, and recording endpoint is available under
`/sessions/{name}/...`:

```bash
# Start the session's virtual display
curl -X POST http://localhost:9123/sessions/alice/display/start

# Add a panel
curl -X POST http://localhost:9123/sessions/alice/panels \
  -H "Content-Type: application/json" \
  -d '{"name": "status", "title": "Status"}'

# Start recording
curl -X POST http://localhost:9123/sessions/alice/recording/start \
  -H "Content-Type: application/json" \
  -d '{"name": "alice_checkout"}'

# Update a panel
curl -X PUT http://localhost:9123/sessions/alice/panels/status \
  -H "Content-Type: application/json" \
  -d '{"text": "Step 3 of 5"}'

# Stop recording
curl -X POST http://localhost:9123/sessions/alice/recording/stop

# Session health
curl http://localhost:9123/sessions/alice/health
```

The top-level endpoints (`/display/start`, `/panels`, `/recording/start`, etc.)
continue to work as before and operate on the **default** session.

See [Orchestration guide](orchestration.md) for parallel recording examples.

## Director (Human-like Interaction)

The Director endpoints let you simulate human-like mouse, keyboard, and window
interactions on the virtual display.  Mouse movements follow minimum-jerk
trajectories; typing uses realistic rhythm models.

All Director endpoints are available under both `/director/...` (default
session) and `/sessions/{name}/director/...` (named session).

### Mouse

#### Move mouse
```bash
curl -X POST http://localhost:9123/director/mouse/move \
  -H "Content-Type: application/json" \
  -d '{"x": 500, "y": 300}'
```

| Field | Required | Description |
|---|---|---|
| `x` | yes | Target X coordinate |
| `y` | yes | Target Y coordinate |
| `duration` | no | Movement duration in seconds (default: Fitts's Law estimate) |
| `target_width` | no | Target element width for Fitts's Law calculation |

**Response** `200`: `{"status": "ok"}`

#### Click
```bash
curl -X POST http://localhost:9123/director/mouse/click \
  -H "Content-Type: application/json" \
  -d '{"x": 500, "y": 300}'
```

| Field | Required | Description |
|---|---|---|
| `x` | no | X coordinate (omit to click in place) |
| `y` | no | Y coordinate (omit to click in place) |
| `button` | no | Mouse button: 1=left, 2=middle, 3=right (default: 1) |
| `duration` | no | Movement duration in seconds |

**Response** `200`: `{"status": "ok"}`

#### Double-click
```bash
curl -X POST http://localhost:9123/director/mouse/double-click \
  -H "Content-Type: application/json" \
  -d '{"x": 500, "y": 300}'
```
Optional `x`, `y` fields. **Response** `200`: `{"status": "ok"}`

#### Right-click
```bash
curl -X POST http://localhost:9123/director/mouse/right-click \
  -H "Content-Type: application/json" \
  -d '{"x": 500, "y": 300}'
```
Optional `x`, `y` fields. **Response** `200`: `{"status": "ok"}`

#### Drag
```bash
curl -X POST http://localhost:9123/director/mouse/drag \
  -H "Content-Type: application/json" \
  -d '{"start_x": 100, "start_y": 200, "end_x": 500, "end_y": 400}'
```

| Field | Required | Description |
|---|---|---|
| `start_x` | yes | Start X |
| `start_y` | yes | Start Y |
| `end_x` | yes | End X |
| `end_y` | yes | End Y |
| `button` | no | Mouse button (default: 1) |
| `duration` | no | Drag duration in seconds |

**Response** `200`: `{"status": "ok"}`

#### Scroll
```bash
curl -X POST http://localhost:9123/director/mouse/scroll \
  -H "Content-Type: application/json" \
  -d '{"clicks": 3}'
```

| Field | Required | Description |
|---|---|---|
| `clicks` | yes | Scroll clicks (positive=up, negative=down) |
| `x` | no | X coordinate |
| `y` | no | Y coordinate |

**Response** `200`: `{"status": "ok"}`

#### Get mouse position
```bash
curl http://localhost:9123/director/mouse/position
```
**Response** `200`: `{"x": 500, "y": 300}`

### Keyboard

#### Type text
```bash
curl -X POST http://localhost:9123/director/keyboard/type \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, world!"}'
```

| Field | Required | Description |
|---|---|---|
| `text` | yes | Text to type |
| `wpm` | no | Typing speed in words per minute (default: realistic rhythm model) |

**Response** `200`: `{"status": "ok"}`

#### Press keys
```bash
curl -X POST http://localhost:9123/director/keyboard/press \
  -H "Content-Type: application/json" \
  -d '{"keys": ["ctrl+a", "Delete"]}'
```

| Field | Required | Description |
|---|---|---|
| `keys` | yes | Array of key names (e.g. `["Return"]`, `["ctrl+c"]`) |

**Response** `200`: `{"status": "ok"}`

#### Hold key
```bash
curl -X POST http://localhost:9123/director/keyboard/hold \
  -H "Content-Type: application/json" \
  -d '{"key": "Shift_L"}'
```
**Response** `200`: `{"status": "ok"}`

#### Release key
```bash
curl -X POST http://localhost:9123/director/keyboard/release \
  -H "Content-Type: application/json" \
  -d '{"key": "Shift_L"}'
```
**Response** `200`: `{"status": "ok"}`

### Window Management

#### Find window
```bash
curl -X POST http://localhost:9123/director/window/find \
  -H "Content-Type: application/json" \
  -d '{"name": "Firefox"}'
```

| Field | Required | Description |
|---|---|---|
| `name` | one of `name`/`class` | Window title substring |
| `class` | one of `name`/`class` | Window class |
| `timeout` | no | Search timeout in seconds (default: 10) |

**Response** `200`: `{"window_id": "12345"}`
**Error** `404` if window not found within timeout.

#### Focus window
```bash
curl -X POST http://localhost:9123/director/window/12345/focus
```
**Response** `200`: `{"status": "ok"}`

#### Move window
```bash
curl -X POST http://localhost:9123/director/window/12345/move \
  -H "Content-Type: application/json" \
  -d '{"x": 0, "y": 0}'
```
**Response** `200`: `{"status": "ok"}`

#### Resize window
```bash
curl -X POST http://localhost:9123/director/window/12345/resize \
  -H "Content-Type: application/json" \
  -d '{"width": 1280, "height": 720}'
```
**Response** `200`: `{"status": "ok"}`

#### Minimize window
```bash
curl -X POST http://localhost:9123/director/window/12345/minimize
```
**Response** `200`: `{"status": "ok"}`

#### Get window geometry
```bash
curl http://localhost:9123/director/window/12345/geometry
```
**Response** `200`: `{"x": 0, "y": 0, "width": 1280, "height": 720}`

#### Tile windows
```bash
curl -X POST http://localhost:9123/director/window/tile \
  -H "Content-Type: application/json" \
  -d '{"window_ids": ["111", "222"], "layout": "side-by-side"}'
```

| Field | Required | Description |
|---|---|---|
| `window_ids` | yes | Array of window ID strings |
| `layout` | no | `side-by-side`, `stacked`, or `grid` (default: `side-by-side`) |

**Response** `200`: `{"status": "ok"}`

## Events

Every state-changing operation is logged to a per-session event log. Events are stored in memory and can be polled for live updates.

### List events

```bash
# Default session events
curl http://localhost:9123/events

# Only events since a given elapsed time (for polling)
curl http://localhost:9123/events?since=45.2

# Session-scoped events
curl http://localhost:9123/sessions/alice/events
```

**Response** `200`:
```json
[
  {
    "event": "display.started",
    "time": "2026-03-12T10:30:00+00:00",
    "elapsed": 0.5,
    "details": {"display": ":99", "display_size": "1920x1080"}
  },
  {
    "event": "recording.started",
    "time": "2026-03-12T10:30:05+00:00",
    "elapsed": 5.2,
    "details": {"name": "login_test"}
  }
]
```

Event types: `display.started`, `display.stopped`, `panel.created`, `panel.updated`, `panel.removed`, `recording.started`, `recording.stopped`, `session.created`, `session.destroyed`, `cleanup`.

## Dashboard

A self-contained HTML dashboard that shows all active sessions with live MJPEG streams and a combined event log.

```bash
# Open in your browser:
open http://localhost:9123/dashboard
```

The dashboard auto-refreshes sessions every 5 seconds and polls for new events every 3 seconds. Each session card shows a live stream thumbnail and recording status.

## Thread Safety

All endpoints that mutate recorder state are protected by a `threading.Lock`. Concurrent callers (e.g., multiple SDK clients or panel updates from different threads) are safe.
