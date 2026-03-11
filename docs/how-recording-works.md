# How Recording Works

This guide explains what Thea does under the hood, what kinds of applications
you can record, and how to set things up correctly. If you're new to Xvfb or
X11, start here.

---

## The big picture (ELI5)

Thea records applications by pointing a virtual camera at a virtual screen.

Think of it like this:

1. **Xvfb** is a fake computer monitor that exists only in memory. Programs
   think they're drawing windows on a real screen, but there's no physical
   display — just pixels in RAM.

2. **Your application** (a browser, a terminal, a spreadsheet — anything with
   a window) draws itself on this fake screen.

3. **ffmpeg** acts as a camera pointed at that fake screen, encoding everything
   it sees into an MP4 video file.

4. **Thea** orchestrates all of this: it starts the fake screen, tells ffmpeg
   to start recording, and optionally draws an info bar with panels below your
   application.

```
┌──────────────────────────────────────────────┐
│              Your computer / container        │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │          Xvfb (virtual screen)         │  │
│  │                                        │  │
│  │   ┌────────────────────────────────┐   │  │
│  │   │                                │   │  │
│  │   │    Your application draws      │   │  │
│  │   │    its window here             │   │  │
│  │   │                                │   │  │
│  │   └────────────────────────────────┘   │  │
│  │                                        │  │
│  │   ┌──────────┐ ┌──────────────────┐   │  │
│  │   │  Panel 1 │ │  Panel 2         │   │  │
│  │   │  (Thea)  │ │  (Thea)          │   │  │
│  │   └──────────┘ └──────────────────┘   │  │
│  └────────────────────────────────────────┘  │
│       ▲                                      │
│       │  ffmpeg reads pixels from Xvfb       │
│       │  and writes video.mp4                │
│                                              │
└──────────────────────────────────────────────┘
```

That's the whole trick. No network protocols, no screen sharing, no VNC. Just
a program drawing pixels into a memory buffer, and ffmpeg reading those pixels
out.

---

## What is X11?

X11 (also called "X Window System" or just "X") is the display system used on
Linux to draw graphical interfaces. When you open a browser, a text editor, or
a terminal on a Linux desktop, X11 is what puts the windows on your screen.

Every X11 program needs to know *which screen to draw on*. It figures this out
from the **`DISPLAY` environment variable**:

```bash
# "Draw on screen number 99"
export DISPLAY=:99
```

When Thea starts Xvfb, it creates a virtual screen — say, `:99`. Any program
you launch with `DISPLAY=:99` will draw its windows on that virtual screen,
where Thea's ffmpeg can record them.

**This is the key to understanding Thea**: you launch your application with
`DISPLAY` set to Thea's display, and your application appears in the recording.
That's it.

---

## What can be recorded?

Anything that draws an X11 window:

