package com.recorder;

import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * Java client for the thea-recorder HTTP server.
 *
 * <p>Uses {@link java.net.http.HttpClient} (Java 11+) with zero external dependencies.
 * All data types use Java records.
 *
 * <p>Example usage:
 * <pre>{@code
 * try (var client = new RecorderClient("http://localhost:9123")) {
 *     client.startDisplay();
 *     client.recording("my-test", c -> {
 *         // perform actions while recording
 *     });
 *     client.stopDisplay();
 * }
 * }</pre>
 */
public class RecorderClient implements AutoCloseable {

    private final String baseUrl;
    private final HttpClient httpClient;
    private final Duration timeout;
    private volatile boolean ready;

    /**
     * Creates a client using the THEA_URL environment variable.
     *
     * @throws RecorderError if THEA_URL is not set
     */
    public RecorderClient() {
        this(envUrl(), Duration.ofSeconds(30));
    }

    /**
     * Creates a client for the given server URL with default 30s timeout.
     *
     * @param url the base URL of the recorder server
     */
    public RecorderClient(String url) {
        this(url, Duration.ofSeconds(30));
    }

    /**
     * Creates a client for the given server URL with a custom timeout.
     *
     * @param url     the base URL of the recorder server
     * @param timeout request timeout
     */
    public RecorderClient(String url, Duration timeout) {
        this.baseUrl = url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
        this.timeout = timeout;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(timeout)
                .build();
    }

    // ── Display ──────────────────────────────────────────────────────────

    /** Starts the virtual display with the server's default resolution. */
    public void startDisplay() {
        post("/display/start", "", 201);
    }

    /**
     * Starts the virtual display with a custom resolution.
     *
     * @param displaySize resolution override (e.g. "1920x1080")
     */
    public void startDisplay(String displaySize) {
        var body = jsonObject(Map.of("display_size", jsonString(displaySize)));
        post("/display/start", body, 201);
    }

    /** Stops the virtual display. */
    public void stopDisplay() {
        post("/display/stop", "", 200);
    }

    /**
     * Captures a JPEG screenshot of the live display.
     *
     * @param quality JPEG quality (1-100)
     * @return JPEG image data
     */
    public byte[] displayScreenshot(int quality) {
        return getRaw("/display/screenshot?quality=" + quality, 200);
    }

    /**
     * Returns the URL for the live MJPEG stream.
     *
     * @param fps frames per second for the stream (1-15)
     * @return full URL to the MJPEG stream endpoint
     */
    public String displayStreamUrl(int fps) {
        return baseUrl + "/display/stream?fps=" + fps;
    }

    /**
     * Returns the URL for the HTML live viewer page.
     *
     * @return full URL to the viewer page
     */
    public String displayViewerUrl() {
        return baseUrl + "/display/view";
    }

    // ── Panels ───────────────────────────────────────────────────────────

    /**
     * Adds a new panel.
     *
     * @param name  panel identifier
     * @param title panel title
     * @param width panel width in characters
     * @return list of warnings from the server (may be empty)
     */
    public List<String> addPanel(String name, String title, int width) {
        return addPanel(name, title, width, null);
    }

    /**
     * Adds a new panel with optional height.
     *
     * @param name   panel identifier
     * @param title  panel title
     * @param width  panel width in characters
     * @param height panel height in lines (null to omit)
     * @return list of warnings from the server (may be empty)
     */
    public List<String> addPanel(String name, String title, Integer width, Integer height) {
        var fields = new LinkedHashMap<String, String>();
        fields.put("name", jsonString(name));
        fields.put("title", jsonString(title));
        if (width != null) {
            fields.put("width", String.valueOf(width));
        }
        if (height != null) {
            fields.put("height", String.valueOf(height));
        }
        var json = post("/panels", jsonObject(fields), 201);
        return parseWarnings(json);
    }

    /**
     * Updates an existing panel's content.
     *
     * @param name      panel identifier
     * @param text      new text content
     * @param focusLine line number to focus on
     */
    public void updatePanel(String name, String text, int focusLine) {
        var body = jsonObject(Map.of(
                "text", jsonString(text),
                "focus_line", String.valueOf(focusLine)
        ));
        put("/panels/" + encode(name), body, 200);
    }

    /**
     * Removes a panel.
     *
     * @param name panel identifier
     */
    public void removePanel(String name) {
        delete("/panels/" + encode(name), 200);
    }

    /**
     * Lists all active panels.
     *
     * @return list of panels
     */
    public List<Panel> listPanels() {
        var json = get("/panels", 200);
        return parsePanelList(json);
    }

    /**
     * Scoped panel helper. Adds a panel, runs the action, then removes the panel.
     *
     * @param name   panel identifier
     * @param title  panel title
     * @param width  panel width in characters
     * @param action action to run while the panel is active
     */
    public void withPanel(String name, String title, int width, Runnable action) {
        addPanel(name, title, width);
        try {
            action.run();
        } finally {
            removePanel(name);
        }
    }

    // ── Recording ────────────────────────────────────────────────────────

    /**
     * Starts a recording.
     *
     * @param name recording name
     * @return list of warnings from the server (may be empty)
     */
    public List<String> startRecording(String name) {
        var body = jsonObject(Map.of("name", jsonString(name)));
        var json = post("/recording/start", body, 201);
        return parseWarnings(json);
    }

    /**
     * Stops the current recording.
     *
     * @return the recording result
     */
    public RecordingResult stopRecording() {
        var json = post("/recording/stop", "", 200);
        return parseRecordingResult(json);
    }

