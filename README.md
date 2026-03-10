# thea-recorder

**Record your Xvfb virtual display as MP4 video with live panel overlays and interactive HTML reports.**

thea-recorder captures anything running in a virtual display — browser-based E2E tests, GUI applications, desktop automation scripts, product demos — as an MP4 video with a live overlay bar showing status panels, step timelines, and custom context. It then generates an interactive HTML report where you can click any step and watch exactly what happened.

## Why

When something visual runs in CI — a test, a demo, a GUI app — and it fails, you're left staring at logs trying to imagine what the screen was doing. The typical debugging cycle:

1. Read the failure log
2. Try to reproduce locally
3. Add more logging
4. Push, wait for CI, read logs again
5. Repeat

This is absurd. The screen was *right there* doing the thing. You just weren't watching.

thea-recorder fixes this by recording the virtual display during execution. Every session gets its own MP4. The panel overlay shows you the current status and any custom context you want. The HTML report lets you click a step and the video seeks to that exact moment.

**You stop guessing. You start watching.**

## What can you record?

Anything that runs in an Xvfb virtual display:

- **Browser-based E2E tests** — Selenium, Playwright, Cypress, any browser automation
- **GUI applications** — GTK, Qt, Electron, or any X11 windowed app
- **Terminal sessions** — xterm, xfce4-terminal, or any terminal emulator running in X11
- **Games and simulations** — solitaire, chess, or any graphical program
- **Product demos** — scripted walkthroughs for sales, onboarding, or documentation

If it has a window and can run on X11, thea can record it.

## Features

- **HTTP server + native SDKs** — use from Go, Python, Ruby, TypeScript, or Java
- **CLI** — server mode and client mode, scriptable from any language
- **Panel overlay system** — named columns below the viewport with live-updating text
- **Smart scrolling** — panels auto-scroll to keep the active content visible
- **Interactive HTML reports** — embedded videos with clickable step timelines
- **Video composition** — tile multiple recordings side-by-side with highlight borders
- **Framework agnostic** — works with any test runner, GUI app, or automation script
- **Docker ready** — example Dockerfile and E2E test suite included

## Install

```bash
# Client only (zero dependencies — for test suites and automation scripts)
pip install thea-recorder

# Server + CLI (includes Flask and Click)
pip install thea-recorder[server]
```

System dependencies (for the server, in your Docker image or CI runner):
```bash
apt install xvfb ffmpeg x11-xserver-utils fonts-dejavu-core
```

## Quick start — HTTP server

Start the server:
```bash
thea serve --port 9123
```

Then use any SDK:

**Go**
```go
client := recorder.NewClient("http://localhost:9123")
client.StartDisplay(ctx)
stop, _ := client.Recording(ctx, "login_test")
defer stop()
// ... run your application ...
```

**Python**
```python
from thea import RecorderClient
client = RecorderClient("http://localhost:9123")
client.start_display()
with client.recording("login_test"):
    # ... run your application ...
    pass
```

**TypeScript**
```typescript
const client = new RecorderClient({ url: "http://localhost:9123" });
await client.startDisplay();
await client.recording("login_test", async () => {
  // ... run your application ...
});
```

**Ruby**
```ruby
client = Recorder::Client.new("http://localhost:9123")
client.start_display
client.recording("login_test") do
  # ... run your application ...
end
```

**Java**
```java
try (var client = new RecorderClient("http://localhost:9123")) {
    client.startDisplay();
    client.recording("login_test", c -> {
        // ... run your application ...
    });
}
```

## Quick start — Python library

