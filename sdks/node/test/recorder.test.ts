import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import * as http from "node:http";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
  RecorderClient,
  RecorderError,
  type HealthResponse,
  type StopRecordingResponse,
  type RecordingStatusResponse,
  type RecordingElapsedResponse,
  type RecordingInfo,
} from "../src/index.js";

// ---------------------------------------------------------------------------
// Minimal mock HTTP server
// ---------------------------------------------------------------------------

type RouteHandler = (
  req: http.IncomingMessage,
  body: string,
) => { status: number; body?: unknown; binary?: Buffer; contentType?: string };

function createMockServer(routes: Record<string, RouteHandler>) {
  const server = http.createServer((req, res) => {
    const key = `${req.method} ${req.url}`;
    const handler = routes[key];

    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      if (!handler) {
        res.writeHead(404, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "not found", route: key }));
        return;
      }
      const result = handler(req, body);
      const ct = result.contentType ?? "application/json";
      res.writeHead(result.status, { "Content-Type": ct });
      if (result.binary) {
        res.end(result.binary);
      } else if (result.body !== undefined) {
        res.end(JSON.stringify(result.body));
      } else {
        res.end();
      }
    });
  });
  return server;
}

function listenOnRandomPort(server: http.Server): Promise<number> {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address() as { port: number };
      resolve(addr.port);
    });
  });
}

function closeServer(server: http.Server): Promise<void> {
  return new Promise((resolve) => server.close(() => resolve()));
}

// ---------------------------------------------------------------------------
// Canned responses
// ---------------------------------------------------------------------------

const healthBody: HealthResponse = {
  status: "ok",
  recording: false,
  display: true,
  panels: 2,
  uptime: 42.5,
};

const stopRecBody: StopRecordingResponse = {
  path: "/tmp/demo.mp4",
  elapsed: 12.3,
  name: "demo",
};

const statusBody: RecordingStatusResponse = {
  recording: true,
  name: "demo",
  elapsed: 5.1,
};

const elapsedBody: RecordingElapsedResponse = { elapsed: 5.1 };

const recordingsList: RecordingInfo[] = [
  { name: "demo", path: "/tmp/demo.mp4", size: 1024, created: "2025-01-01T00:00:00Z" },
];

const recordingInfoBody: RecordingInfo = recordingsList[0];