    /**
     * Stops the current recording with GIF generation options.
     *
     * @param gif      whether to generate a GIF
     * @param gifFps   frames per second for the GIF
     * @param gifWidth width in pixels for the GIF
     * @return the recording result
     */
    public RecordingResult stopRecording(boolean gif, int gifFps, int gifWidth) {
        if (!gif) {
            return stopRecording();
        }
        var fields = new LinkedHashMap<String, String>();
        fields.put("gif", "true");
        fields.put("gif_fps", String.valueOf(gifFps));
        fields.put("gif_width", String.valueOf(gifWidth));
        var json = post("/recording/stop", jsonObject(fields), 200);
        return parseRecordingResult(json);
    }

    /**
     * Stops the current recording with specific output formats.
     *
     * @param outputFormats list of desired output formats (e.g. "mp4", "gif", "webm")
     * @return the recording result
     */
    public RecordingResult stopRecording(List<String> outputFormats) {
        if (outputFormats == null || outputFormats.isEmpty()) {
            return stopRecording();
        }
        var fields = new LinkedHashMap<String, String>();
        fields.put("output_formats", jsonStringArray(outputFormats));
        var json = post("/recording/stop", jsonObject(fields), 200);
        return parseRecordingResult(json);
    }

    /**
     * Gets the elapsed time of the current recording.
     *
     * @return elapsed seconds
     */
    public double recordingElapsed() {
        var json = get("/recording/elapsed", 200);
        return parseDouble(jsonValue(json, "elapsed"));
    }

    /**
     * Gets the current recording status.
     *
     * @return recording status
     */
    public RecordingStatus recordingStatus() {
        var json = get("/recording/status", 200);
        return parseRecordingStatus(json);
    }

    /**
     * Scoped recording helper. Starts a recording, runs the action, then stops.
     *
     * @param name   recording name
     * @param action action to run while recording
     * @return the recording result
     */
    public RecordingResult recording(String name, Consumer<RecorderClient> action) {
        startRecording(name);
        try {
            action.accept(this);
        } catch (Exception e) {
            try {
                stopRecording();
            } catch (Exception suppressed) {
                e.addSuppressed(suppressed);
            }
            throw e;
        }
        return stopRecording();
    }

    /**
     * Scoped recording helper with GIF generation options.
     *
     * @param name     recording name
     * @param action   action to run while recording
     * @param gif      whether to generate a GIF
     * @param gifFps   frames per second for the GIF
     * @param gifWidth width in pixels for the GIF
     * @return the recording result
     */
    public RecordingResult recording(String name, Consumer<RecorderClient> action,
                                     boolean gif, int gifFps, int gifWidth) {
        startRecording(name);
        try {
            action.accept(this);
        } catch (Exception e) {
            try {
                stopRecording();
            } catch (Exception suppressed) {
                e.addSuppressed(suppressed);
            }
            throw e;
        }
        return stopRecording(gif, gifFps, gifWidth);
    }

    /**
     * Scoped recording helper with specific output formats.
     *
     * @param name          recording name
     * @param action        action to run while recording
     * @param outputFormats list of desired output formats (e.g. "mp4", "gif", "webm")
     * @return the recording result
     */
    public RecordingResult recording(String name, Consumer<RecorderClient> action,
                                     List<String> outputFormats) {
        startRecording(name);
        try {
            action.accept(this);
        } catch (Exception e) {
            try {
                stopRecording();
            } catch (Exception suppressed) {
                e.addSuppressed(suppressed);
            }
            throw e;
        }
        return stopRecording(outputFormats);
    }

    // ── Annotations ─────────────────────────────────────────────────────

    /**
     * Adds an annotation to the active recording.
     *
     * @param label   short label for the annotation
     * @param time    time offset in seconds (null to use current elapsed time)
     * @param details optional longer description (null to omit)
     * @return the created annotation as a map
     */
    public Map<String, Object> addAnnotation(String label, Double time, String details) {
        var fields = new LinkedHashMap<String, String>();
        fields.put("label", jsonString(label));
        if (time != null) {
            fields.put("time", String.valueOf(time));
        }
        if (details != null) {
            fields.put("details", jsonString(details));
        }
        var json = post("/recording/annotations", jsonObject(fields), 201);
        return parseJsonObject(json);
    }

    /**
     * Lists annotations for the active recording.
     *
     * @return list of annotation maps
     */
    public List<Map<String, Object>> listAnnotations() {
        var json = get("/recording/annotations", 200);
        return parseJsonArray(json);
    }

    // ── Recordings ───────────────────────────────────────────────────────

    /**
     * Lists all stored recordings.
     *
     * @return list of recording info
     */
    public List<RecordingInfo> listRecordings() {
        var json = get("/recordings", 200);
        return parseRecordingInfoList(json);
    }

    /**
     * Downloads a recording to a file.
     *
     * @param name recording name
     * @param dest destination path
     */
    public void downloadRecording(String name, Path dest) {
        ensureReady("/recordings/" + encode(name));
        var request = newRequest("/recordings/" + encode(name))
                .GET()
                .build();
        try {
            var response = httpClient.send(request, HttpResponse.BodyHandlers.ofFile(dest));
            if (response.statusCode() != 200) {
                throw new RecorderError(response.statusCode(),
                        "Download failed: HTTP " + response.statusCode());
            }
        } catch (RecorderError e) {
            throw e;
        } catch (IOException | InterruptedException e) {
            throw new RecorderError("Download failed", e);
        }
    }

    /**
     * Downloads a recording to an output stream.
     *
     * @param name recording name
     * @param out  output stream to write to
     */
    public void downloadRecording(String name, OutputStream out) {
        ensureReady("/recordings/" + encode(name));
        var request = newRequest("/recordings/" + encode(name))
                .GET()
                .build();
        try {
            var response = httpClient.send(request, HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() != 200) {
                throw new RecorderError(response.statusCode(),
                        "Download failed: HTTP " + response.statusCode());
            }
            try (var in = response.body()) {
                in.transferTo(out);
            }
        } catch (RecorderError e) {
            throw e;
        } catch (IOException | InterruptedException e) {
            throw new RecorderError("Download failed", e);
        }
    }

