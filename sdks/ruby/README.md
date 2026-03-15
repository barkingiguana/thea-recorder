# thea-recorder (Ruby)

Ruby SDK for the thea-recorder HTTP server. Zero runtime dependencies -- uses only Ruby stdlib (`net/http`).

## Installation

Add to your Gemfile:

```ruby
gem "thea-recorder", path: "sdks/ruby"
```

Or install from the gemspec:

```bash
cd sdks/ruby && bundle install
```

## Usage

```ruby
require "recorder"

client = Recorder::Client.new("http://localhost:3000")
# Or rely on THEA_URL env var:
# client = Recorder::Client.new

# Start the virtual display (auto-waits for server readiness)
client.start_display

# Add a panel
client.add_panel(name: "editor", title: "Code Editor", width: 80)
client.update_panel("editor", text: "puts 'hello'", focus_line: 1)

# Record a session
client.start_recording(name: "demo")
# ... do work ...
result = client.stop_recording
puts "Recorded #{result['elapsed']}s to #{result['path']}"

# Download the recording
client.download_recording("demo", "/tmp/demo.mp4")

# Stop recording and generate a GIF automatically
client.start_recording(name: "gif-demo")
# ... do work ...
client.stop_recording(gif: true, gif_fps: 15, gif_width: 640)

# Convert an existing recording to GIF
client.convert_to_gif("demo", fps: 10, width: 720)

# Download in different formats (mp4, gif, webm)
client.download_recording("demo", "/tmp/demo.gif", format: "gif")
client.download_recording("demo", "/tmp/demo.webm", format: "webm")

# Stop recording with multiple output formats
client.stop_recording(output_formats: ["mp4", "gif", "webm"])

# Clean up
client.remove_panel("editor")
client.stop_display
```

### Block syntax

Use the block helpers for automatic cleanup:

```ruby
client.recording("demo") do |r|
  r.with_panel("editor", title: "Editor", width: 80) do
    client.update_panel("editor", text: "hello world", focus_line: 1)
    sleep 2
  end
end
# Recording is stopped and panel is removed automatically,
# even if an exception is raised inside the block.

# Block syntax with GIF output
client.recording("demo", gif: true, gif_fps: 15) do |r|
  # ... do work ...
end

# Block syntax with multiple output formats
client.recording("demo", output_formats: ["mp4", "webm"]) do |r|
  # ... do work ...
end
```

### Error handling

All errors raise `Recorder::Error`:

```ruby
begin
  client.health
rescue Recorder::Error => e
  puts "Server error: #{e.message}"
end
```

### Configuration

```ruby
# Custom timeout (default: 30 seconds)
client = Recorder::Client.new("http://localhost:3000", timeout: 60)
```

## API Reference

| Method | HTTP | Description |
|---|---|---|
| `start_display` | POST /display/start | Start the virtual display |
| `stop_display` | POST /display/stop | Stop the virtual display |
| `add_panel(name:, title:, width:)` | POST /panels | Create a panel |
| `update_panel(name, text:, focus_line:)` | PUT /panels/{name} | Update panel content |
| `remove_panel(name)` | DELETE /panels/{name} | Remove a panel |
| `list_panels` | GET /panels | List all panels |
| `start_recording(name:)` | POST /recording/start | Start recording |
| `stop_recording(gif:, gif_fps:, gif_width:, output_formats:)` | POST /recording/stop | Stop recording (optionally generate GIF/other formats) |
| `recording_elapsed` | GET /recording/elapsed | Get elapsed time |
| `recording_status` | GET /recording/status | Get recording status |
| `list_recordings` | GET /recordings | List all recordings |
| `convert_to_gif(name, fps:, width:)` | POST /recordings/{name}/gif | Convert recording to GIF |
| `download_recording(name, path, format:)` | GET /recordings/{name} | Download recording to path (format: mp4, gif, webm) |
| `recording_info(name)` | GET /recordings/{name}/info | Get recording metadata |
| `health` | GET /health | Health check |
| `cleanup` | POST /cleanup | Clean up resources |
| `wait_until_ready(timeout:)` | GET /health (polling) | Wait for server. Called automatically on first API call. |
| `recording(name, gif:, output_formats:) { \|r\| ... }` | -- | Block with auto stop (supports GIF/format options) |
| `with_panel(name, ...) { ... }` | -- | Block with auto remove |

## Development

```bash
bundle install
bundle exec ruby test/test_recorder.rb
```
