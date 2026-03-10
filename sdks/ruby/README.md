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

# Wait for the server to be reachable
client.wait_until_ready(timeout: 30)

# Start the virtual display
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
| `stop_recording` | POST /recording/stop | Stop recording |
| `recording_elapsed` | GET /recording/elapsed | Get elapsed time |
| `recording_status` | GET /recording/status | Get recording status |
| `list_recordings` | GET /recordings | List all recordings |
| `download_recording(name, path)` | GET /recordings/{name} | Download MP4 to path |
| `recording_info(name)` | GET /recordings/{name}/info | Get recording metadata |
| `health` | GET /health | Health check |
| `cleanup` | POST /cleanup | Clean up resources |
| `wait_until_ready(timeout:)` | GET /health (polling) | Wait for server |
| `recording(name) { \|r\| ... }` | -- | Block with auto stop |
| `with_panel(name, ...) { ... }` | -- | Block with auto remove |

## Development

```bash
bundle install
bundle exec ruby test/test_recorder.rb
```