    /**
     * Gets info about a specific recording.
     *
     * @param name recording name
     * @return recording info
     */
    public RecordingInfo recordingInfo(String name) {
        var json = get("/recordings/" + encode(name) + "/info", 200);
        return parseRecordingInfo(json);
    }

    /**
     * Converts a recording to GIF format.
     *
     * @param name  recording name
     * @param fps   frames per second for the GIF
     * @param width width in pixels for the GIF
     * @return conversion result as a map
     */
    public Map<String, Object> convertToGif(String name, int fps, int width) {
        var fields = new LinkedHashMap<String, String>();
        fields.put("fps", String.valueOf(fps));
        fields.put("width", String.valueOf(width));
        var json = post("/recordings/" + encode(name) + "/gif", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Downloads a recording in a specific format.
     *
     * @param name        recording name
     * @param destination destination path
     * @param format      output format (e.g. "mp4", "gif", "webm")
     */
    public void downloadRecording(String name, Path destination, String format) {
        String query = "mp4".equals(format) ? "" : "?format=" + encode(format);
        String path = "/recordings/" + encode(name) + query;
        ensureReady(path);
        var request = newRequest(path)
                .GET()
                .build();
        try {
            var response = httpClient.send(request, HttpResponse.BodyHandlers.ofFile(destination));
            if (response.statusCode() != 200) {
                throw new RecorderError(response.statusCode(),
                        "Download failed: HTTP " + response.statusCode());
            }
        } catch (RecorderError e) {
            throw e;
        } catch (IOException | InterruptedException e) {
            throw new RecorderError("Download failed", e);
        }
    }

    /**
     * Extracts a JPEG frame from a saved recording.
     *
     * @param name       recording name
     * @param timeOffset time offset in seconds into the video
     * @param quality    JPEG quality (1-100)
     * @return JPEG image data
     */
    public byte[] recordingScreenshot(String name, double timeOffset, int quality) {
        var params = "?t=" + String.format("%.3f", timeOffset) + "&quality=" + quality;
        return getRaw("/recordings/" + encode(name) + "/screenshot" + params, 200);
    }

    // ── Events ──────────────────────────────────────────────────────────

    /**
     * Returns the event log for the current session.
     *
     * @param since only return events with elapsed greater than this value (null for all)
     * @return list of event maps
     */
    public List<Map<String, Object>> events(Double since) {
        var path = "/events";
        if (since != null) {
            path = "/events?since=" + since;
        }
        var json = get(path, 200);
        return parseJsonArray(json);
    }

    /**
     * Returns the URL for the HTML dashboard page.
     *
     * @return full URL to the dashboard
     */
    public String dashboardUrl() {
        return baseUrl + "/dashboard";
    }

    // ── Sessions ─────────────────────────────────────────────────────────

    /**
     * Creates a new named recording session.
     *
     * @param name    session name
     * @param display optional explicit X11 display number (-1 to auto-allocate)
     * @return raw JSON response
     */
    public String createSession(String name, int display) {
        var fields = new LinkedHashMap<String, String>();
        fields.put("name", jsonString(name));
        if (display >= 0) {
            fields.put("display", String.valueOf(display));
        }
        return post("/sessions", jsonObject(fields), 201);
    }

    /** Creates a new named session with auto-allocated display. */
    public String createSession(String name) {
        return createSession(name, -1);
    }

    /**
     * Returns a new client scoped to the named session.
     *
     * @param name session name (empty string for the default session)
     * @return a session-scoped client
     */
    public RecorderClient useSession(String name) {
        var prefix = (name == null || name.isEmpty()) ? "" : "/sessions/" + encode(name);
        var child = new RecorderClient(baseUrl + prefix, timeout);
        child.ready = true;
        return child;
    }

    /**
     * Deletes a named session.
     *
     * @param name session name
     */
    public void deleteSession(String name) {
        delete("/sessions/" + encode(name), 200);
    }

    /**
     * Lists all sessions.
     *
     * @return raw JSON array
     */
    public String listSessions() {
        return get("/sessions", 200);
    }

    // ── Compositions ────────────────────────────────────────────────────

    /**
     * Creates a composition with default settings (row layout, labels on,
     * no highlights, color "00d4aa", width 6).
     *
     * @param name       composition name
     * @param recordings list of recording names to compose
     * @return composition status
     */
    public CompositionStatus createComposition(String name, List<String> recordings) {
        return createComposition(name, recordings, "row", true, List.of(), "00d4aa", 6);
    }

    /**
     * Creates a composition with full options.
     *
     * @param name           composition name
     * @param recordings     list of recording names to compose
     * @param layout         layout type (e.g. "row", "column", "grid")
     * @param labels         whether to show recording labels
     * @param highlights     list of highlights to apply
     * @param highlightColor highlight border color (hex without #)
     * @param highlightWidth highlight border width in pixels
     * @return composition status
     */
    public CompositionStatus createComposition(String name, List<String> recordings,
                                                String layout, boolean labels,
                                                List<CompositionHighlight> highlights,
                                                String highlightColor, int highlightWidth) {
        var recArray = new StringBuilder("[");
        for (int i = 0; i < recordings.size(); i++) {
            if (i > 0) recArray.append(",");
            recArray.append(jsonString(recordings.get(i)));
        }
        recArray.append("]");

        var hlArray = new StringBuilder("[");
        for (int i = 0; i < highlights.size(); i++) {
            if (i > 0) hlArray.append(",");
            var h = highlights.get(i);
            hlArray.append(jsonObject(new LinkedHashMap<>(Map.of(
                    "recording", jsonString(h.recording()),
                    "time", String.valueOf(h.time()),
                    "duration", String.valueOf(h.duration())
            ))));
        }
        hlArray.append("]");

        var body = jsonObject(new LinkedHashMap<>(Map.of(
                "name", jsonString(name),
                "recordings", recArray.toString(),
                "layout", jsonString(layout),
                "labels", String.valueOf(labels),
                "highlights", hlArray.toString(),
                "highlight_color", jsonString(highlightColor),
                "highlight_width", String.valueOf(highlightWidth)
        )));
        var json = post("/compositions", body, 201);
        return parseCompositionStatus(json);
    }

    /**
     * Gets the status of a composition.
     *
     * @param name composition name
     * @return composition status
     */
    public CompositionStatus compositionStatus(String name) {
        var json = get("/compositions/" + encode(name), 200);
        return parseCompositionStatus(json);
    }

    /**
     * Lists all compositions.
     *
     * @return raw JSON response
     */
    public String listCompositions() {
        return get("/compositions", 200);
    }

    /**
     * Deletes a composition.
     *
     * @param name composition name
     */
    public void deleteComposition(String name) {
        delete("/compositions/" + encode(name), 200);
    }

    /**
     * Adds a highlight to a composition.
     *
     * @param compositionName composition name
     * @param recording       recording name to highlight
     * @param time            start time in seconds
     * @param duration        duration in seconds
     */
    public void addHighlight(String compositionName, String recording, double time, double duration) {
        var body = jsonObject(new LinkedHashMap<>(Map.of(
                "recording", jsonString(recording),
                "time", String.valueOf(time),
                "duration", String.valueOf(duration)
        )));
        post("/compositions/" + encode(compositionName) + "/highlights", body, 201);
    }

    /**
     * Polls composition status until complete or failed.
     *
     * @param name      composition name
     * @param timeoutMs maximum time to wait in milliseconds
     * @return the final composition status
     * @throws RecorderError if the composition fails or the timeout expires
     */
    public CompositionStatus waitForComposition(String name, long timeoutMs) {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            var status = compositionStatus(name);
            if ("complete".equals(status.status())) {
                return status;
            }
            if ("failed".equals(status.status())) {
                throw new RecorderError("Composition failed: " + status.error());
            }
            try {
                Thread.sleep(250);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new RecorderError("Interrupted while waiting for composition", e);
            }
        }
        throw new RecorderError("Composition not ready after " + timeoutMs + "ms");
    }

    // ── Director — Mouse ──────────────────────────────────────────────

    /**
     * Moves the mouse cursor.
     *
     * @param x           target X coordinate
     * @param y           target Y coordinate
     * @param duration    movement duration in seconds (null for default)
     * @param targetWidth target width for Fitts's Law (null for default)
     * @return response map
     */
    public Map<String, Object> mouseMove(int x, int y, Double duration, Double targetWidth) {
        var fields = new LinkedHashMap<String, String>();
        fields.put("x", String.valueOf(x));
        fields.put("y", String.valueOf(y));
        if (duration != null) {
            fields.put("duration", String.valueOf(duration));
        }
        if (targetWidth != null) {
            fields.put("target_width", String.valueOf(targetWidth));
        }
        var json = post("/director/mouse/move", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Clicks the mouse.
     *
     * @param x        X coordinate (null to click at current position)
     * @param y        Y coordinate (null to click at current position)
     * @param button   mouse button (1=left, 2=middle, 3=right)
     * @param duration movement duration in seconds (null for default)
     * @return response map
     */
    public Map<String, Object> mouseClick(Integer x, Integer y, int button, Double duration) {
        var fields = new LinkedHashMap<String, String>();
        if (x != null) {
            fields.put("x", String.valueOf(x));
        }
        if (y != null) {
            fields.put("y", String.valueOf(y));
        }
        fields.put("button", String.valueOf(button));
        if (duration != null) {
            fields.put("duration", String.valueOf(duration));
        }
        var json = post("/director/mouse/click", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Double-clicks the mouse.
     *
     * @param x X coordinate (null to click at current position)
     * @param y Y coordinate (null to click at current position)
     * @return response map
     */
    public Map<String, Object> mouseDoubleClick(Integer x, Integer y) {
        var fields = new LinkedHashMap<String, String>();
        if (x != null) {
            fields.put("x", String.valueOf(x));
        }
        if (y != null) {
            fields.put("y", String.valueOf(y));
        }
        var json = post("/director/mouse/double-click", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Right-clicks the mouse.
     *
     * @param x X coordinate (null to click at current position)
     * @param y Y coordinate (null to click at current position)
     * @return response map
     */
    public Map<String, Object> mouseRightClick(Integer x, Integer y) {
        var fields = new LinkedHashMap<String, String>();
        if (x != null) {
            fields.put("x", String.valueOf(x));
        }
        if (y != null) {
            fields.put("y", String.valueOf(y));
        }
        var json = post("/director/mouse/right-click", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Drags from one point to another.
     *
     * @param startX   start X coordinate
     * @param startY   start Y coordinate
     * @param endX     end X coordinate
     * @param endY     end Y coordinate
     * @param button   mouse button (1=left, 2=middle, 3=right)
     * @param duration movement duration in seconds (null for default)
     * @return response map
     */
    public Map<String, Object> mouseDrag(int startX, int startY, int endX, int endY, int button, Double duration) {
        var fields = new LinkedHashMap<String, String>();
        fields.put("start_x", String.valueOf(startX));
        fields.put("start_y", String.valueOf(startY));
        fields.put("end_x", String.valueOf(endX));
        fields.put("end_y", String.valueOf(endY));
        fields.put("button", String.valueOf(button));
        if (duration != null) {
            fields.put("duration", String.valueOf(duration));
        }
        var json = post("/director/mouse/drag", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Scrolls the mouse wheel.
     *
     * @param clicks number of scroll clicks (positive=up, negative=down)
     * @param x      X coordinate (null for current position)
     * @param y      Y coordinate (null for current position)
     * @return response map
     */
    public Map<String, Object> mouseScroll(int clicks, Integer x, Integer y) {
        var fields = new LinkedHashMap<String, String>();
        fields.put("clicks", String.valueOf(clicks));
        if (x != null) {
            fields.put("x", String.valueOf(x));
        }
        if (y != null) {
            fields.put("y", String.valueOf(y));
        }
        var json = post("/director/mouse/scroll", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Gets the current mouse cursor position.
     *
     * @return map with "x" and "y" keys
     */
    public Map<String, Object> mousePosition() {
        var json = get("/director/mouse/position", 200);
        return parseJsonObject(json);
    }

    // ── Director — Keyboard ────────────────────────────────────────────

    /**
     * Types text with human-like rhythm.
     *
     * @param text text to type
     * @param wpm  words per minute (null for default)
     * @return response map
     */
    public Map<String, Object> keyboardType(String text, Double wpm) {
        var fields = new LinkedHashMap<String, String>();
        fields.put("text", jsonString(text));
        if (wpm != null) {
            fields.put("wpm", String.valueOf(wpm));
        }
        var json = post("/director/keyboard/type", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Presses one or more keys.
     *
     * @param keys key names to press
     * @return response map
     */
    public Map<String, Object> keyboardPress(String... keys) {
        var keysArray = new StringBuilder("[");
        for (int i = 0; i < keys.length; i++) {
            if (i > 0) keysArray.append(",");
            keysArray.append(jsonString(keys[i]));
        }
        keysArray.append("]");
        var body = "{\"keys\":" + keysArray + "}";
        var json = post("/director/keyboard/press", body, 200);
        return parseJsonObject(json);
    }

    /**
     * Holds a key down.
     *
     * @param key key name to hold
     * @return response map
     */
    public Map<String, Object> keyboardHold(String key) {
        var body = jsonObject(Map.of("key", jsonString(key)));
        var json = post("/director/keyboard/hold", body, 200);
        return parseJsonObject(json);
    }

    /**
     * Releases a held key.
     *
     * @param key key name to release
     * @return response map
     */
    public Map<String, Object> keyboardRelease(String key) {
        var body = jsonObject(Map.of("key", jsonString(key)));
        var json = post("/director/keyboard/release", body, 200);
        return parseJsonObject(json);
    }

    // ── Director — Window ──────────────────────────────────────────────

    /**
     * Finds a window by name or WM_CLASS.
     *
     * @param name      window name (null to search by class only)
     * @param className WM_CLASS (null to search by name only)
     * @param timeout   search timeout in seconds
     * @return map with "window_id" key
     */
    public Map<String, Object> windowFind(String name, String className, double timeout) {
        var fields = new LinkedHashMap<String, String>();
        if (name != null) {
            fields.put("name", jsonString(name));
        }
        if (className != null) {
            fields.put("class", jsonString(className));
        }
        fields.put("timeout", String.valueOf(timeout));
        var json = post("/director/window/find", jsonObject(fields), 200);
        return parseJsonObject(json);
    }

    /**
     * Focuses a window.
     *
     * @param windowId X11 window ID
     * @return response map
     */
    public Map<String, Object> windowFocus(String windowId) {
        var json = post("/director/window/" + encode(windowId) + "/focus", "", 200);
        return parseJsonObject(json);
    }

    /**
     * Moves a window.
     *
     * @param windowId X11 window ID
     * @param x        target X coordinate
     * @param y        target Y coordinate
     * @return response map
     */
    public Map<String, Object> windowMove(String windowId, int x, int y) {
        var body = jsonObject(new LinkedHashMap<>(Map.of(
                "x", String.valueOf(x),
                "y", String.valueOf(y)
        )));
        var json = post("/director/window/" + encode(windowId) + "/move", body, 200);
        return parseJsonObject(json);
    }

    /**
     * Resizes a window.
     *
     * @param windowId X11 window ID
     * @param width    target width
     * @param height   target height
     * @return response map
     */
    public Map<String, Object> windowResize(String windowId, int width, int height) {
        var body = jsonObject(new LinkedHashMap<>(Map.of(
                "width", String.valueOf(width),
                "height", String.valueOf(height)
        )));
        var json = post("/director/window/" + encode(windowId) + "/resize", body, 200);
        return parseJsonObject(json);
    }

    /**
     * Minimizes a window.
     *
     * @param windowId X11 window ID
     * @return response map
     */
    public Map<String, Object> windowMinimize(String windowId) {
        var json = post("/director/window/" + encode(windowId) + "/minimize", "", 200);
        return parseJsonObject(json);
    }

    /**
     * Gets window geometry.
     *
     * @param windowId X11 window ID
     * @return map with "x", "y", "width", "height" keys
     */
    public Map<String, Object> windowGeometry(String windowId) {
        var json = get("/director/window/" + encode(windowId) + "/geometry", 200);
        return parseJsonObject(json);
    }

    /**
     * Tiles windows in a layout.
     *
     * @param windowIds list of X11 window IDs
     * @param layout    layout type (e.g. "side-by-side")
     * @param bounds    optional bounding box [x, y, width, height] (null for display size)
     * @return response map
     */
    public Map<String, Object> windowTile(List<String> windowIds, String layout, int[] bounds) {
        var idsArray = new StringBuilder("[");
        for (int i = 0; i < windowIds.size(); i++) {
            if (i > 0) idsArray.append(",");
            idsArray.append(jsonString(windowIds.get(i)));
        }
        idsArray.append("]");
        var body = new StringBuilder("{\"window_ids\":").append(idsArray)
                .append(",\"layout\":").append(jsonString(layout));
        if (bounds != null) {
            body.append(",\"bounds\":[")
                    .append(bounds[0]).append(",")
                    .append(bounds[1]).append(",")
                    .append(bounds[2]).append(",")
                    .append(bounds[3]).append("]");
        }
        body.append("}");
        var json = post("/director/window/tile", body.toString(), 200);
        return parseJsonObject(json);
    }

    // ── Layout & Diagnostics ────────────────────────────────────────────

    /**
     * Validates the current panel layout.
     *
     * @return validation result with warnings and validity flag
     */
    public ValidationResult validateLayout() {
        var json = get("/validate-layout", 200);
        return new ValidationResult(
                parseBool(jsonValue(json, "valid")),
                parseWarnings(json)
        );
    }

    /**
     * Gets a test card SVG for the current display configuration.
     *
     * @return SVG content as a string
     */
    public String testcard() {
        var request = newRequest("/testcard")
                .header("Accept", "image/svg+xml")
                .GET()
                .build();
        return send(request, 200);
    }

    // ── Health & Cleanup ─────────────────────────────────────────────────

    /**
     * Gets server health status.
     *
     * @return health status
     */
    public Health health() {
        var json = get("/health", 200);
        return parseHealth(json);
    }

    /**
     * Cleans up server resources.
     */
    public void cleanup() {
        post("/cleanup", "", 200);
    }

    /**
     * Polls the /health endpoint until the server is ready or the timeout expires.
     *
     * @param timeout maximum time to wait
     * @throws RecorderError if the timeout expires before the server is ready
     */
    public void waitUntilReady(Duration timeout) {
        long deadline = System.currentTimeMillis() + timeout.toMillis();
        while (System.currentTimeMillis() < deadline) {
            try {
                health();
                return;
            } catch (RecorderError e) {
                // not ready yet
            }
            try {
                Thread.sleep(250);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new RecorderError("Interrupted while waiting for server", e);
            }
        }
        throw new RecorderError("Server not ready after " + timeout);
    }

    /**
     * Calls {@link #cleanup()} when used with try-with-resources.
     */
    @Override
    public void close() {
        cleanup();
    }

    // ── Internal HTTP helpers ────────────────────────────────────────────

    private HttpRequest.Builder newRequest(String path) {
        return HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .timeout(timeout)
                .header("Content-Type", "application/json");
    }

    private String get(String path, int expectedStatus) {
        var request = newRequest(path).GET().build();
        return send(request, expectedStatus);
    }

    private String post(String path, String body, int expectedStatus) {
        var request = newRequest(path)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        return send(request, expectedStatus);
    }

    private void put(String path, String body, int expectedStatus) {
        var request = newRequest(path)
                .PUT(HttpRequest.BodyPublishers.ofString(body))
                .build();
        send(request, expectedStatus);
    }

    private void delete(String path, int expectedStatus) {
        var request = newRequest(path).DELETE().build();
        send(request, expectedStatus);
    }

    private byte[] getRaw(String path, int expectedStatus) {
        ensureReady(path);
        var request = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .timeout(timeout)
                .GET()
                .build();
        try {
            var response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() != expectedStatus) {
                throw new RecorderError(response.statusCode(),
                        "HTTP %d from GET %s".formatted(response.statusCode(), path));
            }
            return response.body();
        } catch (RecorderError e) {
            throw e;
        } catch (IOException | InterruptedException e) {
            throw new RecorderError("Request failed: GET " + path, e);
        }
    }

    private synchronized void ensureReady(String path) {
        if (ready || path.equals("/health")) return;
        waitUntilReady(Duration.ofSeconds(30));
        ready = true;
    }

    private String send(HttpRequest request, int expectedStatus) {
        ensureReady(request.uri().getPath());
        try {
            var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != expectedStatus) {
                throw new RecorderError(response.statusCode(),
                        "HTTP %d from %s %s: %s".formatted(
                                response.statusCode(),
                                request.method(),
                                request.uri().getPath(),
                                response.body()));
            }
            return response.body();
        } catch (RecorderError e) {
            throw e;
        } catch (IOException | InterruptedException e) {
            throw new RecorderError("Request failed: " + request.method() + " " + request.uri(), e);
        }
    }

    private static String encode(String value) {
        return java.net.URLEncoder.encode(value, java.nio.charset.StandardCharsets.UTF_8);
    }

    private static String envUrl() {
        var url = System.getenv("THEA_URL");
        if (url == null || url.isBlank()) {
            return "http://localhost:9123";
        }
        return url;
    }

    // ── Minimal JSON helpers ─────────────────────────────────────────────
    // These are intentionally simple — this is a thin client that only needs
    // to build and parse small flat JSON objects and arrays thereof.

    static String jsonString(String value) {
        if (value == null) return "null";
        return "\"" + value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
                + "\"";
    }

    static String jsonObject(Map<String, String> fields) {
        var sb = new StringBuilder("{");
        var first = true;
        for (var entry : fields.entrySet()) {
            if (!first) sb.append(",");
            sb.append("\"").append(entry.getKey()).append("\":").append(entry.getValue());
            first = false;
        }
        sb.append("}");
        return sb.toString();
    }

    /**
     * Extracts a value for a given key from a flat JSON object string.
     * Returns the raw value (with quotes for strings, without for numbers/booleans).
     */
    static String jsonValue(String json, String key) {
        var search = "\"" + key + "\"";
        int idx = json.indexOf(search);
        if (idx < 0) return null;
        idx = json.indexOf(':', idx + search.length());
        if (idx < 0) return null;
        idx++; // skip colon
        // skip whitespace
        while (idx < json.length() && Character.isWhitespace(json.charAt(idx))) idx++;
        if (idx >= json.length()) return null;

        char ch = json.charAt(idx);
        if (ch == '"') {
            // string value — find closing quote (handling escaped quotes)
            int start = idx + 1;
            int end = start;
            while (end < json.length()) {
                if (json.charAt(end) == '\\') {
                    end += 2;
                    continue;
                }
                if (json.charAt(end) == '"') break;
                end++;
            }
            return json.substring(start, end);
        } else if (ch == 'n' && json.startsWith("null", idx)) {
            return null;
        } else {
            // number or boolean — read until delimiter
            int start = idx;
            while (idx < json.length() && json.charAt(idx) != ',' && json.charAt(idx) != '}'
                    && json.charAt(idx) != ']' && !Character.isWhitespace(json.charAt(idx))) {
                idx++;
            }
            return json.substring(start, idx);
        }
    }

    /**
     * Extracts the raw JSON value (including arrays/objects) for a given key.
     */
    static String jsonRawValue(String json, String key) {
        var search = "\"" + key + "\"";
        int idx = json.indexOf(search);
        if (idx < 0) return null;
        idx = json.indexOf(':', idx + search.length());
        if (idx < 0) return null;
        idx++;
        while (idx < json.length() && Character.isWhitespace(json.charAt(idx))) idx++;
        if (idx >= json.length()) return null;

        char ch = json.charAt(idx);
        if (ch == '[' || ch == '{') {
            char open = ch;
            char close = (ch == '[') ? ']' : '}';
            int depth = 1;
            int start = idx;
            idx++;
            boolean inStr = false;
            while (idx < json.length() && depth > 0) {
                char c = json.charAt(idx);
                if (c == '\\' && inStr) { idx += 2; continue; }
                if (c == '"') inStr = !inStr;
                else if (!inStr) {
                    if (c == open) depth++;
                    else if (c == close) depth--;
                }
                idx++;
            }
            return json.substring(start, idx);
        }
        // Delegate to jsonValue for simple values
        return jsonValue(json, key);
    }

    /**
     * Builds a JSON array of strings, e.g. ["a", "b", "c"].
     */
    static String jsonStringArray(List<String> values) {
        var sb = new StringBuilder("[");
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) sb.append(",");
            sb.append(jsonString(values.get(i)));
        }
        sb.append("]");
        return sb.toString();
    }

    /**
     * Parses a flat JSON object of string values into a Map, e.g. {"a":"x","b":"y"}.
     */
    static Map<String, String> parseStringMap(String json) {
        var result = new LinkedHashMap<String, String>();
        if (json == null) return result;
        json = json.strip();
        if (!json.startsWith("{") || !json.endsWith("}")) return result;
        json = json.substring(1, json.length() - 1).strip();
        if (json.isEmpty()) return result;
        // Split by commas at the top level
        int depth = 0;
        boolean inStr = false;
        int start = 0;
        for (int i = 0; i < json.length(); i++) {
            char c = json.charAt(i);
            if (c == '\\' && inStr) { i++; continue; }
            if (c == '"') inStr = !inStr;
            else if (!inStr) {
                if (c == '{' || c == '[') depth++;
                else if (c == '}' || c == ']') depth--;
                else if (c == ',' && depth == 0) {
                    parseStringMapEntry(json.substring(start, i).strip(), result);
                    start = i + 1;
                }
            }
        }
        parseStringMapEntry(json.substring(start).strip(), result);
        return result;
    }

    private static void parseStringMapEntry(String entry, Map<String, String> map) {
        int colon = entry.indexOf(':');
        if (colon < 0) return;
        String key = entry.substring(0, colon).strip();
        String val = entry.substring(colon + 1).strip();
        if (key.startsWith("\"") && key.endsWith("\"")) key = key.substring(1, key.length() - 1);
        if (val.startsWith("\"") && val.endsWith("\"")) val = val.substring(1, val.length() - 1);
        map.put(key, val);
    }

    /**
     * Parses a JSON array of strings, e.g. ["a", "b", "c"].
     */
    static List<String> parseStringArray(String json) {
        var result = new ArrayList<String>();
        if (json == null) return result;
        var elements = jsonArrayElements(json);
        for (var el : elements) {
            el = el.strip();
            if (el.startsWith("\"") && el.endsWith("\"")) {
                result.add(el.substring(1, el.length() - 1));
            } else {
                result.add(el);
            }
        }
        return result;
    }

    /**
     * Splits a JSON array string into its top-level element strings.
     */
    static List<String> jsonArrayElements(String json) {
        var result = new ArrayList<String>();
        json = json.strip();
        if (!json.startsWith("[") || !json.endsWith("]")) return result;
        json = json.substring(1, json.length() - 1).strip();
        if (json.isEmpty()) return result;

        int depth = 0;
        int start = 0;
        boolean inString = false;
        for (int i = 0; i < json.length(); i++) {
            char ch = json.charAt(i);
            if (ch == '\\' && inString) {
                i++; // skip escaped character
                continue;
            }
            if (ch == '"') {
                inString = !inString;
            } else if (!inString) {
                if (ch == '{' || ch == '[') depth++;
                else if (ch == '}' || ch == ']') depth--;
                else if (ch == ',' && depth == 0) {
                    result.add(json.substring(start, i).strip());
                    start = i + 1;
                }
            }
        }
        var last = json.substring(start).strip();
        if (!last.isEmpty()) result.add(last);
        return result;
    }

    private static double parseDouble(String value) {
        if (value == null) return 0.0;
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException e) {
            return 0.0;
        }
    }

    private static long parseLong(String value) {
        if (value == null) return 0L;
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException e) {
            return 0L;
        }
    }

    private static int parseInt(String value) {
        if (value == null) return 0;
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static boolean parseBool(String value) {
        return "true".equals(value);
    }

    // ── JSON → Record parsers ────────────────────────────────────────────

    private RecordingResult parseRecordingResult(String json) {
        var extraPathsRaw = jsonRawValue(json, "extra_paths");
        Map<String, String> extraPaths = extraPathsRaw != null ? parseStringMap(extraPathsRaw) : null;
        return new RecordingResult(
                jsonValue(json, "name"),
                jsonValue(json, "path"),
                parseDouble(jsonValue(json, "elapsed")),
                jsonValue(json, "gif_path"),
                extraPaths
        );
    }

    private RecordingInfo parseRecordingInfo(String json) {
        var formatsRaw = jsonRawValue(json, "formats_available");
        List<String> formats = formatsRaw != null ? parseStringArray(formatsRaw) : null;
        return new RecordingInfo(
                jsonValue(json, "name"),
                jsonValue(json, "path"),
                parseLong(jsonValue(json, "size")),
                jsonValue(json, "created"),
                jsonValue(json, "gif_path"),
                parseLong(jsonValue(json, "gif_size")),
                jsonValue(json, "webm_path"),
                parseLong(jsonValue(json, "webm_size")),
                formats
        );
    }

    private RecordingStatus parseRecordingStatus(String json) {
        return new RecordingStatus(
                parseBool(jsonValue(json, "recording")),
                jsonValue(json, "name"),
                parseDouble(jsonValue(json, "elapsed"))
        );
    }

    private Health parseHealth(String json) {
        return new Health(
                jsonValue(json, "status"),
                parseBool(jsonValue(json, "recording")),
                jsonValue(json, "display"),
                parseStringArray(jsonRawValue(json, "panels")),
                parseDouble(jsonValue(json, "uptime"))
        );
    }

    private List<Panel> parsePanelList(String json) {
        var elements = jsonArrayElements(json);
        var panels = new ArrayList<Panel>(elements.size());
        for (var el : elements) {
            panels.add(new Panel(
                    jsonValue(el, "name"),
                    jsonValue(el, "title"),
                    parseInt(jsonValue(el, "width")),
                    parseInt(jsonValue(el, "height"))
            ));
        }
        return panels;
    }

    private List<String> parseWarnings(String json) {
        var raw = jsonRawValue(json, "warnings");
        if (raw == null) return List.of();
        return parseStringArray(raw);
    }

    private CompositionStatus parseCompositionStatus(String json) {
        return new CompositionStatus(
                jsonValue(json, "name"),
                jsonValue(json, "status"),
                jsonValue(json, "output_path"),
                jsonValue(json, "error")
        );
    }

    /**
     * Parses a flat JSON object into a Map. Values are strings, numbers, or booleans.
     */
    private Map<String, Object> parseJsonObject(String json) {
        var result = new LinkedHashMap<String, Object>();
        if (json == null || json.isBlank()) return result;
        json = json.strip();
        if (!json.startsWith("{") || !json.endsWith("}")) return result;
        // Extract keys by scanning for "key": patterns
        int idx = 1; // skip opening brace
        while (idx < json.length() - 1) {
            // skip whitespace
            while (idx < json.length() && Character.isWhitespace(json.charAt(idx))) idx++;
            if (idx >= json.length() - 1 || json.charAt(idx) == '}') break;
            if (json.charAt(idx) == ',') { idx++; continue; }
            // expect a quoted key
            if (json.charAt(idx) != '"') break;
            int keyStart = idx + 1;
            int keyEnd = json.indexOf('"', keyStart);
            if (keyEnd < 0) break;
            String key = json.substring(keyStart, keyEnd);
            idx = keyEnd + 1;
            // skip colon and whitespace
            while (idx < json.length() && (json.charAt(idx) == ':' || Character.isWhitespace(json.charAt(idx)))) idx++;
            if (idx >= json.length()) break;
            // parse value
            char ch = json.charAt(idx);
            if (ch == '"') {
                // string value
                int vStart = idx + 1;
                int vEnd = vStart;
                while (vEnd < json.length()) {
                    if (json.charAt(vEnd) == '\\') { vEnd += 2; continue; }
                    if (json.charAt(vEnd) == '"') break;
                    vEnd++;
                }
                result.put(key, json.substring(vStart, vEnd));
                idx = vEnd + 1;
            } else if (ch == 'n' && json.startsWith("null", idx)) {
                result.put(key, null);
                idx += 4;
            } else if (ch == 't' && json.startsWith("true", idx)) {
                result.put(key, Boolean.TRUE);
                idx += 4;
            } else if (ch == 'f' && json.startsWith("false", idx)) {
                result.put(key, Boolean.FALSE);
                idx += 5;
            } else if (ch == '[' || ch == '{') {
                // skip nested structure
                char open = ch;
                char close = (ch == '[') ? ']' : '}';
                int depth = 1;
                int sStart = idx;
                idx++;
                boolean inStr = false;
                while (idx < json.length() && depth > 0) {
                    char c = json.charAt(idx);
                    if (c == '\\' && inStr) { idx += 2; continue; }
                    if (c == '"') inStr = !inStr;
                    else if (!inStr) {
                        if (c == open) depth++;
                        else if (c == close) depth--;
                    }
                    idx++;
                }
                result.put(key, json.substring(sStart, idx));
            } else {
                // number
                int vStart = idx;
                while (idx < json.length() && json.charAt(idx) != ',' && json.charAt(idx) != '}'
                        && !Character.isWhitespace(json.charAt(idx))) idx++;
                String raw = json.substring(vStart, idx);
                try {
                    if (raw.contains(".")) {
                        result.put(key, Double.parseDouble(raw));
                    } else {
                        long l = Long.parseLong(raw);
                        if (l >= Integer.MIN_VALUE && l <= Integer.MAX_VALUE) {
                            result.put(key, (int) l);
                        } else {
                            result.put(key, l);
                        }
                    }
                } catch (NumberFormatException e) {
                    result.put(key, raw);
                }
            }
        }
        return result;
    }

    /**
     * Parses a JSON array of objects into a List of Maps.
     */
    private List<Map<String, Object>> parseJsonArray(String json) {
        var result = new ArrayList<Map<String, Object>>();
        if (json == null || json.isBlank()) return result;
        var elements = jsonArrayElements(json);
        for (var el : elements) {
            result.add(parseJsonObject(el));
        }
        return result;
    }

    private List<RecordingInfo> parseRecordingInfoList(String json) {
        var elements = jsonArrayElements(json);
        var list = new ArrayList<RecordingInfo>(elements.size());
        for (var el : elements) {
            list.add(parseRecordingInfo(el));
        }
        return list;
    }
}
