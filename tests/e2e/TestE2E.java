import com.recorder.RecorderClient;
import java.time.Duration;

/**
 * E2E test for the Java SDK against a live recorder server.
 */
public class TestE2E {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("THEA_URL");
        if (url == null || url.isEmpty()) url = "http://localhost:9123";

        try (var client = new RecorderClient(url)) {
            System.out.println("[java] Waiting for server...");
            client.waitUntilReady(Duration.ofSeconds(30));

            System.out.println("[java] Starting display...");
            client.startDisplay();

            System.out.println("[java] Health check...");
            var health = client.health();
            assertEq("ok", health.status(), "health.status");
            System.out.printf("[java] Health: status=%s display=%s%n", health.status(), health.display());

            System.out.println("[java] Adding panel...");
            client.addPanel("editor", "Code Editor", 80);

            System.out.println("[java] Updating panel...");
            client.updatePanel("editor", "System.out.println(\"hello from Java\")", 1);

            System.out.println("[java] Listing panels...");
            var panels = client.listPanels();
            assertEq(1, panels.size(), "panels.size");
            assertEq("editor", panels.get(0).name(), "panel name");

            System.out.println("[java] Starting recording...");
            client.startRecording("java-e2e-test");

            Thread.sleep(2000);

            System.out.println("[java] Checking recording status...");
            var status = client.recordingStatus();
            assertTrue(status.recording(), "expected recording=true");

            System.out.println("[java] Stopping recording...");
            var result = client.stopRecording();
            assertTrue(result.path() != null && !result.path().isEmpty(), "expected non-empty path");
            System.out.printf("[java] Recording saved: %s (%.1fs)%n", result.path(), result.elapsed());

            System.out.println("[java] Removing panel...");
            client.removePanel("editor");

            System.out.println("[java] Listing recordings...");
            var recordings = client.listRecordings();
            assertTrue(recordings.size() >= 1, "expected >= 1 recording");

            System.out.println("[java] Stopping display...");
            client.stopDisplay();

            System.out.println("[java] Cleanup...");
            client.cleanup();

            System.out.println("[java] ALL PASSED");
        }
    }

    static void assertEq(Object expected, Object actual, String label) {
        if (!expected.equals(actual)) {
            System.err.printf("[java] ASSERTION FAILED: %s: expected %s, got %s%n", label, expected, actual);
            System.exit(1);
        }
    }

    static void assertTrue(boolean cond, String msg) {
        if (!cond) {
            System.err.printf("[java] ASSERTION FAILED: %s%n", msg);
            System.exit(1);
        }
    }
}
