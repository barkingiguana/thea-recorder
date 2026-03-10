# frozen_string_literal: true

require "net/http"
require "uri"
require "json"

module Recorder
  VERSION = "0.1.0"

  class Error < StandardError; end

  class Client
    attr_reader :base_url, :timeout

    def initialize(url = nil, timeout: 30)
      @base_url = (url || ENV["RECORDER_URL"] || "http://localhost:9123").chomp("/")
      @timeout = timeout
      @uri = URI.parse(@base_url)
    end

    # Display

    def start_display
      post("/display/start")
    end

    def stop_display
      post("/display/stop")
    end

    # Panels

    def add_panel(name:, title:, width:)
      post("/panels", name: name, title: title, width: width)
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

    def with_panel(name, title:, width:)
      add_panel(name: name, title: title, width: width)
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

    def execute(request)
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
