# thea-recorder Node.js SDK

TypeScript/JavaScript client for the [thea-recorder](../../README.md) HTTP server.

- Zero runtime dependencies (uses the built-in Node 18+ `fetch` API)
- Full TypeScript type definitions
- Async/await throughout
- High-level helpers for common workflows

## Installation

```bash
npm install thea-recorder
```

## Quick start

```typescript
import { RecorderClient } from "thea-recorder";

const client = new RecorderClient({
  url: "http://localhost:9123", // or set THEA_URL env var
});

// Start display and record (auto-waits for server readiness)
await client.startDisplay();

const result = await client.recording("my-demo", async () => {
  // ... do work while recording ...
  await client.addPanel({ name: "code", title: "Source", width: 80 });
  await client.updatePanel("code", { text: "console.log('hello')", focus_line: 1 });
});

console.log(`Recorded ${result.name} (${result.elapsed}s) → ${result.path}`);
```

## API

### Constructor

```typescript
new RecorderClient(options?: {
  url?: string;      // default: process.env.THEA_URL ?? "http://localhost:9123"
  timeout?: number;  // request timeout in ms, default: 30000
})
```

### Display

| Method | Description |
|--------|-------------|
| `startDisplay()` | Start the virtual display |
| `stopDisplay()` | Stop the virtual display |

### Panels

| Method | Description |
|--------|-------------|
| `addPanel({ name, title, width })` | Create a new panel |
| `updatePanel(name, { text, focus_line? })` | Update panel content |
| `removePanel(name)` | Remove a panel |
| `listPanels()` | List all panels |

### Recording

| Method | Description |
|--------|-------------|
| `startRecording(name)` | Start recording with the given name |
| `stopRecording(options?)` | Stop recording; returns `{ path, elapsed, name, gif_path?, extra_paths? }`. Pass `StopRecordingOptions` to produce GIF/WebM. |
| `recordingElapsed()` | Get elapsed recording time |
| `recordingStatus()` | Get recording status |

### Recordings

| Method | Description |
|--------|-------------|
| `listRecordings()` | List all recordings |
| `convertToGif(name, options?)` | Convert an existing recording to GIF; options: `{ fps?, width? }` |
| `downloadRecording(name, format?)` | Download as `ReadableStream<Uint8Array>`. Optional format: `"gif"`, `"webm"`. |
| `downloadRecordingToFile(name, path, format?)` | Download and save to a local file. Optional format: `"gif"`, `"webm"`. |
| `recordingInfo(name)` | Get metadata for a recording (includes `gif_path`, `webm_path`, `formats_available` when applicable) |

### System

| Method | Description |
|--------|-------------|
| `health()` | Health check |
| `cleanup()` | Clean up resources |
| `waitUntilReady(timeoutMs)` | Poll `/health` until the server responds. Called automatically on first API call. |

### Helpers

```typescript
// Scoped recording — stops automatically when fn completes or throws
const result = await client.recording("name", async () => {
  // ... your logic ...
});

// Record and also produce a GIF
const result2 = await client.recording("name", async () => {
  // ... your logic ...
}, { gif: true, gif_fps: 10, gif_width: 720 });
console.log(result2.gif_path); // path to the generated GIF

// Stop with multiple output formats
await client.stopRecording({ output_formats: ["gif", "webm"] });

// Convert an existing recording to GIF
const gif = await client.convertToGif("my-recording", { fps: 10, width: 720 });

// Download a specific format
await client.downloadRecordingToFile("my-recording", "output.gif", "gif");

// Scoped panel — removed automatically when fn completes or throws
await client.withPanel("code", "Source Code", 80, async () => {
  await client.updatePanel("code", { text: "..." });
});

// Explicit server readiness check (called automatically on first API call)
await client.waitUntilReady(10_000);
```

### Error handling

All methods throw `RecorderError` on failure:

```typescript
import { RecorderError } from "thea-recorder";

try {
  await client.startRecording("demo");
} catch (err) {
  if (err instanceof RecorderError) {
    console.error(err.message);  // human-readable message
    console.error(err.status);   // HTTP status code (if available)
    console.error(err.body);     // response body text (if available)
  }
}
```

## Development

```bash
npm install
npm test
npm run build
```

## Requirements

- Node.js 18 or later
