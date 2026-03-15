/**
 * Node.js/TypeScript SDK for the thea-recorder HTTP server.
 *
 * Uses the built-in Node 18+ fetch API — zero runtime dependencies.
 */

import { writeFile } from "node:fs/promises";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Options for constructing a {@link RecorderClient}. */
export interface RecorderClientOptions {
  /** Base URL of the recorder server. */
  url?: string;
  /** Request timeout in milliseconds (default 30 000). */
  timeout?: number;
}

/** Body for POST /panels. */
export interface AddPanelRequest {
  name: string;
  title: string;
  width?: number;
  height?: number;
}

/** Response from POST /panels. */
export interface AddPanelResponse {
  warnings?: string[];
}

/** Response from POST /recording/start. */
export interface StartRecordingResponse {
  warnings?: string[];
}

/** Response from GET /validate-layout. */
export interface ValidateLayoutResponse {
  warnings: string[];
  valid: boolean;
}

/** Body for PUT /panels/{name}. */
export interface UpdatePanelRequest {
  text: string;
  focus_line?: number;
}

/** Body for POST /recording/start. */
export interface StartRecordingRequest {
  name: string;
}

/** Response from POST /recording/stop. */
export interface StopRecordingResponse {
  path: string;
  elapsed: number;
  name: string;
  gif_path?: string;
  extra_paths?: Record<string, string>;
}

/** Options for stopping a recording with additional output formats. */
export interface StopRecordingOptions {
  /** Also produce a GIF version. */
  gif?: boolean;
  /** GIF frame rate (default 10). */
  gif_fps?: number;
  /** GIF width in pixels (default 720). */
  gif_width?: number;
  /** Additional output formats to produce (e.g. ["gif", "webm"]). */
  output_formats?: string[];
}

/** Response from GET /recording/elapsed. */
export interface RecordingElapsedResponse {
  elapsed: number;
}

/** Response from GET /recording/status. */
export interface RecordingStatusResponse {
  recording: boolean;
  name: string;
  elapsed: number;
}

/** A single recording entry returned by GET /recordings. */
export interface RecordingInfo {
  name: string;
  path: string;
  size: number;
  created: string;
  gif_path?: string;
  gif_size?: number;
  webm_path?: string;
  webm_size?: number;
  formats_available?: string[];
}

/** Response from GET /health. */
export interface HealthResponse {
  status: string;
  recording: boolean;
  display: boolean;
  panels: number;
  uptime: number;
}

/** A highlight within a composition. */
export interface CompositionHighlight {
  recording: string;
  time: number;
  duration?: number;
}

/** Body for POST /compositions. */
export interface CreateCompositionRequest {
  name: string;
  recordings: string[];
  layout?: "row" | "column" | "grid";
  labels?: boolean;
  highlights?: CompositionHighlight[];
  highlight_color?: string;
  highlight_width?: number;
}

/** An annotation on a recording. */
export interface Annotation {
  label: string;
  time: number;
  details?: string;
}

/** An event from the event log. */
export interface Event {
  event: string;
  time: string;
  elapsed: number;
  details?: Record<string, unknown>;
}

/** Window information returned by windowFind. */
export interface WindowInfo {
  window_id: string;
  name?: string;
  class?: string;
}

/** Window geometry returned by windowGeometry. */
export interface WindowGeometry {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Mouse position returned by mousePosition. */
export interface MousePosition {
  x: number;
  y: number;
}

/** Response from composition endpoints. */
export interface CompositionStatus {
  name: string;
  status: "pending" | "rendering" | "complete" | "failed";
  recordings: string[];
  output_path?: string;
  output_size?: number;
  error?: string;
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

/** Error thrown by the SDK on non-success HTTP responses or network issues. */
export class RecorderError extends Error {
  /** HTTP status code, if available. */
  public readonly status?: number;
  /** Response body text, if available. */
  public readonly body?: string;

