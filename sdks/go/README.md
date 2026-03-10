# thea-recorder Go SDK

A Go client library for the [thea-recorder](https://github.com/BarkingIguana/thea-recorder) HTTP server. Zero external dependencies — uses only the Go standard library.

## Installation

```bash
go get github.com/BarkingIguana/thea-recorder/sdks/go
```

## Quick start

```go
package main

import (
    "context"
    "log"
    "time"

    "github.com/BarkingIguana/thea-recorder/sdks/go/recorder"
)

func main() {
    client := recorder.NewClient("") // reads RECORDER_URL env, defaults to localhost:2233

    ctx := context.Background()

    // Wait for the server to be ready.
    if err := client.WaitUntilReady(ctx, 10*time.Second); err != nil {
        log.Fatal(err)
    }

    // Start the virtual display.
    if err := client.StartDisplay(ctx); err != nil {
        log.Fatal(err)
    }

    // Record a session.
    stop, err := client.Recording(ctx, "demo")
    if err != nil {
        log.Fatal(err)
    }
    defer stop()

    // Use panels to display content.
    client.WithPanel(ctx, "editor", "Code", 80, func() error {
        return client.UpdatePanel(ctx, "editor", "fmt.Println(\"hello\")", 1)
    })
}
```

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `NewClient(url)` | Server base URL. Pass `""` to use `RECORDER_URL` env or the default. | `http://localhost:2233` |
| `SetTimeout(d)` | HTTP client timeout. | 30 seconds |

## API reference

### Display

| Method | Description |
|--------|-------------|
| `StartDisplay(ctx)` | Start the virtual X display |
| `StopDisplay(ctx)` | Stop the virtual X display |

### Panels

| Method | Description |
|--------|-------------|
| `AddPanel(ctx, name, title, width)` | Create a new panel |
| `UpdatePanel(ctx, name, text, focusLine)` | Update panel content |
| `RemovePanel(ctx, name)` | Delete a panel |
| `ListPanels(ctx)` | List all panels |
| `WithPanel(ctx, name, title, width, fn)` | Scoped panel — removed after `fn` returns |

### Recording

| Method | Description |
|--------|-------------|
| `StartRecording(ctx, name)` | Begin recording |
| `StopRecording(ctx)` | Stop recording, returns `*RecordingResult` |
| `Recording(ctx, name)` | Returns a `stop` func — ideal with `defer` |
| `RecordingElapsed(ctx)` | Elapsed seconds of current recording |
| `RecordingStatusInfo(ctx)` | Full recording status |
| `ListRecordings(ctx)` | List all stored recordings |
| `GetRecordingInfo(ctx, name)` | Metadata for a single recording |
| `DownloadRecording(ctx, name, w)` | Stream MP4 to an `io.Writer` |
| `DownloadRecordingToFile(ctx, name, path)` | Download MP4 to a local file |

### Utility

| Method | Description |
|--------|-------------|
| `Health(ctx)` | Server health check |
| `Cleanup(ctx)` | Trigger server-side cleanup |
| `WaitUntilReady(ctx, timeout)` | Poll `/health` until the server responds |

## Error handling

All methods return errors. HTTP errors are wrapped in `*RecorderError`:

```go
var recErr *recorder.RecorderError
if errors.As(err, &recErr) {
    log.Printf("HTTP %d: %s", recErr.StatusCode, recErr.Body)
}
```

## Testing

```bash
cd sdks/go
go test ./...
```
