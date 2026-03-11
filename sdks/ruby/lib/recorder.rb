# frozen_string_literal: true

require "net/http"
require "uri"
require "json"

module Recorder
  VERSION = "0.9.0"

  class Error < StandardError; end

  class Client
    attr_reader :base_url, :timeout

    def initialize(url = nil, timeout: 30)
      @base_url = (url || ENV["THEA_URL"] || "http://localhost:9123").chomp("/")
      @timeout = timeout
      @uri = URI.parse(@base_url)
      @ready = false
    end

    # Display

    def start_display(display_size: nil)
      body = display_size ? { display_size: display_size } : nil
      post("/display/start", body)
    end

    def stop_display
      post("/display/stop")
    end

    # Panels

    def add_panel(name:, title:, width: nil, height: nil)
      body = { name: name, title: title }
      body[:width] = width if width
      body[:height] = height if height
      post("/panels", body)
    end

    def update_panel(name, text:, focus_line: nil)
      body = { text: text }
      body[:focus_line] = focus_line if focus_line
      put("/panels/#{encode(name)}", body)
    end

    def remove_panel(name)
      delete("/panels/#{encode(name)}")
    end

    def list_panels
      get("/panels")
    end

    def with_panel(name, title:, width: nil, height: nil)
      add_panel(name: name, title: title, width: width, height: height)
      yield
    ensure
      remove_panel(name)
    end

    # Recording

    def start_recording(name:)
      post("/recording/start", name: name)
    end

    def stop_recording
      post("/recording/stop")
    end

    def recording_elapsed
      get("/recording/elapsed")
    end

    def recording_status
      get("/recording/status")
    end

    def recording(name)
      start_recording(name: name)
      yield self
    ensure
      stop_recording
    end

    # Recordings

    def list_recordings
      get("/recordings")
    end

    def download_recording(name, path)
      response = raw_get("/recordings/#{encode(name)}")
      File.binwrite(path, response.body)
      path
    end

    def recording_info(name)
      get("/recordings/#{encode(name)}/info")
    end

    # Sessions

    def create_session(name:, display: nil)
      body = { name: name }
      body[:display] = display if display
      post("/sessions", body)
    end

    def use_session(name)
      prefix = name.to_s.empty? ? "" : "/sessions/#{encode(name)}"
      child = self.class.new("#{@base_url}#{prefix}", timeout: @timeout)
      child.instance_variable_set(:@ready, true)
      child
    end

    def delete_session(name)
      delete("/sessions/#{encode(name)}")
    end

    def list_sessions
      get("/sessions")
    end

    # Compositions

    def create_composition(name:, recordings:, layout: "row", labels: true, highlights: [], highlight_color: "00d4aa", highlight_width: 6)
      post("/compositions", name: name, recordings: recordings, layout: layout,
           labels: labels, highlights: highlights, highlight_color: highlight_color,
           highlight_width: highlight_width)
    end

    def add_highlight(composition_name:, recording:, time:, duration: 1.0)
      post("/compositions/#{encode(composition_name)}/highlights",
           recording: recording, time: time, duration: duration)
    end

    def composition_status(name:)
      get("/compositions/#{encode(name)}")
    end

    def list_compositions
      get("/compositions")
    end

    def delete_composition(name:)
      delete("/compositions/#{encode(name)}")
    end

    def wait_for_composition(name:, timeout: 120, interval: 1.0)
      deadline = Time.now + timeout
      last_status = nil

      while Time.now < deadline
        last_status = composition_status(name: name)
        case last_status["status"]
        when "complete"
          return last_status
        when "failed"
          raise Error, "Composition failed: #{last_status["error"]}"
        end
        sleep interval
      end

      raise Error, "Composition not ready after #{timeout}s"
    end

    # Layout / Utility

    def validate_layout
      get("/validate-layout")
    end

    def testcard
      raw_get("/testcard").body
    end

    # Health / Utility

    def health
      get("/health")
    end

    def cleanup
      post("/cleanup")
    end

    def wait_until_ready(timeout: 30)
      deadline = Time.now + timeout
      last_error = nil

      while Time.now < deadline
        begin
          result = health
          return result if result.is_a?(Hash) && result["status"]
        rescue Error => e
          last_error = e
        end
        sleep 0.5
      end

      raise Error, "Server not ready after #{timeout}s: #{last_error&.message}"
    end

    private

    def connection
      http = Net::HTTP.new(@uri.host, @uri.port)
      http.use_ssl = @uri.scheme == "https"
      http.open_timeout = @timeout
      http.read_timeout = @timeout
      http
    end

    def get(path)
      request = Net::HTTP::Get.new(path)
      execute(request)
    end

    def post(path, body = nil)
      request = Net::HTTP::Post.new(path)
      if body
        request["Content-Type"] = "application/json"
        request.body = JSON.generate(body)
      end
      execute(request)
    end

    def put(path, body)
      request = Net::HTTP::Put.new(path)
      request["Content-Type"] = "application/json"
      request.body = JSON.generate(body)
      execute(request)
    end

    def delete(path)
      request = Net::HTTP::Delete.new(path)
      execute(request)
    end

    def raw_get(path)
      ensure_ready(path)
      request = Net::HTTP::Get.new(path)
      response = connection.request(request)
      unless response.is_a?(Net::HTTPSuccess)
        raise Error, "HTTP #{response.code}: #{response.body}"
      end
      response
    rescue Errno::ECONNREFUSED, Errno::ECONNRESET, Errno::EHOSTUNREACH,
           Net::OpenTimeout, Net::ReadTimeout, SocketError => e
      raise Error, "Connection failed: #{e.message}"
    end

    def ensure_ready(path)
      return if @ready || path == "/health"
      wait_until_ready
      @ready = true
    end

    def execute(request)
      ensure_ready(request.path)
      response = connection.request(request)
      unless response.is_a?(Net::HTTPSuccess)
        raise Error, "HTTP #{response.code}: #{response.body}"
      end

      content_type = response["Content-Type"]
      if content_type&.include?("application/json")
        JSON.parse(response.body)
      elsif response.body && !response.body.empty?
        begin
          JSON.parse(response.body)
        rescue JSON::ParserError
          response.body
        end
      else
        true
      end
    rescue Errno::ECONNREFUSED, Errno::ECONNRESET, Errno::EHOSTUNREACH,
           Net::OpenTimeout, Net::ReadTimeout, SocketError => e
      raise Error, "Connection failed: #{e.message}"
    end

    def encode(value)
      URI.encode_www_form_component(value.to_s)
    end
  end
end
