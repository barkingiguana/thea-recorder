# SDK Overview

Thin HTTP client libraries for the recorder server, available in 5 languages. Each SDK wraps the REST API with idiomatic method calls, error handling, and convenience helpers.

## Quick Start

Every SDK follows the same pattern — connect, record, done:

### Go

```go
client := thea.NewClient("http://localhost:9123")
result, _ := client.Recording(ctx, "login_test", func() error {
    // ... your test code ...
    return nil
})
fmt.Println(result.Path)
```

### Python

```python
from thea import RecorderClient

client = RecorderClient("http://localhost:9123")
with client.recording("login_test") as result:
    pass  # ... your test code ...
print(result.path)
```

### Ruby

```ruby
require "recorder"

client = Recorder::Client.new("http://localhost:9123")
client.recording("login_test") do |result|
  # ... your test code ...
end
puts result.path
```

### Node / TypeScript

```typescript
import { RecorderClient } from "thea-recorder";

const client = new RecorderClient("http://localhost:9123");
const result = await client.recording("login_test", async () => {
  // ... your test code ...
});
console.log(result.path);
```

### Java

```java
var client = new RecorderClient("http://localhost:9123");
client.recording("login_test", () -> {
    // ... your test code ...
});
```

## Installation

| Language | Install |
|---|---|
| Go | `go get github.com/barkingiguana/thea-recorder/sdks/go` |
| Python | `pip install ./sdks/python` (or copy `thea/`) |
| Ruby | `gem build thea-recorder.gemspec && gem install thea-recorder-*.gem` |
| Node | `npm install ./sdks/node` |
| Java | `mvn install` from `sdks/java/` |

## Common API Surface

Every SDK provides:

| Method | Description |
|---|---|
| `start_display()` | Launch Xvfb |
| `stop_display()` | Stop Xvfb |
| `add_panel(name, title, width, bg_color, opacity)` | Add overlay panel (optional background color and opacity) |
| `update_panel(name, text, focus_line)` | Update panel content |
| `remove_panel(name)` | Remove panel |
| `list_panels()` | List all panels |
| `start_recording(name)` | Begin recording |
| `stop_recording(gif, output_formats)` | Stop recording, get path + elapsed. Optional `gif=True` or `output_formats=["gif","webm"]` for format conversion |
| `recording_elapsed()` | Get elapsed seconds |
| `recording_status()` | Get recording state |
| `add_annotation(label, time, details)` | Add a timestamped annotation to the active recording |
| `list_annotations()` | List annotations for the active recording |
| `convert_to_gif(name)` | Convert an existing recording to GIF (two-pass palette-based, 10fps, 720px width) |
| `convert_to_webm(name)` | Convert an existing recording to WebM (VP9) |
| `list_recordings()` | List available recordings (includes `formats_available` per entry) |
| `download_recording(name, path, format)` | Download recording to local file. Optional `format` (`"gif"`, `"webm"`) to download a converted version |
| `recording_info(name)` | Get file metadata |
| `display_screenshot(quality)` | Capture a JPEG screenshot of the live display |
| `display_stream_url(fps)` | Get the MJPEG stream URL |
| `display_viewer_url()` | Get the HTML live viewer URL |
| `recording_screenshot(name, time, quality)` | Extract a frame from a recorded video |
| `events(since)` | Get the session event log |
| `dashboard_url()` | Get the dashboard URL |
| `health()` | Server health check |
| `cleanup()` | Full teardown |

## Convenience Helpers

Every SDK provides scoped helpers that handle start/stop automatically:

| Helper | Description |
|---|---|
| `recording(name)` | Start recording, run code, stop recording (even on error) |
| `with_panel(name, ...)` | Add panel, run code, remove panel |
| `wait_until_ready(timeout)` | Poll `/health` until server responds. Called automatically on first API call. |

### Go SDK extras

The Go SDK provides additional helpers for error classification and idempotent operations:

| Helper | Description |
|---|---|
| `IsConflict(err)` | True if the error is a 409 Conflict (resource already exists) |
| `IsAccepted(err)` | True if the error is a 202 Accepted (async operation in progress) |
| `IsNotFound(err)` | True if the error is a 404 Not Found |
| `EnsureRecording(ctx, name)` | Idempotent recording start — returns existing status on 409 |
| `CreateCompositionAndWait(ctx, req, timeout)` | Create composition + poll until complete (handles 409) |

## Configuration

All SDKs support:

| Config | Method |
|---|---|
| URL | Constructor argument |
| `THEA_URL` | Environment variable (fallback if no URL passed) |
| Timeout | Configurable (default 30s) |

## Per-SDK Documentation

- [Go SDK](../sdks/go/README.md)
- [Python SDK](../sdks/python/README.md)
- [Node SDK](../sdks/node/README.md)
- [Ruby SDK](../sdks/ruby/README.md)
- [Java SDK](../sdks/java/README.md)
