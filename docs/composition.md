# Video Composition: Side-by-Side Recordings

Compose multiple independent recordings into a single video.  Each
recording becomes a tile, arranged side-by-side, stacked, or in a grid.
You can highlight individual tiles at specific moments to draw attention
to where the action is happening.

This is useful for:

- **Multi-user demos** — show two users collaborating in real time
- **Before/after comparisons** — old vs new side by side
- **Parallel test runs** — see what each browser/app was doing at the same time
- **Multi-window workflows** — terminal + GUI + browser in one video

---

## Quick start

The simplest possible composition: take two recordings and put them
side by side.

```bash
# Record two sessions (separately, as normal)
thea start-display
thea start-recording --name session_a
# ... run app A on DISPLAY :99 ...
thea stop-recording

thea start-recording --name session_b
# ... run app B on DISPLAY :99 ...
thea stop-recording

# Compose them
thea compose --name side_by_side --recordings session_a,session_b
```

That's it.  You get `side_by_side.mp4` in the output directory with both
recordings tiled next to each other.

---

## Step-by-step examples

### 1. Two recordings, side by side (Python)

The absolute minimum:

```python
from thea import RecorderClient

client = RecorderClient("http://localhost:9123")

# Record two things (sequentially for simplicity)
client.start_display()

with client.recording("left"):
    pass  # ... your first application ...

with client.recording("right"):
    pass  # ... your second application ...

# Compose them side by side
client.create_composition("demo", recordings=["left", "right"])
client.wait_for_composition("demo")
```

### 2. Add labels so you know which tile is which

```python
client.create_composition(
    "demo",
    recordings=["alice_checkout", "bob_checkout"],
    labels=True,   # <-- this is the default
)
client.wait_for_composition("demo")
```

Each tile gets a text label in the top-left corner showing the recording
name.  To hide them, pass `labels=False`.

### 3. Highlight the active session

When composing a multi-user demo, it helps to glow a border around
whichever tile is about to do something:

```python
client.create_composition(
    "demo",
    recordings=["alice", "bob"],
    highlights=[
        # At t=2.0s, highlight Alice's tile for 3 seconds
        {"recording": "alice", "time": 2.0, "duration": 3.0},
        # At t=6.0s, highlight Bob's tile for 2 seconds
        {"recording": "bob", "time": 6.0, "duration": 2.0},
        # At t=9.0s, highlight Alice again
        {"recording": "alice", "time": 9.0, "duration": 2.0},
    ],
)
result = client.wait_for_composition("demo")
print(result["output_path"])
```

The highlight is a coloured glow border that appears and disappears
at the specified times.

### 4. Use the context manager to track highlights automatically

Instead of calculating timestamps yourself, use `composed_recording()`
which tracks elapsed time for you:

```python
with client.composed_recording("demo", ["alice", "bob"]) as comp:
    # Highlight Alice — the timestamp is recorded automatically
    comp.highlight("alice", duration=2.0)

    # ... drive Alice's session for a bit ...
    time.sleep(3)

    # Now highlight Bob
    comp.highlight("bob", duration=2.0)

    # ... drive Bob's session ...
    time.sleep(3)

# comp.result has the final composition status
print(comp.result["output_path"])
```

### 5. Parallel sessions with highlights

The most common real-world pattern: multiple sessions recording
simultaneously, with highlights showing who's active:

```python
import threading
import time
from thea import RecorderClient

client = RecorderClient("http://localhost:9123")

def user_flow(session_name, actions):
    client.create_session(session_name)
    try:
        client.use_session(session_name)
        client.start_display()

        with client.recording(f"rec_{session_name}"):
            for action in actions:
                client.update_panel("status", action)
                time.sleep(2)
    finally:
        client.delete_session(session_name)

# Run two users in parallel
alice_thread = threading.Thread(
    target=user_flow,
    args=("alice", ["Logging in", "Browsing products", "Checking out"]),
)
bob_thread = threading.Thread(
    target=user_flow,
    args=("bob", ["Logging in", "Searching", "Adding to cart"]),
)

alice_thread.start()
bob_thread.start()
alice_thread.join()
bob_thread.join()

# Compose with highlights
client.create_composition(
    "multi_user",
    recordings=["rec_alice", "rec_bob"],
    highlights=[
        {"recording": "rec_alice", "time": 0.0, "duration": 2.0},
        {"recording": "rec_bob",   "time": 2.0, "duration": 2.0},
        {"recording": "rec_alice", "time": 4.0, "duration": 2.0},
        {"recording": "rec_bob",   "time": 4.0, "duration": 2.0},
    ],
)
result = client.wait_for_composition("multi_user")
print(f"Video: {result['output_path']}")
```