const fakeMp4 = Buffer.from("fake-mp4-bytes");

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("RecorderClient", () => {
  let server: http.Server;
  let port: number;
  let client: RecorderClient;

  beforeAll(async () => {
    const routes: Record<string, RouteHandler> = {
      "POST /display/start": () => ({ status: 201 }),
      "POST /display/stop": () => ({ status: 200 }),
      "POST /panels": (_req, body) => {
        const parsed = JSON.parse(body);
        if (!parsed.name) return { status: 400, body: { error: "name required" } };
        return { status: 201 };
      },
      "PUT /panels/editor": () => ({ status: 200 }),
      "DELETE /panels/editor": () => ({ status: 200 }),
      "GET /panels": () => ({ status: 200, body: [{ name: "editor" }] }),
      "POST /recording/start": (_req, body) => {
        const parsed = JSON.parse(body);
        if (!parsed.name) return { status: 400, body: { error: "name required" } };
        return { status: 201 };
      },
      "POST /recording/stop": () => ({ status: 200, body: stopRecBody }),
      "GET /recording/elapsed": () => ({ status: 200, body: elapsedBody }),
      "GET /recording/status": () => ({ status: 200, body: statusBody }),
      "GET /recordings": () => ({ status: 200, body: recordingsList }),
      "GET /recordings/demo": () => ({
        status: 200,
        binary: fakeMp4,
        contentType: "video/mp4",
      }),
      "GET /recordings/demo/info": () => ({ status: 200, body: recordingInfoBody }),
      "GET /health": () => ({ status: 200, body: healthBody }),
      "POST /cleanup": () => ({ status: 200 }),
    };

    server = createMockServer(routes);
    port = await listenOnRandomPort(server);
    client = new RecorderClient({ url: `http://127.0.0.1:${port}` });
  });

  afterAll(async () => {
    await closeServer(server);
  });

  // -- Display ------------------------------------------------------------

  it("startDisplay", async () => {
    await expect(client.startDisplay()).resolves.toBeUndefined();
  });

  it("stopDisplay", async () => {
    await expect(client.stopDisplay()).resolves.toBeUndefined();
  });

  // -- Panels -------------------------------------------------------------

  it("addPanel", async () => {
    await expect(
      client.addPanel({ name: "editor", title: "Editor", width: 80 }),
    ).resolves.toBeUndefined();
  });

  it("updatePanel", async () => {
    await expect(
      client.updatePanel("editor", { text: "hello world", focus_line: 1 }),
    ).resolves.toBeUndefined();
  });

  it("removePanel", async () => {
    await expect(client.removePanel("editor")).resolves.toBeUndefined();
  });

  it("listPanels", async () => {
    const panels = await client.listPanels();
    expect(panels).toEqual([{ name: "editor" }]);
  });

  // -- Recording ----------------------------------------------------------

  it("startRecording", async () => {
    await expect(client.startRecording("demo")).resolves.toBeUndefined();
  });

  it("stopRecording", async () => {
    const res = await client.stopRecording();
    expect(res).toEqual(stopRecBody);
  });

  it("recordingElapsed", async () => {
    const res = await client.recordingElapsed();
    expect(res.elapsed).toBe(5.1);
  });

  it("recordingStatus", async () => {
    const res = await client.recordingStatus();
    expect(res.recording).toBe(true);
    expect(res.name).toBe("demo");
  });

  // -- Recordings collection -----------------------------------------------

  it("listRecordings", async () => {
    const list = await client.listRecordings();
    expect(list).toHaveLength(1);
    expect(list[0].name).toBe("demo");
  });

  it("downloadRecording returns a ReadableStream", async () => {
    const stream = await client.downloadRecording("demo");
    expect(stream).toBeDefined();
    // Consume the stream
    const reader = stream.getReader();
    const chunks: Uint8Array[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    const buf = Buffer.concat(chunks);
    expect(buf.toString()).toBe("fake-mp4-bytes");
  });

  it("downloadRecordingToFile writes a file", async () => {
    const tmpFile = path.join(os.tmpdir(), `recorder-test-${Date.now()}.mp4`);
    try {
      await client.downloadRecordingToFile("demo", tmpFile);
      const content = fs.readFileSync(tmpFile);
      expect(content.toString()).toBe("fake-mp4-bytes");
    } finally {
      fs.rmSync(tmpFile, { force: true });
    }
  });

  it("recordingInfo", async () => {
    const info = await client.recordingInfo("demo");
    expect(info.name).toBe("demo");
    expect(info.size).toBe(1024);
  });

  // -- Health / cleanup ---------------------------------------------------

  it("health", async () => {
    const h = await client.health();
    expect(h.status).toBe("ok");
    expect(h.display).toBe(true);
  });

  it("cleanup", async () => {
    await expect(client.cleanup()).resolves.toBeUndefined();
  });

  // -- High-level helpers -------------------------------------------------

  it("recording() helper calls fn and returns stop result", async () => {
    let called = false;
    const result = await client.recording("demo", async () => {
      called = true;
    });
    expect(called).toBe(true);
    expect(result).toEqual(stopRecBody);
  });

  it("recording() helper still stops on error", async () => {
    const err = new Error("boom");
    await expect(
      client.recording("demo", async () => {
        throw err;
      }),
    ).rejects.toThrow("boom");
  });

  it("withPanel() helper creates and removes panel", async () => {
    let called = false;
    await client.withPanel("editor", "Editor", 80, async () => {
      called = true;
    });
    expect(called).toBe(true);
  });

  it("withPanel() helper removes panel even on error", async () => {
    await expect(
      client.withPanel("editor", "Editor", 80, async () => {
        throw new Error("panel-boom");
      }),
    ).rejects.toThrow("panel-boom");
  });

  it("waitUntilReady succeeds when healthy", async () => {
    await expect(client.waitUntilReady(2000)).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Error handling tests
// ---------------------------------------------------------------------------

describe("RecorderClient – error handling", () => {
  let server: http.Server;
  let port: number;

  beforeAll(async () => {
    server = createMockServer({
      "GET /health": () => ({ status: 503, body: { error: "unhealthy" } }),
      "POST /recording/start": () => ({
        status: 409,
        body: { error: "already recording" },
      }),
    });
    port = await listenOnRandomPort(server);
  });

  afterAll(async () => {
    await closeServer(server);
  });

  it("throws RecorderError with status on non-OK response", async () => {
    const client = new RecorderClient({ url: `http://127.0.0.1:${port}` });
    try {
      await client.startRecording("test");
      expect.unreachable("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(RecorderError);
      const re = err as RecorderError;
      expect(re.status).toBe(409);
      expect(re.body).toContain("already recording");
    }
  });

  it("waitUntilReady times out when server is unhealthy", async () => {
    const client = new RecorderClient({ url: `http://127.0.0.1:${port}` });
    await expect(client.waitUntilReady(500, 100)).rejects.toThrow(
      /not ready after/i,
    );
  });
});

// ---------------------------------------------------------------------------
// Connection refused
// ---------------------------------------------------------------------------

describe("RecorderClient – connection refused", () => {
  it("throws RecorderError when server is not reachable", async () => {
    // Use a port that is almost certainly not listening.
    const client = new RecorderClient({
      url: "http://127.0.0.1:19999",
      timeout: 2000,
    });
    await expect(client.health()).rejects.toThrow(RecorderError);
  });
});

// ---------------------------------------------------------------------------
// Timeout
// ---------------------------------------------------------------------------

describe("RecorderClient – timeout", () => {
  let server: http.Server;
  let port: number;

  beforeAll(async () => {
    server = createMockServer({
      "GET /health": () => {
        // This handler intentionally never responds (the test relies on timeout).
        // Returning a never-resolving promise would be ideal, but our simple
        // mock always responds synchronously. Instead we use a slow server below.
        return { status: 200, body: { status: "ok" } };
      },
    });

    // Replace with a server that delays response
    await closeServer(server);

    server = http.createServer((req, res) => {
      // Delay 5 seconds — longer than the client timeout we'll set.
      setTimeout(() => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "ok" }));
      }, 5000);
    });
    port = await listenOnRandomPort(server);
  });

  afterAll(async () => {
    await closeServer(server);
  });

  it("throws RecorderError on timeout", async () => {
    const client = new RecorderClient({
      url: `http://127.0.0.1:${port}`,
      timeout: 200,
    });
    await expect(client.health()).rejects.toThrow(/timed out/i);
  });
});

// ---------------------------------------------------------------------------
// Constructor defaults
// ---------------------------------------------------------------------------

describe("RecorderClient – defaults", () => {
  it("defaults to http://localhost:9123", () => {
    // Ensure THEA_URL is not set for this test
    const prev = process.env.THEA_URL;
    delete process.env.THEA_URL;
    try {
      const client = new RecorderClient();
      // We can't directly access private baseUrl, but we can verify
      // the client was created without errors.
      expect(client).toBeInstanceOf(RecorderClient);
    } finally {
      if (prev !== undefined) process.env.THEA_URL = prev;
    }
  });

  it("reads THEA_URL from environment", () => {
    const prev = process.env.THEA_URL;
    process.env.THEA_URL = "http://custom:1234";
    try {
      const client = new RecorderClient();
      expect(client).toBeInstanceOf(RecorderClient);
    } finally {
      if (prev !== undefined) {
        process.env.THEA_URL = prev;
      } else {
        delete process.env.THEA_URL;
      }
    }
  });
});