  constructor(message: string, status?: number, body?: string) {
    super(message);
    this.name = "RecorderError";
    this.status = status;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

const DEFAULT_URL = "http://localhost:9123";
const DEFAULT_TIMEOUT = 30_000;

export class RecorderClient {
  private readonly baseUrl: string;
  private readonly timeout: number;
  private readyPromise: Promise<void> | null = null;

  constructor(options?: RecorderClientOptions) {
    const envUrl =
      typeof process !== "undefined" ? process.env.THEA_URL : undefined;
    this.baseUrl = (options?.url ?? envUrl ?? DEFAULT_URL).replace(/\/+$/, "");
    this.timeout = options?.timeout ?? DEFAULT_TIMEOUT;
  }

  // -----------------------------------------------------------------------
  // Internal helpers
  // -----------------------------------------------------------------------

  private async ensureReady(): Promise<void> {
    if (!this.readyPromise) {
      this.readyPromise = this.waitUntilReady();
    }
    return this.readyPromise;
  }

  private async request<T = unknown>(
    method: string,
    path: string,
    body?: unknown,
    raw?: false,
  ): Promise<T>;
  private async request(
    method: string,
    path: string,
    body: unknown,
    raw: true,
  ): Promise<Response>;
  private async request<T = unknown>(
    method: string,
    path: string,
    body?: unknown,
    raw?: boolean,
  ): Promise<T | Response> {
    if (path !== "/health") {
      await this.ensureReady();
    }
    const url = `${this.baseUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    const headers: Record<string, string> = {};
    let reqBody: string | undefined;
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      reqBody = JSON.stringify(body);
    }

    let res: Response;
    try {
      res = await fetch(url, {
        method,
        headers,
        body: reqBody,
        signal: controller.signal,
      });
    } catch (err: unknown) {
      clearTimeout(timer);
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new RecorderError(`Request timed out: ${method} ${path}`);
      }
      const msg =
        err instanceof Error ? err.message : "Unknown network error";
      throw new RecorderError(`Request failed: ${msg}`);
    } finally {
      clearTimeout(timer);
    }

    if (raw) {
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new RecorderError(
          `${method} ${path} returned ${res.status}`,
          res.status,
          text,
        );
      }
      return res;
    }

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new RecorderError(
        `${method} ${path} returned ${res.status}`,
        res.status,
        text,
      );
    }

    const text = await res.text();
    if (text.length === 0) {
      return {} as T;
    }
    const contentType = res.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      return JSON.parse(text) as T;
    }
    return {} as T;
  }

  // -----------------------------------------------------------------------
  // Display
  // -----------------------------------------------------------------------

  /** Start the virtual display (POST /display/start). */
  async startDisplay(displaySize?: string): Promise<void> {
    const body = displaySize ? { display_size: displaySize } : undefined;
    await this.request("POST", "/display/start", body);
  }

  /** Stop the virtual display (POST /display/stop). */
  async stopDisplay(): Promise<void> {
    await this.request("POST", "/display/stop");
  }

  /** Capture a JPEG screenshot of the live display (GET /display/screenshot). */
  async displayScreenshot(quality = 80): Promise<Buffer> {
    const res = await this.request(
      "GET",
      `/display/screenshot?quality=${quality}`,
      undefined,
      true,
    );
    return Buffer.from(await res.arrayBuffer());
  }

  /** Return the URL for the live MJPEG stream (no HTTP call). */
  displayStreamUrl(fps = 5): string {
    return `${this.baseUrl}/display/stream?fps=${fps}`;
  }

  /** Return the URL for the HTML live viewer page (no HTTP call). */
  displayViewerUrl(): string {
    return `${this.baseUrl}/display/view`;
  }

  // -----------------------------------------------------------------------
  // Panels
  // -----------------------------------------------------------------------

  /** Create a panel (POST /panels). */
  async addPanel(panel: AddPanelRequest): Promise<AddPanelResponse> {
    return this.request<AddPanelResponse>("POST", "/panels", panel);
  }

  /** Update a panel's content (PUT /panels/{name}). */
  async updatePanel(name: string, update: UpdatePanelRequest): Promise<void> {
    await this.request("PUT", `/panels/${encodeURIComponent(name)}`, update);
  }

  /** Remove a panel (DELETE /panels/{name}). */
  async removePanel(name: string): Promise<void> {
    await this.request("DELETE", `/panels/${encodeURIComponent(name)}`);
  }

  /** List all panels (GET /panels). */
  async listPanels(): Promise<unknown[]> {
    return this.request<unknown[]>("GET", "/panels");
  }

  // -----------------------------------------------------------------------
  // Recording
  // -----------------------------------------------------------------------

  /** Start recording (POST /recording/start). */
  async startRecording(name: string): Promise<StartRecordingResponse> {
    return this.request<StartRecordingResponse>("POST", "/recording/start", { name });
  }

  /** Stop recording (POST /recording/stop). */
  async stopRecording(options?: StopRecordingOptions): Promise<StopRecordingResponse> {
    return this.request<StopRecordingResponse>("POST", "/recording/stop", options);
  }

  /** Convert an existing recording to GIF (POST /recordings/{name}/gif). */
  async convertToGif(
    name: string,
    options?: { fps?: number; width?: number },
  ): Promise<{ name: string; gif_path: string; gif_size: number }> {
    return this.request("POST", `/recordings/${encodeURIComponent(name)}/gif`, {
      fps: options?.fps ?? 10,
      width: options?.width ?? 720,
    });
  }

  /** Get elapsed recording time (GET /recording/elapsed). */
  async recordingElapsed(): Promise<RecordingElapsedResponse> {
    return this.request<RecordingElapsedResponse>("GET", "/recording/elapsed");
  }

  /** Get recording status (GET /recording/status). */
  async recordingStatus(): Promise<RecordingStatusResponse> {
    return this.request<RecordingStatusResponse>("GET", "/recording/status");
  }

  /** Add an annotation to the active recording (POST /recording/annotations). */
  async addAnnotation(
    label: string,
    options?: { time?: number; details?: string },
  ): Promise<Annotation> {
    const body: Record<string, unknown> = { label };
    if (options?.time !== undefined) body.time = options.time;
    if (options?.details !== undefined) body.details = options.details;
    return this.request<Annotation>("POST", "/recording/annotations", body);
  }

  /** List annotations for the active recording (GET /recording/annotations). */
  async listAnnotations(): Promise<Annotation[]> {
    return this.request<Annotation[]>("GET", "/recording/annotations");
  }

  // -----------------------------------------------------------------------
  // Recordings collection
  // -----------------------------------------------------------------------

  /** List all recordings (GET /recordings). */
  async listRecordings(): Promise<RecordingInfo[]> {
    return this.request<RecordingInfo[]>("GET", "/recordings");
  }

  /**
   * Download a recording as a ReadableStream (GET /recordings/{name}).
   *
   * Returns the raw {@link Response} body stream.
   */
  async downloadRecording(
    name: string,
    format?: string,
  ): Promise<ReadableStream<Uint8Array>> {
    const query = format && format !== "mp4" ? `?format=${format}` : "";
    const res = await this.request(
      "GET",
      `/recordings/${encodeURIComponent(name)}${query}`,
      undefined,
      true,
    );
    if (!res.body) {
      throw new RecorderError("Response body is null");
    }
    return res.body;
  }

  /**
   * Download a recording and write it to a local file.
   */
  async downloadRecordingToFile(
    name: string,
    destPath: string,
    format?: string,
  ): Promise<void> {
    const query = format && format !== "mp4" ? `?format=${format}` : "";
    const res = await this.request(
      "GET",
      `/recordings/${encodeURIComponent(name)}${query}`,
      undefined,
      true,
    );
    const buf = Buffer.from(await res.arrayBuffer());
    await writeFile(destPath, buf);
  }

  /** Get info for a specific recording (GET /recordings/{name}/info). */
  async recordingInfo(name: string): Promise<RecordingInfo> {
    return this.request<RecordingInfo>(
      "GET",
      `/recordings/${encodeURIComponent(name)}/info`,
    );
  }

  /** Extract a JPEG frame from a saved recording (GET /recordings/{name}/screenshot). */
  async recordingScreenshot(
    name: string,
    timeOffset: number,
    quality = 80,
  ): Promise<Buffer> {
    const params = `?t=${timeOffset.toFixed(3)}&quality=${quality}`;
    const res = await this.request(
      "GET",
      `/recordings/${encodeURIComponent(name)}/screenshot${params}`,
      undefined,
      true,
    );
    return Buffer.from(await res.arrayBuffer());
  }

  // -----------------------------------------------------------------------
  // Events
  // -----------------------------------------------------------------------

  /** Return the event log for the current session (GET /events). */
  async events(since?: number): Promise<Event[]> {
    const path = since !== undefined ? `/events?since=${since}` : "/events";
    return this.request<Event[]>("GET", path);
  }

  /** Return the URL for the HTML dashboard page (no HTTP call). */
  dashboardUrl(): string {
    return `${this.baseUrl}/dashboard`;
  }

  // -----------------------------------------------------------------------
  // Sessions
  // -----------------------------------------------------------------------

  /** Create a named session (POST /sessions). */
  async createSession(
    name: string,
    display?: number,
  ): Promise<{ name: string; display: number; url_prefix: string }> {
    const body: Record<string, unknown> = { name };
    if (display !== undefined) body.display = display;
    return this.request("POST", "/sessions", body);
  }

  /**
   * Return a new client whose requests are scoped to the named session.
   * Pass an empty string to target the default session.
   */
  useSession(name: string): RecorderClient {
    const prefix = name ? `/sessions/${encodeURIComponent(name)}` : "";
    const child = new RecorderClient({
      url: `${this.baseUrl}${prefix}`,
      timeout: this.timeout,
    });
    // Skip readiness check — parent already verified.
    child.readyPromise = Promise.resolve();
    return child;
  }

  /** Delete a named session (DELETE /sessions/{name}). */
  async deleteSession(name: string): Promise<void> {
    await this.request("DELETE", `/sessions/${encodeURIComponent(name)}`);
  }

  /** List all sessions (GET /sessions). */
  async listSessions(): Promise<unknown[]> {
    return this.request<unknown[]>("GET", "/sessions");
  }

  // -----------------------------------------------------------------------
  // Compositions
  // -----------------------------------------------------------------------

  /** Create a composition (POST /compositions). */
  async createComposition(
    req: CreateCompositionRequest,
  ): Promise<CompositionStatus> {
    return this.request<CompositionStatus>("POST", "/compositions", req);
  }

  /** Get composition status (GET /compositions/{name}). */
  async compositionStatus(name: string): Promise<CompositionStatus> {
    return this.request<CompositionStatus>(
      "GET",
      `/compositions/${encodeURIComponent(name)}`,
    );
  }

  /** List all compositions (GET /compositions). */
  async listCompositions(): Promise<CompositionStatus[]> {
    return this.request<CompositionStatus[]>("GET", "/compositions");
  }

  /** Delete a composition (DELETE /compositions/{name}). */
  async deleteComposition(name: string): Promise<void> {
    await this.request(
      "DELETE",
      `/compositions/${encodeURIComponent(name)}`,
    );
  }

  /** Add a highlight to a composition (POST /compositions/{name}/highlights). */
  async addHighlight(
    compositionName: string,
    highlight: CompositionHighlight,
  ): Promise<void> {
    await this.request(
      "POST",
      `/compositions/${encodeURIComponent(compositionName)}/highlights`,
      highlight,
    );
  }

  /**
   * Poll composition status until complete or failed, or timeout expires.
   *
   * @param name Composition name.
   * @param options.timeout Max wait time in milliseconds (default 300 000).
   * @param options.interval Poll interval in milliseconds (default 1 000).
   */
  async waitForComposition(
    name: string,
    options?: { timeout?: number; interval?: number },
  ): Promise<CompositionStatus> {
    const timeout = options?.timeout ?? 300_000;
    const interval = options?.interval ?? 1_000;
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const status = await this.compositionStatus(name);
      if (status.status === "complete" || status.status === "failed") {
        return status;
      }
      await new Promise((r) => setTimeout(r, interval));
    }
    throw new RecorderError(
      `Composition "${name}" not ready after ${timeout}ms`,
    );
  }

  // -----------------------------------------------------------------------
  // Director — Mouse
  // -----------------------------------------------------------------------

  /** Move the mouse cursor (POST /director/mouse/move). */
  async mouseMove(
    x: number,
    y: number,
    options?: { duration?: number; targetWidth?: number },
  ): Promise<void> {
    const body: Record<string, unknown> = { x, y };
    if (options?.duration !== undefined) body.duration = options.duration;
    if (options?.targetWidth !== undefined) body.target_width = options.targetWidth;
    await this.request("POST", "/director/mouse/move", body);
  }

  /** Click the mouse (POST /director/mouse/click). */
  async mouseClick(options?: {
    x?: number;
    y?: number;
    button?: number;
    duration?: number;
  }): Promise<void> {
    const body: Record<string, unknown> = {};
    if (options?.x !== undefined) body.x = options.x;
    if (options?.y !== undefined) body.y = options.y;
    if (options?.button !== undefined) body.button = options.button;
    if (options?.duration !== undefined) body.duration = options.duration;
    await this.request("POST", "/director/mouse/click", body);
  }

  /** Double-click the mouse (POST /director/mouse/double-click). */
  async mouseDoubleClick(x?: number, y?: number): Promise<void> {
    const body: Record<string, unknown> = {};
    if (x !== undefined) body.x = x;
    if (y !== undefined) body.y = y;
    await this.request("POST", "/director/mouse/double-click", body);
  }

  /** Right-click the mouse (POST /director/mouse/right-click). */
  async mouseRightClick(x?: number, y?: number): Promise<void> {
    const body: Record<string, unknown> = {};
    if (x !== undefined) body.x = x;
    if (y !== undefined) body.y = y;
    await this.request("POST", "/director/mouse/right-click", body);
  }

  /** Drag from one point to another (POST /director/mouse/drag). */
  async mouseDrag(
    startX: number,
    startY: number,
    endX: number,
    endY: number,
    options?: { button?: number; duration?: number },
  ): Promise<void> {
    const body: Record<string, unknown> = {
      start_x: startX,
      start_y: startY,
      end_x: endX,
      end_y: endY,
    };
    if (options?.button !== undefined) body.button = options.button;
    if (options?.duration !== undefined) body.duration = options.duration;
    await this.request("POST", "/director/mouse/drag", body);
  }

  /** Scroll the mouse wheel (POST /director/mouse/scroll). */
  async mouseScroll(clicks: number, x?: number, y?: number): Promise<void> {
    const body: Record<string, unknown> = { clicks };
    if (x !== undefined) body.x = x;
    if (y !== undefined) body.y = y;
    await this.request("POST", "/director/mouse/scroll", body);
  }

  /** Get cursor position (GET /director/mouse/position). */
  async mousePosition(): Promise<MousePosition> {
    return this.request<MousePosition>("GET", "/director/mouse/position");
  }

  // -----------------------------------------------------------------------
  // Director — Keyboard
  // -----------------------------------------------------------------------

  /** Type text with human-like rhythm (POST /director/keyboard/type). */
  async keyboardType(text: string, wpm?: number): Promise<void> {
    const body: Record<string, unknown> = { text };
    if (wpm !== undefined) body.wpm = wpm;
    await this.request("POST", "/director/keyboard/type", body);
  }

  /** Press key(s) (POST /director/keyboard/press). */
  async keyboardPress(...keys: string[]): Promise<void> {
    await this.request("POST", "/director/keyboard/press", { keys });
  }

  /** Hold a key down (POST /director/keyboard/hold). */
  async keyboardHold(key: string): Promise<void> {
    await this.request("POST", "/director/keyboard/hold", { key });
  }

  /** Release a held key (POST /director/keyboard/release). */
  async keyboardRelease(key: string): Promise<void> {
    await this.request("POST", "/director/keyboard/release", { key });
  }

  // -----------------------------------------------------------------------
  // Director — Window
  // -----------------------------------------------------------------------

  /** Find a window by name or WM_CLASS (POST /director/window/find). */
  async windowFind(options: {
    name?: string;
    className?: string;
    timeout?: number;
  }): Promise<WindowInfo> {
    const body: Record<string, unknown> = {};
    if (options.name !== undefined) body.name = options.name;
    if (options.className !== undefined) body.class = options.className;
    if (options.timeout !== undefined) body.timeout = options.timeout;
    return this.request<WindowInfo>("POST", "/director/window/find", body);
  }

  /** Focus a window (POST /director/window/{id}/focus). */
  async windowFocus(windowId: string): Promise<void> {
    await this.request(
      "POST",
      `/director/window/${encodeURIComponent(windowId)}/focus`,
    );
  }

  /** Move a window (POST /director/window/{id}/move). */
  async windowMove(windowId: string, x: number, y: number): Promise<void> {
    await this.request(
      "POST",
      `/director/window/${encodeURIComponent(windowId)}/move`,
      { x, y },
    );
  }

  /** Resize a window (POST /director/window/{id}/resize). */
  async windowResize(
    windowId: string,
    width: number,
    height: number,
  ): Promise<void> {
    await this.request(
      "POST",
      `/director/window/${encodeURIComponent(windowId)}/resize`,
      { width, height },
    );
  }

  /** Minimize a window (POST /director/window/{id}/minimize). */
  async windowMinimize(windowId: string): Promise<void> {
    await this.request(
      "POST",
      `/director/window/${encodeURIComponent(windowId)}/minimize`,
    );
  }

  /** Get window geometry (GET /director/window/{id}/geometry). */
  async windowGeometry(windowId: string): Promise<WindowGeometry> {
    return this.request<WindowGeometry>(
      "GET",
      `/director/window/${encodeURIComponent(windowId)}/geometry`,
    );
  }

  /** Tile windows (POST /director/window/tile). */
  async windowTile(
    windowIds: string[],
    layout?: string,
    bounds?: number[],
  ): Promise<void> {
    const body: Record<string, unknown> = { window_ids: windowIds };
    if (layout !== undefined) body.layout = layout;
    if (bounds !== undefined) body.bounds = bounds;
    await this.request("POST", "/director/window/tile", body);
  }

  // -----------------------------------------------------------------------
  // Health / cleanup
  // -----------------------------------------------------------------------

  /** Health check (GET /health). */
  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("GET", "/health");
  }

  /** Validate the current panel layout (GET /validate-layout). */
  async validateLayout(): Promise<ValidateLayoutResponse> {
    return this.request<ValidateLayoutResponse>("GET", "/validate-layout");
  }

  /** Get an SVG test card for the current display (GET /testcard). */
  async testcard(): Promise<string> {
    const res = await this.request("GET", "/testcard", undefined, true);
    return res.text();
  }

  /** Clean up resources (POST /cleanup). */
  async cleanup(): Promise<void> {
    await this.request("POST", "/cleanup");
  }

  // -----------------------------------------------------------------------
  // High-level helpers
  // -----------------------------------------------------------------------

  /**
   * Start a recording, execute `fn`, then stop the recording.
   *
   * The recording is stopped even if `fn` throws.
   */
  async recording(
    name: string,
    fn: () => Promise<void>,
    options?: StopRecordingOptions,
  ): Promise<StopRecordingResponse> {
    await this.startRecording(name);
    let fnError: unknown;
    try {
      await fn();
    } catch (err) {
      fnError = err;
    }
    const result = await this.stopRecording(options);
    if (fnError !== undefined) {
      throw fnError;
    }
    return result;
  }

  /**
   * Create a panel, execute `fn`, then remove the panel.
   *
   * The panel is removed even if `fn` throws.
   */
  async withPanel(
    name: string,
    title: string,
    width?: number,
    height?: number | (() => Promise<void>),
    fn?: () => Promise<void>,
  ): Promise<void> {
    // Support both (name, title, width, fn) and (name, title, width, height, fn).
    let actualHeight: number | undefined;
    let actualFn: () => Promise<void>;
    if (typeof height === "function") {
      actualFn = height;
      actualHeight = undefined;
    } else {
      actualHeight = height;
      actualFn = fn!;
    }
    await this.addPanel({ name, title, width, height: actualHeight });
    try {
      await actualFn();
    } finally {
      await this.removePanel(name).catch(() => {
        /* best-effort removal */
      });
    }
  }

  /**
   * Poll `/health` until the server is ready or timeout expires.
   *
   * @param timeout Max wait time in milliseconds (default 10 000).
   * @param interval Poll interval in milliseconds (default 250).
   */
  async waitUntilReady(timeout = 10_000, interval = 250): Promise<void> {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      try {
        await this.health();
        return;
      } catch {
        // Not ready yet — wait and retry.
        await new Promise((r) => setTimeout(r, interval));
      }
    }
    throw new RecorderError(
      `Server not ready after ${timeout}ms`,
    );
  }
}