### 6. Three or more tiles in a grid

For more than two recordings, `grid` layout arranges them automatically:

```python
client.create_composition(
    "grid_demo",
    recordings=["user_1", "user_2", "user_3", "user_4"],
    layout="grid",  # 2×2 grid
)
```

Layout options:

| Layout | Effect |
|--------|--------|
| `"row"` | Side by side horizontally (default) |
| `"column"` | Stacked vertically |
| `"grid"` | Auto rows × columns (e.g. 4 → 2×2, 6 → 3×2) |

### 7. Customise the highlight appearance

```python
client.create_composition(
    "demo",
    recordings=["a", "b"],
    highlights=[{"recording": "a", "time": 1.0, "duration": 3.0}],
    highlight_color="f85149",   # red instead of the default teal
    highlight_width=8,          # thicker border (default is 6)
)
```

### 8. Stacked vertically

```python
client.create_composition(
    "stacked",
    recordings=["terminal_session", "browser_session"],
    layout="column",
)
```

---

## CLI reference

### `thea compose`

Create a composed video from multiple recordings.

```
thea compose --name NAME --recordings REC1,REC2[,REC3...] [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--name` | required | Output video name |
| `--recordings` | required | Comma-separated recording names |
| `--layout` | `row` | `row`, `column`, or `grid` |
| `--labels/--no-labels` | `--labels` | Show recording names on tiles |
| `--highlight` | — | `recording:time:duration` (repeatable) |
| `--highlight-color` | `00d4aa` | Hex colour for highlight border |
| `--highlight-width` | `6` | Border thickness in pixels |
| `--wait/--no-wait` | `--wait` | Wait for rendering to finish |

Examples:

```bash
# Simple side by side
thea compose --name demo --recordings left,right

# Vertical stack
thea compose --name stacked --recordings top,bottom --layout column

# With highlights
thea compose --name demo --recordings alice,bob \
  --highlight alice:2.0:3.0 \
  --highlight bob:6.0:2.0

# Red highlights, thicker border
thea compose --name demo --recordings a,b \
  --highlight a:1.0:2.0 \
  --highlight-color f85149 --highlight-width 8

# Don't wait for rendering
thea compose --name demo --recordings a,b --no-wait
thea compose-status --name demo
```

### `thea compose-status`

Check the status of a composition.

```bash
thea compose-status --name demo
# {"name": "demo", "status": "complete", "output_path": "/tmp/recordings/demo.mp4", ...}
```

### `thea list-compositions`

List all compositions.

```bash
thea list-compositions
# [{"name": "demo", "status": "complete", ...}]
```

---

## HTTP API reference

### Create composition

```bash
curl -X POST http://localhost:9123/compositions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "demo",
    "recordings": ["alice", "bob"],
    "layout": "row",
    "labels": true,
    "highlights": [
      {"recording": "alice", "time": 2.0, "duration": 3.0},
      {"recording": "bob", "time": 6.0, "duration": 2.0}
    ],
    "highlight_color": "00d4aa",
    "highlight_width": 6
  }'
```

**Response** `202 Accepted`:
```json
{"name": "demo", "status": "rendering"}
```

Rendering happens in the background.  Poll `GET /compositions/{name}`
for the result.

### Get composition status

```bash
curl http://localhost:9123/compositions/demo
```

