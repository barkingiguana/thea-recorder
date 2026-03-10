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
| `--browser-size` | `1920x1080` | Virtual display resolution |
| `--framerate` | `15` | Recording FPS |
| `--cors` | off | Enable CORS headers for browser access |

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

### Panels

#### Create panel
```bash
curl -X POST http://localhost:9123/panels \
  -H "Content-Type: application/json" \
  -d '{"name": "status", "title": "Status", "width": 120}'
```
**Response** `201`:
```json
{"name": "status", "title": "Status", "width": 120}
```
`width` is optional (null = auto-width). `title` defaults to empty string.

**Error** `400` if `name` is missing or `width` is invalid.

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

Enable CORS with `--cors` to allow browser-based dashboards to access recordings:

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
lets you record 2–3 concurrent browser sessions without running multiple servers.

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

## Thread Safety

All endpoints that mutate recorder state are protected by a `threading.Lock`. Concurrent callers (e.g., multiple SDK clients or panel updates from different threads) are safe.
