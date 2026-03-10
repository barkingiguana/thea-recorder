# frozen_string_literal: true

require "minitest/autorun"
require "webmock/minitest"
require_relative "../lib/recorder"

class TestRecorderClient < Minitest::Test
  def setup
    @base = "http://localhost:3000"
    @client = Recorder::Client.new(@base)
  end

  # --- Constructor ---

  def test_default_url
    ENV["RECORDER_URL"] = "http://custom:9000"
    client = Recorder::Client.new
    assert_equal "http://custom:9000", client.base_url
  ensure
    ENV.delete("RECORDER_URL")
  end

  def test_explicit_url_overrides_env
    ENV["RECORDER_URL"] = "http://custom:9000"
    client = Recorder::Client.new("http://explicit:4000")
    assert_equal "http://explicit:4000", client.base_url
  ensure
    ENV.delete("RECORDER_URL")
  end

  def test_default_timeout
    assert_equal 30, @client.timeout
  end

  def test_custom_timeout
    client = Recorder::Client.new(@base, timeout: 10)
    assert_equal 10, client.timeout
  end

  # --- Display ---

  def test_start_display
    stub_request(:post, "#{@base}/display/start")
      .to_return(status: 201, body: "")
    @client.start_display
  end

  def test_stop_display
    stub_request(:post, "#{@base}/display/stop")
      .to_return(status: 200, body: "")
    @client.stop_display
  end

  # --- Panels ---

  def test_add_panel
    stub_request(:post, "#{@base}/panels")
      .with(body: { name: "editor", title: "Editor", width: 80 }.to_json)
      .to_return(status: 201, body: "")
    @client.add_panel(name: "editor", title: "Editor", width: 80)
  end

  def test_update_panel
    stub_request(:put, "#{@base}/panels/editor")
      .with(body: { text: "hello", focus_line: 5 }.to_json)
      .to_return(status: 200, body: "")
    @client.update_panel("editor", text: "hello", focus_line: 5)
  end

  def test_update_panel_without_focus_line
    stub_request(:put, "#{@base}/panels/editor")
      .with(body: { text: "hello" }.to_json)
      .to_return(status: 200, body: "")
    @client.update_panel("editor", text: "hello")
  end

  def test_remove_panel
    stub_request(:delete, "#{@base}/panels/editor")
      .to_return(status: 200, body: "")
    @client.remove_panel("editor")
  end

  def test_list_panels
    body = [{ "name" => "editor", "title" => "Editor" }]
    stub_request(:get, "#{@base}/panels")
      .to_return(status: 200, body: body.to_json, headers: { "Content-Type" => "application/json" })
    result = @client.list_panels
    assert_equal "editor", result[0]["name"]
  end

  def test_with_panel_block
    stub_request(:post, "#{@base}/panels")
      .to_return(status: 201, body: "")
    stub_request(:delete, "#{@base}/panels/editor")
      .to_return(status: 200, body: "")

    called = false
    @client.with_panel("editor", title: "Editor", width: 80) do
      called = true
    end

    assert called
    assert_requested :post, "#{@base}/panels"
    assert_requested :delete, "#{@base}/panels/editor"
  end

  def test_with_panel_cleanup_on_exception
    stub_request(:post, "#{@base}/panels")
      .to_return(status: 201, body: "")
    stub_request(:delete, "#{@base}/panels/editor")
      .to_return(status: 200, body: "")

    assert_raises(RuntimeError) do
      @client.with_panel("editor", title: "Editor", width: 80) do
        raise "boom"
      end
    end

    assert_requested :delete, "#{@base}/panels/editor"
  end

  # --- Recording ---

  def test_start_recording
    stub_request(:post, "#{@base}/recording/start")
      .with(body: { name: "demo" }.to_json)
      .to_return(status: 201, body: "")
    @client.start_recording(name: "demo")
  end

  def test_stop_recording
    body = { "path" => "/tmp/demo.mp4", "elapsed" => 10.5, "name" => "demo" }
    stub_request(:post, "#{@base}/recording/stop")
      .to_return(status: 200, body: body.to_json, headers: { "Content-Type" => "application/json" })
    result = @client.stop_recording
    assert_equal "demo", result["name"]
    assert_equal 10.5, result["elapsed"]
  end

  def test_recording_elapsed
    body = { "elapsed" => 5.2 }
    stub_request(:get, "#{@base}/recording/elapsed")
      .to_return(status: 200, body: body.to_json, headers: { "Content-Type" => "application/json" })
    result = @client.recording_elapsed
    assert_equal 5.2, result["elapsed"]
  end

  def test_recording_status
    body = { "recording" => true, "name" => "demo", "elapsed" => 3.1 }
    stub_request(:get, "#{@base}/recording/status")
      .to_return(status: 200, body: body.to_json, headers: { "Content-Type" => "application/json" })
    result = @client.recording_status
    assert result["recording"]
  end

  def test_recording_block
    stub_request(:post, "#{@base}/recording/start")
      .with(body: { name: "demo" }.to_json)
      .to_return(status: 201, body: "")
    stub_request(:post, "#{@base}/recording/stop")
      .to_return(status: 200, body: { "name" => "demo" }.to_json,
                 headers: { "Content-Type" => "application/json" })

    called = false
    @client.recording("demo") do |r|
      called = true
      assert_equal @client, r
    end

    assert called
    assert_requested :post, "#{@base}/recording/start"
    assert_requested :post, "#{@base}/recording/stop"
  end

  def test_recording_block_cleanup_on_exception
    stub_request(:post, "#{@base}/recording/start")
      .to_return(status: 201, body: "")
    stub_request(:post, "#{@base}/recording/stop")
      .to_return(status: 200, body: "")

    assert_raises(RuntimeError) do
      @client.recording("demo") { raise "boom" }
    end

    assert_requested :post, "#{@base}/recording/stop"
  end

  # --- Recordings ---

  def test_list_recordings
    body = [{ "name" => "demo", "path" => "/tmp/demo.mp4", "size" => 1024, "created" => "2026-01-01" }]
    stub_request(:get, "#{@base}/recordings")
      .to_return(status: 200, body: body.to_json, headers: { "Content-Type" => "application/json" })
    result = @client.list_recordings
    assert_equal 1, result.length
    assert_equal "demo", result[0]["name"]
  end

  def test_download_recording
    video_bytes = "\x00\x00\x00\x1Cftypisom".b
    stub_request(:get, "#{@base}/recordings/demo")
      .to_return(status: 200, body: video_bytes,
                 headers: { "Content-Type" => "video/mp4" })

    Dir.mktmpdir do |dir|
      path = File.join(dir, "demo.mp4")
      result = @client.download_recording("demo", path)
      assert_equal path, result
      assert_equal video_bytes, File.binread(path)
    end
  end

  def test_recording_info
    body = { "name" => "demo", "path" => "/tmp/demo.mp4", "size" => 1024, "created" => "2026-01-01" }
    stub_request(:get, "#{@base}/recordings/demo/info")
      .to_return(status: 200, body: body.to_json, headers: { "Content-Type" => "application/json" })
    result = @client.recording_info("demo")
    assert_equal "demo", result["name"]
  end

  # --- Health / Utility ---

  def test_health
    body = { "status" => "ok", "recording" => false, "display" => true, "panels" => 0, "uptime" => 120 }
    stub_request(:get, "#{@base}/health")
      .to_return(status: 200, body: body.to_json, headers: { "Content-Type" => "application/json" })
    result = @client.health
    assert_equal "ok", result["status"]
  end

  def test_cleanup
    stub_request(:post, "#{@base}/cleanup")
      .to_return(status: 200, body: "")
    @client.cleanup
  end

  def test_wait_until_ready
    body = { "status" => "ok" }
    stub_request(:get, "#{@base}/health")
      .to_return(status: 200, body: body.to_json, headers: { "Content-Type" => "application/json" })
    result = @client.wait_until_ready(timeout: 5)
    assert_equal "ok", result["status"]
  end

  def test_wait_until_ready_timeout
    stub_request(:get, "#{@base}/health")
      .to_return(status: 503, body: "unavailable")

    error = assert_raises(Recorder::Error) do
      @client.wait_until_ready(timeout: 1)
    end
    assert_match(/not ready/i, error.message)
  end

  # --- Error handling ---

  def test_http_error_raises_recorder_error
    stub_request(:get, "#{@base}/health")
      .to_return(status: 500, body: "Internal Server Error")

    error = assert_raises(Recorder::Error) do
      @client.health
    end
    assert_match(/500/, error.message)
  end

  def test_404_raises_recorder_error
    stub_request(:get, "#{@base}/recordings/missing/info")
      .to_return(status: 404, body: "not found")

    assert_raises(Recorder::Error) do
      @client.recording_info("missing")
    end
  end

  def test_connection_refused
    stub_request(:get, "#{@base}/health")
      .to_raise(Errno::ECONNREFUSED)

    error = assert_raises(Recorder::Error) do
      @client.health
    end
    assert_match(/Connection failed/, error.message)
  end

  def test_timeout_raises_recorder_error
    stub_request(:get, "#{@base}/health")
      .to_raise(Net::OpenTimeout)

    error = assert_raises(Recorder::Error) do
      @client.health
    end
    assert_match(/Connection failed/, error.message)
  end

  def test_error_is_standard_error
    assert Recorder::Error < StandardError
  end
end
