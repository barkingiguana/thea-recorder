# thea-recorder Java SDK

Java client for the thea-recorder HTTP server. Zero external dependencies — uses only `java.net.http.HttpClient` (Java 11+) and Java 17 records.

## Installation

Add to your `pom.xml`:

```xml
<dependency>
    <groupId>com.thea</groupId>
    <artifactId>thea-recorder</artifactId>
    <version>1.0.0</version>
</dependency>
```

## Quick Start

```java
try (var client = new RecorderClient("http://localhost:9123")) {
    client.startDisplay();

    // Scoped recording — automatically starts and stops
    var result = client.recording("my-test", c -> {
        c.addPanel("editor", "Code Editor", 80);
        c.updatePanel("editor", "print('hello')", 1);
        c.removePanel("editor");
    });

    System.out.println("Recording saved: " + result.path());
    client.stopDisplay();
}
```

## Usage

### Constructor

```java
// Explicit URL
var client = new RecorderClient("http://localhost:9123");

// From THEA_URL environment variable
var client = new RecorderClient();

// With custom timeout
var client = new RecorderClient("http://localhost:9123", Duration.ofSeconds(60));
```

### Display

```java
client.startDisplay();
client.stopDisplay();
```

### Panels

```java
client.addPanel("editor", "Code Editor", 80);
client.updatePanel("editor", "line 1\nline 2\nline 3", 2);
client.removePanel("editor");
List<Panel> panels = client.listPanels();

// Scoped panel — automatically added and removed
client.withPanel("terminal", "Terminal", 120, () -> {
    // panel is active here
});
```

### Recording

```java
client.startRecording("test-session");
// ... perform actions ...
RecordingResult result = client.stopRecording();

// Scoped recording
RecordingResult result = client.recording("test-session", c -> {
    // recording is active here
});

// Status
RecordingStatus status = client.recordingStatus();
double elapsed = client.recordingElapsed();
```

### Recordings

```java
List<RecordingInfo> recordings = client.listRecordings();
RecordingInfo info = client.recordingInfo("my-recording");

// Download to file
client.downloadRecording("my-recording", Path.of("output.mp4"));

// Download to stream
try (var out = new FileOutputStream("output.mp4")) {
    client.downloadRecording("my-recording", out);
}
```

### Health and Cleanup

```java
Health health = client.health();
client.waitUntilReady(Duration.ofSeconds(10));  // called automatically on first API call
client.cleanup();
```

## Data Types

All responses use Java records:

| Record            | Fields                                        |
|-------------------|-----------------------------------------------|
| `Panel`           | `name`, `title`, `width`                      |
| `RecordingResult` | `name`, `path`, `elapsed`                     |
| `RecordingInfo`   | `name`, `path`, `size`, `created`             |
| `RecordingStatus` | `recording`, `name`, `elapsed`                |
| `Health`          | `status`, `recording`, `display`, `panels`, `uptime` |

## Error Handling

All errors throw `RecorderError` (extends `RuntimeException`):

```java
try {
    client.startRecording("test");
} catch (RecorderError e) {
    System.err.println("Status: " + e.getStatusCode());
    System.err.println("Message: " + e.getMessage());
}
```

## Building

```bash
mvn clean package
```

## Running Tests

```bash
mvn test
```

Tests use JDK's built-in `com.sun.net.httpserver` for mock HTTP — no WireMock or other test dependencies needed beyond JUnit 5.
