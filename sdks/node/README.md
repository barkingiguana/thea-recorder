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
| `stopRecording()` | Stop recording; returns `{ path, elapsed, name }` |
| `recordingElapsed()` | Get elapsed recording time |
| `recordingStatus()` | Get recording status |

### Recordings

| Method | Description |
|--------|-------------|
| `listRecordings()` | List all recordings |
| `downloadRecording(name)` | Download as `ReadableStream<Uint8Array>` |
| `downloadRecordingToFile(name, path)` | Download and save to a local file |
| `recordingInfo(name)` | Get metadata for a recording |

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