```python
from thea import Recorder, generate_report

recorder = Recorder(output_dir="./recordings", display=99)
recorder.add_panel("status", title="Status", width=120)
recorder.add_panel("steps", title="Steps")
recorder.start_display()

recorder.start_recording("login_test")
recorder.update_panel("status", "Running")
recorder.update_panel("steps", "  Given a user\n* When I log in\n  Then I see the dashboard")

# ... run your application here (on DISPLAY :99) ...

video = recorder.stop_recording()

generate_report(
    videos=[{
        "feature": "Authentication",
        "scenario": "Login",
        "status": "passed",
        "video": video,
        "steps": [
            {"keyword": "Given", "name": "a user", "status": "passed", "offset": 0.0},
            {"keyword": "When", "name": "I log in", "status": "passed", "offset": 2.5},
            {"keyword": "Then", "name": "I see the dashboard", "status": "passed", "offset": 5.0},
        ],
    }],
    output_dir="./recordings",
    title="My Test Report",
)

recorder.cleanup()
```

## CLI

```bash
# Server mode
thea serve --host 0.0.0.0 --port 9123 --output-dir ./recordings --cors

# Client mode (talks to running server)
thea --server http://localhost:9123 start-display
thea --server http://localhost:9123 add-panel --name editor --title "Code" --width 80
thea --server http://localhost:9123 start-recording --name login_test
thea --server http://localhost:9123 stop-recording
thea --server http://localhost:9123 list-recordings
thea --server http://localhost:9123 health
```

Set `THEA_URL` to avoid repeating `--server`:
```bash
export THEA_URL=http://localhost:9123
thea health
thea start-display
thea start-recording --name my-test
```

## Docker

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -qyy --no-install-recommends \
    chromium-driver xvfb ffmpeg x11-xserver-utils fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install thea-recorder[server]
EXPOSE 9123
CMD ["thea", "serve", "--host", "0.0.0.0", "--port", "9123"]
```

## Panel system

Panels are named overlay columns rendered below the application viewport in a dark bar. They update in real-time during recording.

```python
# Fixed-width panel
recorder.add_panel("status", title="Status", width=120)

# Auto-width panel (shares remaining space)
recorder.add_panel("log", title="Activity Log")

# Update content (atomically — no tearing in the video)
recorder.update_panel("log", "Line 1\nLine 2\nLine 3")

# Scroll to keep a specific line visible
recorder.update_panel("log", long_text, focus_line=current_step)
```

## Report

The HTML report is a single self-contained file with:

- Embedded MP4 video players per scenario
- Clickable step timelines that seek the video
- Video playback highlights the current step
- Feature/scenario grouping with pass/fail badges
- Dark theme, responsive layout
- Customisable title, subtitle, and logo

## Documentation

- [HTTP Server API](docs/server.md) — full endpoint reference
- [CLI Reference](docs/cli.md) — all commands and flags
- [SDK Quick Start](docs/sdks.md) — all 5 languages
- [Integration Guide](docs/integration-guide.md) — framework-specific examples
- [Video Composition](docs/composition.md) — side-by-side multi-session videos with highlight borders

## API

### `Recorder(output_dir, display, display_size, framerate, font, font_bold)`

| Param | Default | Description |
|---|---|---|
| `output_dir` | `/tmp/recordings` | Where MP4 files are saved |
| `display` | `99` | X11 display number |
| `display_size` | `1920x1080` | Application viewport resolution |
| `framerate` | `15` | Recording FPS |
| `font` | auto-detect | Path to regular TTF font |
| `font_bold` | auto-detect | Path to bold TTF font |

### Methods

| Method | Description |
|---|---|
| `start_display()` | Launch Xvfb |
| `stop_display()` | Terminate Xvfb |
| `add_panel(name, title, width)` | Register a panel |
| `remove_panel(name)` | Remove a panel |
| `update_panel(name, text, focus_line)` | Update panel content |
| `start_recording(filename)` | Start ffmpeg capture |
| `stop_recording()` | Stop capture, return MP4 path |
| `recording_elapsed` | Seconds since recording started |
| `cleanup()` | Stop everything, remove temp files |

### `generate_report(videos, output_dir, title, subtitle, logo_text)`

Takes a list of video metadata dicts and writes `report.html`.

## License

MIT
