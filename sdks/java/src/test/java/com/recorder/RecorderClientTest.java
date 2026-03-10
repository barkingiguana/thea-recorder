package com.recorder;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class RecorderClientTest {

    private HttpServer server;
    private RecorderClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.start();
        int port = server.getAddress().getPort();
        client = new RecorderClient("http://localhost:" + port, Duration.ofSeconds(5));
    }

    @AfterEach
    void tearDown() {
        server.stop(0);
    }

    // ── Display ──────────────────────────────────────────────────────────

    @Test
    void startDisplay() {
        server.createContext("/display/start", ex -> {
            assertEquals("POST", ex.getRequestMethod());
            respond(ex, 201, "{}");
        });
        assertDoesNotThrow(() -> client.startDisplay());
    }

    @Test
    void stopDisplay() {
        server.createContext("/display/stop", ex -> {
            assertEquals("POST", ex.getRequestMethod());
            respond(ex, 200, "{}");
        });
        assertDoesNotThrow(() -> client.stopDisplay());
    }

    // ── Panels ───────────────────────────────────────────────────────────

    @Test
    void addPanel() {
        var receivedBody = new AtomicReference<String>();
        server.createContext("/panels", ex -> {
            assertEquals("POST", ex.getRequestMethod());
            receivedBody.set(new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            respond(ex, 201, "{}");
        });

        client.addPanel("editor", "Code Editor", 80);

        var body = receivedBody.get();
        assertNotNull(body);
        assertTrue(body.contains("\"name\":\"editor\""));
        assertTrue(body.contains("\"title\":\"Code Editor\""));
        assertTrue(body.contains("\"width\":80"));
    }

    @Test
    void updatePanel() {
        var receivedBody = new AtomicReference<String>();
        server.createContext("/panels/editor", ex -> {
            assertEquals("PUT", ex.getRequestMethod());
            receivedBody.set(new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            respond(ex, 200, "{}");
        });

        client.updatePanel("editor", "hello world", 5);

        var body = receivedBody.get();
        assertNotNull(body);
        assertTrue(body.contains("\"text\":\"hello world\""));
        assertTrue(body.contains("\"focus_line\":5"));
    }

    @Test
    void removePanel() {
        server.createContext("/panels/editor", ex -> {
            assertEquals("DELETE", ex.getRequestMethod());
            respond(ex, 200, "{}");
        });
        assertDoesNotThrow(() -> client.removePanel("editor"));
    }

    @Test
    void listPanels() {
        server.createContext("/panels", ex -> {
            assertEquals("GET", ex.getRequestMethod());
            respond(ex, 200, """
                    [
                      {"name":"editor","title":"Code Editor","width":80},
                      {"name":"output","title":"Output","width":40}
                    ]
                    """);
        });

        var panels = client.listPanels();
        assertEquals(2, panels.size());
        assertEquals("editor", panels.get(0).name());
        assertEquals("Code Editor", panels.get(0).title());
        assertEquals(80, panels.get(0).width());
        assertEquals("output", panels.get(1).name());
    }

    @Test
    void withPanelScopedHelper() {
        var addCalled = new AtomicReference<>(false);
        var removeCalled = new AtomicReference<>(false);
        var actionRan = new AtomicReference<>(false);

        server.createContext("/panels", ex -> {
            if ("POST".equals(ex.getRequestMethod())) {
                addCalled.set(true);
                respond(ex, 201, "{}");
            } else {
                respond(ex, 405, "{}");
            }
        });
        server.createContext("/panels/test-panel", ex -> {
            if ("DELETE".equals(ex.getRequestMethod())) {
                removeCalled.set(true);
                respond(ex, 200, "{}");
            } else {
                respond(ex, 405, "{}");
            }
        });

        client.withPanel("test-panel", "Test", 60, () -> actionRan.set(true));

        assertTrue(addCalled.get());
        assertTrue(actionRan.get());
        assertTrue(removeCalled.get());
    }

    // ── Recording ────────────────────────────────────────────────────────

    @Test
    void startRecording() {
        var receivedBody = new AtomicReference<String>();
        server.createContext("/recording/start", ex -> {
            assertEquals("POST", ex.getRequestMethod());
            receivedBody.set(new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            respond(ex, 201, "{}");
        });

        client.startRecording("my-test");
        assertTrue(receivedBody.get().contains("\"name\":\"my-test\""));
    }

    @Test
    void stopRecording() {
        server.createContext("/recording/stop", ex -> {
            assertEquals("POST", ex.getRequestMethod());
            respond(ex, 200, """
                    {"name":"my-test","path":"/recordings/my-test.mp4","elapsed":12.5}
                    """);
        });

        var result = client.stopRecording();
        assertEquals("my-test", result.name());
        assertEquals("/recordings/my-test.mp4", result.path());
        assertEquals(12.5, result.elapsed(), 0.001);
    }

    @Test
    void recordingElapsed() {
        server.createContext("/recording/elapsed", ex -> {
            respond(ex, 200, """
                    {"elapsed":7.3}
                    """);
        });

        assertEquals(7.3, client.recordingElapsed(), 0.001);
    }

    @Test
    void recordingStatus() {
        server.createContext("/recording/status", ex -> {
            respond(ex, 200, """
                    {"recording":true,"name":"session-1","elapsed":45.2}
                    """);
        });

        var status = client.recordingStatus();
        assertTrue(status.recording());
        assertEquals("session-1", status.name());
        assertEquals(45.2, status.elapsed(), 0.001);
    }

    @Test
    void recordingScopedHelper() {
        var startCalled = new AtomicReference<>(false);
        var stopCalled = new AtomicReference<>(false);

        server.createContext("/recording/start", ex -> {
            startCalled.set(true);
            respond(ex, 201, "{}");
        });
        server.createContext("/recording/stop", ex -> {
            stopCalled.set(true);
            respond(ex, 200, """
                    {"name":"scoped","path":"/recordings/scoped.mp4","elapsed":3.0}
                    """);
        });

        var result = client.recording("scoped", c -> {
            assertTrue(startCalled.get());
        });
        assertTrue(stopCalled.get());
        assertEquals("scoped", result.name());
    }

    // ── Recordings ───────────────────────────────────────────────────────

    @Test
    void listRecordings() {
        server.createContext("/recordings", ex -> {
            respond(ex, 200, """
                    [
                      {"name":"test1","path":"/r/test1.mp4","size":1024,"created":"2025-01-01T00:00:00Z"},
                      {"name":"test2","path":"/r/test2.mp4","size":2048,"created":"2025-01-02T00:00:00Z"}
                    ]
                    """);
        });

        var recordings = client.listRecordings();
        assertEquals(2, recordings.size());
        assertEquals("test1", recordings.get(0).name());
        assertEquals(1024, recordings.get(0).size());
        assertEquals("test2", recordings.get(1).name());
        assertEquals(2048, recordings.get(1).size());
    }

    @Test
    void downloadRecordingToFile() throws IOException {
        var content = new byte[]{0x00, 0x01, 0x02, 0x03};
        server.createContext("/recordings/test.mp4", ex -> {
            ex.sendResponseHeaders(200, content.length);
            ex.getResponseBody().write(content);
            ex.getResponseBody().close();
        });

        var tempFile = Files.createTempFile("recorder-test-", ".mp4");
        try {
            client.downloadRecording("test.mp4", tempFile);
            assertArrayEquals(content, Files.readAllBytes(tempFile));
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }

    @Test
    void downloadRecordingToStream() {
        var content = "fake-mp4-data".getBytes(StandardCharsets.UTF_8);
        server.createContext("/recordings/test.mp4", ex -> {
            ex.sendResponseHeaders(200, content.length);
            ex.getResponseBody().write(content);
            ex.getResponseBody().close();
        });

        var baos = new ByteArrayOutputStream();
        client.downloadRecording("test.mp4", baos);
        assertArrayEquals(content, baos.toByteArray());
    }

    @Test
    void recordingInfo() {
        server.createContext("/recordings/my-rec/info", ex -> {
            respond(ex, 200, """
                    {"name":"my-rec","path":"/r/my-rec.mp4","size":5000,"created":"2025-06-15T10:30:00Z"}
                    """);
        });

        var info = client.recordingInfo("my-rec");
        assertEquals("my-rec", info.name());
        assertEquals("/r/my-rec.mp4", info.path());
        assertEquals(5000, info.size());
        assertEquals("2025-06-15T10:30:00Z", info.created());
    }

    // ── Health & Cleanup ─────────────────────────────────────────────────

    @Test
    void health() {
        server.createContext("/health", ex -> {
            respond(ex, 200, """
                    {"status":"ok","recording":false,"display":":99","panels":["editor","status"],"uptime":120.5}
                    """);
        });

        var h = client.health();
        assertEquals("ok", h.status());
        assertFalse(h.recording());
        assertEquals(":99", h.display());
        assertEquals(List.of("editor", "status"), h.panels());
        assertEquals(120.5, h.uptime(), 0.001);
    }

    @Test
    void cleanupEndpoint() {
        server.createContext("/cleanup", ex -> {
            assertEquals("POST", ex.getRequestMethod());
            respond(ex, 200, "{}");
        });
        assertDoesNotThrow(() -> client.cleanup());
    }

    @Test
    void waitUntilReady() {
        var callCount = new AtomicReference<>(0);
        server.createContext("/health", ex -> {
            int n = callCount.updateAndGet(v -> v + 1);
            if (n < 3) {
                ex.sendResponseHeaders(503, -1);
                ex.close();
            } else {
                respond(ex, 200, """
                        {"status":"ok","recording":false,"display":"","panels":[],"uptime":0.1}
                        """);
            }
        });

        assertDoesNotThrow(() -> client.waitUntilReady(Duration.ofSeconds(5)));
        assertTrue(callCount.get() >= 3);
    }

    @Test
    void waitUntilReadyTimeout() {
        server.createContext("/health", ex -> {
            ex.sendResponseHeaders(503, -1);
            ex.close();
        });

        assertThrows(RecorderError.class, () -> client.waitUntilReady(Duration.ofMillis(500)));
    }

    // ── Error handling ───────────────────────────────────────────────────

    @Test
    void errorOnUnexpectedStatus() {
        server.createContext("/display/start", ex -> {
            respond(ex, 500, """
                    {"error":"internal error"}
                    """);
        });

        var error = assertThrows(RecorderError.class, () -> client.startDisplay());
        assertEquals(500, error.getStatusCode());
    }

    // ── JSON helper tests ────────────────────────────────────────────────

    @Test
    void jsonValueParsing() {
        var json = """
                {"name":"test","count":42,"active":true,"rate":3.14}
                """;
        assertEquals("test", RecorderClient.jsonValue(json, "name"));
        assertEquals("42", RecorderClient.jsonValue(json, "count"));
        assertEquals("true", RecorderClient.jsonValue(json, "active"));
        assertEquals("3.14", RecorderClient.jsonValue(json, "rate"));
        assertNull(RecorderClient.jsonValue(json, "missing"));
    }

    @Test
    void jsonValueWithNull() {
        var json = """
                {"name":null}
                """;
        assertNull(RecorderClient.jsonValue(json, "name"));
    }

    @Test
    void jsonArrayElementsParsing() {
        var json = """
                [{"a":1},{"b":2},{"c":3}]
                """;
        var elements = RecorderClient.jsonArrayElements(json);
        assertEquals(3, elements.size());
        assertEquals("1", RecorderClient.jsonValue(elements.get(0), "a"));
        assertEquals("2", RecorderClient.jsonValue(elements.get(1), "b"));
    }

    @Test
    void jsonArrayEmpty() {
        assertEquals(0, RecorderClient.jsonArrayElements("[]").size());
    }

    @Test
    void jsonStringEscaping() {
        assertEquals("\"hello\\nworld\"", RecorderClient.jsonString("hello\nworld"));
        assertEquals("\"say \\\"hi\\\"\"", RecorderClient.jsonString("say \"hi\""));
        assertEquals("null", RecorderClient.jsonString(null));
    }

    // ── Utility ──────────────────────────────────────────────────────────

    private static void respond(HttpExchange ex, int status, String body) throws IOException {
        var bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "application/json");
        ex.sendResponseHeaders(status, bytes.length);
        ex.getResponseBody().write(bytes);
        ex.getResponseBody().close();
    }
}
