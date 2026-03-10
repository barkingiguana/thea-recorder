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

    // ── Panels ───────────────────────────────────────────────────────────

    /**
     * Adds a new panel.
     *
     * @param name  panel identifier
     * @param title panel title
     * @param width panel width in characters
     */
    public void addPanel(String name, String title, int width) {
        var body = jsonObject(Map.of(
                "name", jsonString(name),
                "title", jsonString(title),
                "width", String.valueOf(width)
        ));
        post("/panels", body, 201);
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
     */
    public void startRecording(String name) {
        var body = jsonObject(Map.of("name", jsonString(name)));
        post("/recording/start", body, 201);
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
        return new RecordingResult(
                jsonValue(json, "name"),
                jsonValue(json, "path"),
                parseDouble(jsonValue(json, "elapsed"))
        );
    }

    private RecordingInfo parseRecordingInfo(String json) {
        return new RecordingInfo(
                jsonValue(json, "name"),
                jsonValue(json, "path"),
                parseLong(jsonValue(json, "size")),
                jsonValue(json, "created")
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
                    parseInt(jsonValue(el, "width"))
            ));
        }
        return panels;
    }

    private CompositionStatus parseCompositionStatus(String json) {
        return new CompositionStatus(
                jsonValue(json, "name"),
                jsonValue(json, "status"),
                jsonValue(json, "output_path"),
                jsonValue(json, "error")
        );
    }

    private List<RecordingInfo> parseRecordingInfoList(String json) {
        var elements = jsonArrayElements(json);
        var list = new ArrayList<RecordingInfo>(elements.size());
        for (var el : elements) {
            list.add(new RecordingInfo(
                    jsonValue(el, "name"),
                    jsonValue(el, "path"),
                    parseLong(jsonValue(el, "size")),
                    jsonValue(el, "created")
            ));
        }
        return list;
    }
}
