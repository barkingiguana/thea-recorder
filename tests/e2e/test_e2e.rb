# E2E test for the Ruby SDK against a live recorder server.

require_relative "lib/recorder"

url = ENV["THEA_URL"] || "http://localhost:9123"
client = Recorder::Client.new(url)

puts "[ruby] Waiting for server..."
client.wait_until_ready(timeout: 30)

puts "[ruby] Starting display..."
client.start_display

puts "[ruby] Health check..."
health = client.health
raise "expected ok, got #{health['status']}" unless health["status"] == "ok"
puts "[ruby] Health: status=#{health['status']} display=#{health['display']}"

puts "[ruby] Adding panel..."
client.add_panel(name: "editor", title: "Code Editor", width: 80)

puts "[ruby] Updating panel..."
client.update_panel("editor", text: "puts 'hello from Ruby'", focus_line: 1)

puts "[ruby] Listing panels..."
panels = client.list_panels
raise "expected 1 panel, got #{panels.size}" unless panels.size == 1
raise "expected editor, got #{panels[0]['name']}" unless panels[0]["name"] == "editor"

puts "[ruby] Starting recording..."
client.start_recording(name: "ruby-e2e-test")

sleep 2

puts "[ruby] Checking recording status..."
status = client.recording_status
raise "expected recording=true" unless status["recording"] == true

puts "[ruby] Stopping recording..."
result = client.stop_recording
raise "expected non-empty path" if result["path"].to_s.empty?
puts "[ruby] Recording saved: #{result['path']} (#{result['elapsed']}s)"

puts "[ruby] Removing panel..."
client.remove_panel("editor")

puts "[ruby] Listing recordings..."
recordings = client.list_recordings
raise "expected >= 1 recording" unless recordings.size >= 1

puts "[ruby] Stopping display..."
client.stop_display

puts "[ruby] Cleanup..."
client.cleanup

puts "[ruby] ALL PASSED"