| Application type | Examples | Notes |
|-----------------|----------|-------|
| **Web browsers** | Chrome, Chromium, Firefox | Driven by Selenium, Playwright, Cypress, or manually |
| **Terminal emulators** | xterm, xfce4-terminal, urxvt | For recording CLI tools — see [Terminal recording](#terminal-recording) |
| **Office apps** | LibreOffice, Gnumeric | Spreadsheets, documents, presentations |
| **Image/design** | GIMP, Inkscape | Any GTK or Qt application |
| **Custom GUI apps** | Electron apps, Java Swing, Tkinter | Anything that opens a window |
| **Desktop automation** | xdotool | Simulating mouse clicks and keyboard input |

### What can NOT be recorded

- **Stdout/stderr alone**: If your program only prints text to a terminal and
  doesn't open a window, nothing appears on the virtual screen. You need a
  terminal emulator (like xterm) to make text visible. See
  [Terminal recording](#terminal-recording).
- **Wayland-only applications**: Thea uses X11 (Xvfb). Apps that only support
  Wayland won't work. Most Linux GUI apps still support X11.
- **macOS/Windows native GUIs**: Xvfb is Linux-only. Thea records X11
  applications.

---

## The co-location rule

> **Thea, Xvfb, and your application must run on the same machine.**

This is the most important thing to understand. Thea works by reading pixels
directly from Xvfb's memory buffer. There is no network protocol involved.
Your application must draw on the same virtual screen that Thea is recording.

### What "same machine" means in practice

- **Same bare-metal server or VM**: Thea, Xvfb, and your app are all
  processes on the same OS.
- **Same Docker container**: Everything runs in one container.
- **Same Kubernetes pod** (with shared process namespace): Containers in the
  same pod can share `/tmp/.X11-unix/`.

### What does NOT work

- Running Thea in one Docker container and your application in a different
  container (they can't share the display socket).
- Running Thea on machine A and your application on machine B.
- Using Thea as a remote screen-capture tool — it isn't one.

### But I want to control things remotely...

That's fine! The **Thea client** (HTTP API, CLI, SDKs) can run anywhere. The
control plane is just HTTP:

```
┌─────────────────────────────────────┐      ┌─────────────────────┐
│  Machine / Container A              │      │  Machine B          │
│                                     │      │                     │
│  Thea server ◄──── Xvfb            │ HTTP │  Your test runner   │
│       ▲              ▲              │◄─────│  (pytest, etc.)     │
│       │              │              │      │  uses Thea client   │
│     ffmpeg      Your application    │      │  to start/stop      │
│                 (must be here!)     │      │  recording           │
└─────────────────────────────────────┘      └─────────────────────┘
```

Your test runner on Machine B can tell Thea to start recording, but the
application being recorded must be on Machine A alongside Thea.

**Exception — remote browser control**: If you're using Selenium with
RemoteWebDriver, the *browser* must be on the same machine as Thea, but the
Selenium *client* (test code) can be elsewhere:

```
┌─────────────────────────────────────┐      ┌─────────────────────┐
│  Machine / Container A              │      │  Machine B          │
│                                     │      │                     │
│  Thea server                        │      │  Test code          │
│  Xvfb (:99)                         │ HTTP │  Selenium client    │
│  ChromeDriver ◄── Chromium          │◄─────│  (RemoteWebDriver)  │
│                   (DISPLAY=:99)     │      │                     │
│  ffmpeg (records :99)               │      │  Thea client        │
└─────────────────────────────────────┘      └─────────────────────┘
```

---

## Three recording patterns

Every recording follows the same shape:

1. Start Thea's display (Xvfb)
2. Launch your application on that display (`DISPLAY=:99`)
3. Start recording
4. Do things with your application
5. Stop recording

The only difference between recording a browser, a terminal, or a GUI app is
step 2 — how you launch the application. Thea doesn't need to know or care
what application you're recording.

### Pattern 1: Browser via Selenium

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from thea import Recorder

rec = Recorder(output_dir="./videos")
rec.start_display()

# Launch Chrome on Thea's display
options = Options()
options.add_argument("--no-sandbox")
options.add_argument("--disable-gpu")
options.add_argument("--disable-dev-shm-usage")

# The key line: Chrome draws on Thea's virtual screen
driver = webdriver.Chrome(options=options)
driver.set_window_size(1920, 1080)

rec.start_recording("selenium-test")

driver.get("https://example.com")
# ... interact with the page ...

rec.stop_recording()
driver.quit()
rec.cleanup()
```

The `DISPLAY` environment variable is inherited from the process. Since Thea
set it when starting the display, Chrome picks it up automatically. If you
need to be explicit:

```python
import os
os.environ["DISPLAY"] = rec.display_string
```

Or use `rec.display_env` to get a complete environment dict:

```python
import subprocess
subprocess.Popen(["chromium"], env=rec.display_env)
```

### Pattern 2: Terminal (xterm)

Terminal recording is slightly more involved because CLI programs write to
stdout, not to a window. You need a terminal emulator to make the text visible.

```python
import subprocess
import os
from thea import Recorder

rec = Recorder(output_dir="./videos", display_size="1280x720")
rec.start_display()
rec.start_recording("cli-demo")

# Launch xterm on Thea's display
# -geometry COLSxROWS+X+Y positions and sizes the window
# -fa/-fs set the font family and size
# -b 0 removes internal border padding
xterm = subprocess.Popen(
    [
        "xterm",
        "-geometry", "132x40+0+0",
        "-fa", "DejaVu Sans Mono",
        "-fs", "14",
        "-b", "0",
        "-e", "tail", "-f", "/tmp/myapp.log",
    ],
    env=rec.display_env,
)

# Now pipe your application's output to the log file
with open("/tmp/myapp.log", "w") as log:
    subprocess.run(["my-cli-tool", "--verbose"], stdout=log, stderr=log)

rec.stop_recording()
xterm.terminate()
rec.cleanup()
```

**Tip — matching column widths**: CLI tools that use Rich, Click, or similar
libraries detect terminal width from `COLUMNS`. If your xterm is 132 columns
wide, tell your subprocess:

```python
env = {**os.environ, "COLUMNS": "132", "LINES": "40"}
subprocess.run(cmd, stdout=log, stderr=log, env=env)
```

### Pattern 3: GUI application

GUI apps are the simplest — they already draw windows. Just launch them on
Thea's display:

```python
import subprocess
import time
from thea import Recorder

rec = Recorder(output_dir="./videos")
rec.start_display()
rec.start_recording("spreadsheet-demo")

# Launch a spreadsheet on Thea's display
app = subprocess.Popen(
    ["gnumeric", "my-spreadsheet.gnumeric"],
    env=rec.display_env,
)

time.sleep(5)  # Let the app render

rec.stop_recording()
app.terminate()
rec.cleanup()
```

---

## Terminal recording

Recording terminal output deserves extra attention because it has a few
non-obvious gotchas.

### Why you need a terminal emulator

When you run `python myscript.py` in a regular terminal, you see the output
because your terminal emulator (iTerm, GNOME Terminal, etc.) renders the text
as pixels on screen.

On a headless server with Xvfb, there's no terminal emulator running. If your
script writes to stdout, those characters go nowhere visible — they're not
drawn on the virtual screen. You need to explicitly launch a terminal emulator
(like xterm) on the Xvfb display and route your output into it.

### Sizing xterm to fill the viewport

xterm sizes itself in **character cells** (columns × rows), not pixels. This
means you can't just say "be 1280×720 pixels" — you need to calculate the
right number of columns and rows for your chosen font size.

Rough formula:
- **Columns** ≈ `display_width / (font_size × 0.6)`
- **Rows** ≈ `display_height / (font_size × 1.2)`

For a 1280×720 display with 14px font:
- Columns ≈ `1280 / 8.4 ≈ 152`
- Rows ≈ `720 / 16.8 ≈ 42`

Use `-geometry 152x42+0+0` and `-b 0` (no internal border) to fill the
viewport as closely as possible. There may be a small black border due to
rounding — this is normal.

---

## Docker setup

When running in Docker, you need to install the X11 and video dependencies.
Here's a typical Dockerfile:

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb ffmpeg x11-xserver-utils fonts-dejavu-core \
    # For terminal recording:
    xterm \
    # For browser recording:
    chromium chromium-driver \
    # For GUI app recording:
    gnumeric \
    && rm -rf /var/lib/apt/lists/*

# Install Thea
RUN pip install thea-recorder

# Everything runs in this one container:
# Thea + Xvfb + ffmpeg + your application
```

Note: **everything is in one container**. Thea, Xvfb, ffmpeg, and whatever
application you're recording must all be in the same environment.

Set `shm_size: 2g` (or `--shm-size=2g`) when running the container — Chrome
and ffmpeg both use shared memory heavily and the default 64MB is not enough:

```yaml
services:
  recorder:
    build: .
    shm_size: 2g
```

---

## How Thea uses Xvfb and ffmpeg (technical details)

For the curious, here's exactly what happens under the hood:

### Starting the display

```python
rec.start_display()
```

1. Thea launches `Xvfb :99 -screen 0 1920x1380x24 -ac`
   - `:99` — display number (configurable)
   - `1920x1380` — viewport width × (viewport height + panel bar height)
   - `x24` — 24-bit colour
   - `-ac` — disable access control (any process can draw)
2. Waits for `/tmp/.X11-unix/X99` socket to appear (up to 5 seconds)
3. Runs `xsetroot -cursor_name left_ptr` to set a visible mouse cursor

### Starting a recording

```python
rec.start_recording("my-test")
```

1. Validates the panel layout (warns about overlaps or overflow)
2. Builds an ffmpeg filter chain for the panel bar (background, dividers,
   titles, text content, clock)
3. Launches ffmpeg:
   ```
   ffmpeg -y -f x11grab -video_size 1920x1380 -framerate 15
     -draw_mouse 1 -i :99
     -vf "drawbox=...,drawtext=...,..."
     -codec:v libx264 -preset ultrafast -crf 23
     -pix_fmt yuv420p -movflags +faststart
     my-test.mp4
   ```
4. ffmpeg reads pixels from the Xvfb framebuffer every 1/15th of a second

### Panel updates

```python
rec.update_panel("status", "Step 3: Login")
```

1. Writes the text to a temp file (atomic rename)
2. ffmpeg's `drawtext` filter has `reload=1`, so it re-reads the file on
   every frame
3. The panel content updates in the video within one frame (1/15th second)

### Stopping

```python
rec.stop_recording()
```

1. Sends `q` to ffmpeg's stdin (graceful quit)
2. ffmpeg finalises the MP4 (writes moov atom, flushes buffers)
3. The finished video file is ready to play
