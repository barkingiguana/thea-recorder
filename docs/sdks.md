# SDK Overview

Thin HTTP client libraries for the recorder server, available in 5 languages. Each SDK wraps the REST API with idiomatic method calls, error handling, and convenience helpers.

## Quick Start

Every SDK follows the same pattern — connect, record, done:

### Go

```go
client := recorder.NewClient("http://localhost:9123")
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
| Go | `go get github.com/BarkingIguana/thea-recorder/sdks/go` |
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
| `add_panel(name, title, width)` | Add overlay panel |
| `update_panel(name, text, focus_line)` | Update panel content |
| `remove_panel(name)` | Remove panel |
| `list_panels()` | List all panels |
| `start_recording(name)` | Begin recording |
| `stop_recording()` | Stop recording, get path + elapsed |
| `recording_elapsed()` | Get elapsed seconds |
| `recording_status()` | Get recording state |
| `list_recordings()` | List available MP4 files |
| `download_recording(name, path)` | Download MP4 to local file |
| `recording_info(name)` | Get file metadata |
| `health()` | Server health check |
| `cleanup()` | Full teardown |

## Convenience Helpers

Every SDK provides scoped helpers that handle start/stop automatically:

| Helper | Description |
|---|---|
| `recording(name)` | Start recording, run code, stop recording (even on error) |
| `with_panel(name, ...)` | Add panel, run code, remove panel |
| `wait_until_ready(timeout)` | Poll `/health` until server responds |

## Configuration

All SDKs support:

| Config | Method |
|---|---|
| URL | Constructor argument |
| `RECORDER_URL` | Environment variable (fallback if no URL passed) |
| Timeout | Configurable (default 30s) |

## Per-SDK Documentation

- [Go SDK](../sdks/go/README.md)
- [Python SDK](../sdks/python/README.md)
- [Node SDK](../sdks/node/README.md)
- [Ruby SDK](../sdks/ruby/README.md)
- [Java SDK](../sdks/java/README.md)
