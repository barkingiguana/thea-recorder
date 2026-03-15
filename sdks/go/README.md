# thea-recorder Go SDK

A Go client library for the [thea-recorder](https://github.com/barkingiguana/thea-recorder) HTTP server. Zero external dependencies — uses only the Go standard library.

## Installation

```bash
go get github.com/barkingiguana/thea-recorder/sdks/go
```

## Quick start

```go
package main

import (
    "context"
    "log"

    "github.com/barkingiguana/thea-recorder/sdks/go/thea"
)

func main() {
    client := thea.NewClient("") // reads THEA_URL env, defaults to localhost:9123

    ctx := context.Background()

    // Start the virtual display (auto-waits for server readiness).

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
| `NewClient(url)` | Server base URL. Pass `""` to use `THEA_URL` env or the default. | `http://localhost:9123` |
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
| `StopRecording(ctx, opts...)` | Stop recording, returns `*RecordingResult`. Pass `StopRecordingOptions` to request GIF/WebM output. |
| `Recording(ctx, name, opts...)` | Returns a `stop` func — ideal with `defer`. Accepts optional `StopRecordingOptions`. |
| `ConvertToGIF(ctx, name, fps, width)` | Convert an existing recording to GIF |
| `RecordingElapsed(ctx)` | Elapsed seconds of current recording |
| `RecordingStatusInfo(ctx)` | Full recording status |
| `ListRecordings(ctx)` | List all stored recordings |
| `GetRecordingInfo(ctx, name)` | Metadata for a single recording (includes GIF/WebM info if available) |
| `DownloadRecording(ctx, name, w)` | Stream recording to an `io.Writer` |
| `DownloadRecordingFormat(ctx, name, format, w)` | Stream recording in a specific format (`"mp4"`, `"gif"`, `"webm"`) to an `io.Writer` |
| `DownloadRecordingToFile(ctx, name, path)` | Download recording to a local file |

### Utility

| Method | Description |
|--------|-------------|
| `Health(ctx)` | Server health check |
| `Cleanup(ctx)` | Trigger server-side cleanup |
| `WaitUntilReady(ctx, timeout)` | Poll `/health` until the server responds. Called automatically on first API call. |

## Error handling

All methods return errors. HTTP errors are wrapped in `*RecorderError`:

```go
var recErr *thea.RecorderError
if errors.As(err, &recErr) {
    log.Printf("HTTP %d: %s", recErr.StatusCode, recErr.Body)
}
```

## GIF / WebM output

You can request GIF (or other format) output when stopping a recording:

```go
result, err := client.StopRecording(ctx, thea.StopRecordingOptions{
    GIF:      true,
    GIFFps:   10,
    GIFWidth: 640,
})
// result.GifPath contains the path to the generated GIF.
// result.ExtraPaths has any additional output format paths.
```

Or convert an existing recording after the fact:

```go
info, err := client.ConvertToGIF(ctx, "demo", 10, 640)
```

To download a recording in a specific format:

```go
f, _ := os.Create("demo.gif")
defer f.Close()
client.DownloadRecordingFormat(ctx, "demo", "gif", f)
```

The `Recording` helper also accepts options:

```go
stop, err := client.Recording(ctx, "demo", thea.StopRecordingOptions{GIF: true})
if err != nil { log.Fatal(err) }
defer stop()
```

## Testing

```bash
cd sdks/go
go test ./...
```