**Response** `200`:
```json
{
  "name": "demo",
  "status": "complete",
  "recordings": ["alice", "bob"],
  "output_path": "/tmp/recordings/demo.mp4",
  "output_size": 4521984,
  "layout": "row",
  "labels": true,
  "highlights": [
    {"recording": "alice", "time": 2.0, "duration": 3.0}
  ]
}
```

Status values: `"pending"`, `"rendering"`, `"complete"`, `"failed"`.

### List compositions

```bash
curl http://localhost:9123/compositions
```

**Response** `200`:
```json
[
  {"name": "demo", "status": "complete", "recordings": ["alice", "bob"]}
]
```

### Delete composition

```bash
curl -X DELETE http://localhost:9123/compositions/demo
```

**Response** `200`:
```json
{"status": "removed"}
```

### Add highlight (separately)

You can add highlights to an existing composition before it renders:

```bash
curl -X POST http://localhost:9123/compositions/demo/highlights \
  -H "Content-Type: application/json" \
  -d '{"recording": "alice", "time": 5.0, "duration": 2.0}'
```

**Response** `201`:
```json
{"status": "added"}
```

### List highlights

```bash
curl http://localhost:9123/compositions/demo/highlights
```

**Response** `200`:
```json
[
  {"recording": "alice", "time": 2.0, "duration": 3.0},
  {"recording": "bob", "time": 6.0, "duration": 2.0}
]
```

---

## SDK reference

All SDKs have the same methods.  Here's a quick reference for each language.

### Python

```python
# Create and wait
client.create_composition("demo", recordings=["a", "b"])
result = client.wait_for_composition("demo")

# With all options
client.create_composition(
    "demo",
    recordings=["a", "b", "c"],
    layout="grid",
    labels=True,
    highlights=[{"recording": "a", "time": 1.0, "duration": 2.0}],
    highlight_color="f85149",
    highlight_width=8,
)

# Context manager
with client.composed_recording("demo", ["a", "b"]) as comp:
    comp.highlight("a", duration=2.0)
    # ...
```

### Go

```go
status, err := client.CreateComposition(ctx, thea.CompositionRequest{
    Name:       "demo",
    Recordings: []string{"a", "b"},
    Layout:     "row",
    Labels:     true,
    Highlights: []thea.CompositionHighlight{
        {Recording: "a", Time: 2.0, Duration: 3.0},
    },
})

result, err := client.WaitForComposition(ctx, "demo", 120*time.Second)
```

### TypeScript / Node

```typescript
await client.createComposition({
  name: "demo",
  recordings: ["a", "b"],
  highlights: [{ recording: "a", time: 2.0, duration: 3.0 }],
});

const result = await client.waitForComposition("demo");
```

### Ruby

```ruby
client.create_composition(
  name: "demo",
  recordings: ["a", "b"],
  highlights: [{ recording: "a", time: 2.0, duration: 3.0 }],
)

result = client.wait_for_composition(name: "demo")
```

### Java

```java
client.createComposition("demo", List.of("a", "b"));
var result = client.waitForComposition("demo", 120_000);
```

---

## How it works

1. You record sessions independently — each gets its own MP4.
2. You call `create_composition` with the list of recordings to combine.
3. The server runs ffmpeg in a background thread:
   - Scales each input to equal tile dimensions (640×360 by default)
   - Tiles them using the `xstack` filter
   - Pads shorter recordings with black frames so they all match the longest
   - Overlays timed `drawbox` borders for highlights
   - Adds `drawtext` labels if enabled
4. You poll (or use `wait_for_composition`) until the status is `"complete"`.
5. The composed video is in the same output directory as your recordings.

### Duration alignment

If recordings have different lengths, the shorter ones are padded with
their last frame (cloned) to match the longest recording.  This means
the composed video is always as long as the longest input.

### System requirements

Composition uses ffmpeg's `xstack` filter, which requires **ffmpeg 4.1+**
(released 2018).  Most modern systems have this.

```bash
ffmpeg -filters 2>&1 | grep xstack
# Should show: ... xstack  ... Stack video inputs into custom layout.
```
