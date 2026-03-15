// Package thea provides a Go client for the thea-recorder HTTP server.
//
// The client wraps every REST endpoint exposed by the recorder service and
// requires only the standard library (net/http). Every method accepts a
// [context.Context] so callers can control timeouts and cancellation.
package thea

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"strings"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Exported types
// ---------------------------------------------------------------------------

// RecorderError is returned when the server responds with a non-success HTTP
// status code.
type RecorderError struct {
	StatusCode int
	Status     string
	Body       string
}

func (e *RecorderError) Error() string {
	if e.Body != "" {
		return fmt.Sprintf("recorder: %s: %s", e.Status, e.Body)
	}
	return fmt.Sprintf("recorder: %s", e.Status)
}

// Panel describes a terminal panel managed by the recorder.
type Panel struct {
	Name   string `json:"name"`
	Title  string `json:"title,omitempty"`
	Width  int    `json:"width,omitempty"`
	Height int    `json:"height,omitempty"`
	Text   string `json:"text,omitempty"`
}

// AddPanelResult is the payload returned by POST /panels.
type AddPanelResult struct {
	Warnings []string `json:"warnings,omitempty"`
}

// StartRecordingResult is the payload returned by POST /recording/start.
type StartRecordingResult struct {
	Warnings []string `json:"warnings,omitempty"`
}

// LayoutValidation is the payload returned by GET /validate-layout.
type LayoutValidation struct {
	Warnings []string `json:"warnings"`
	Valid    bool     `json:"valid"`
}

// Health is the payload returned by GET /health.
type Health struct {
	Status    string   `json:"status"`
	Recording bool     `json:"recording"`
	Display   string   `json:"display"`
	Panels    []string `json:"panels"`
	Uptime    float64  `json:"uptime"`
}

// RecordingResult is the payload returned by POST /recording/stop.
type RecordingResult struct {
	Path       string            `json:"path"`
	Elapsed    float64           `json:"elapsed"`
	Name       string            `json:"name"`
	GifPath    string            `json:"gif_path,omitempty"`
	ExtraPaths map[string]string `json:"extra_paths,omitempty"`
}

// RecordingStatus is the payload returned by GET /recording/status.
type RecordingStatus struct {
	Recording bool    `json:"recording"`
	Name      string  `json:"name"`
	Elapsed   float64 `json:"elapsed"`
}

// RecordingInfo describes a single recording file.
type RecordingInfo struct {
	Name             string   `json:"name"`
	Path             string   `json:"path"`
	Size             int64    `json:"size"`
	Created          string   `json:"created"`
	GifPath          string   `json:"gif_path,omitempty"`
	GifSize          int64    `json:"gif_size,omitempty"`
	WebmPath         string   `json:"webm_path,omitempty"`
	WebmSize         int64    `json:"webm_size,omitempty"`
	FormatsAvailable []string `json:"formats_available,omitempty"`
}

// CompositionHighlight describes a highlight applied to a recording within a
// composition.
type CompositionHighlight struct {
	Recording string  `json:"recording"`
	Time      float64 `json:"time"`
	Duration  float64 `json:"duration"`
}

// Annotation describes a timestamped annotation on a recording.
type Annotation struct {
	Label   string  `json:"label"`
	Time    float64 `json:"time"`
	Details string  `json:"details,omitempty"`
}

// AddAnnotationRequest is the payload for POST /recording/annotations.
type AddAnnotationRequest struct {
	Label   string   `json:"label"`
	Time    *float64 `json:"time,omitempty"`
	Details string   `json:"details,omitempty"`
}

// Event describes an entry in the session event log.
type Event struct {
	Event   string         `json:"event"`
	Time    string         `json:"time"`
	Elapsed float64        `json:"elapsed"`
	Details map[string]any `json:"details,omitempty"`
}

// MousePos describes the current cursor position.
type MousePos struct {
	X int `json:"x"`
	Y int `json:"y"`
}

// MouseMoveRequest is the payload for POST /director/mouse/move.
type MouseMoveRequest struct {
	X           int      `json:"x"`
	Y           int      `json:"y"`
	Duration    *float64 `json:"duration,omitempty"`
	TargetWidth *float64 `json:"target_width,omitempty"`
}

// MouseClickRequest is the payload for POST /director/mouse/click.
type MouseClickRequest struct {
	X        *int     `json:"x,omitempty"`
	Y        *int     `json:"y,omitempty"`
	Button   int      `json:"button"`
	Duration *float64 `json:"duration,omitempty"`
}

// MouseDragRequest is the payload for POST /director/mouse/drag.
type MouseDragRequest struct {
	StartX   int      `json:"start_x"`
	StartY   int      `json:"start_y"`
	EndX     int      `json:"end_x"`
	EndY     int      `json:"end_y"`
	Button   int      `json:"button"`
	Duration *float64 `json:"duration,omitempty"`
}

// MouseScrollRequest is the payload for POST /director/mouse/scroll.
type MouseScrollRequest struct {
	Clicks int  `json:"clicks"`
	X      *int `json:"x,omitempty"`
	Y      *int `json:"y,omitempty"`
}

// KeyboardTypeRequest is the payload for POST /director/keyboard/type.
type KeyboardTypeRequest struct {
	Text string   `json:"text"`
	WPM  *float64 `json:"wpm,omitempty"`
}

// WindowFindRequest is the payload for POST /director/window/find.
type WindowFindRequest struct {
	Name      string  `json:"name,omitempty"`
	ClassName string  `json:"class,omitempty"`
	Timeout   float64 `json:"timeout"`
}

// WindowInfo is the payload returned by POST /director/window/find.
type WindowInfo struct {
	WindowID string `json:"window_id"`
	Name     string `json:"name,omitempty"`
	Class    string `json:"class,omitempty"`
}

// WindowGeometryInfo is the payload returned by GET /director/window/{id}/geometry.
type WindowGeometryInfo struct {
	X      int `json:"x"`
	Y      int `json:"y"`
	Width  int `json:"width"`
	Height int `json:"height"`
}

// WindowTileRequest is the payload for POST /director/window/tile.
type WindowTileRequest struct {
	WindowIDs []string `json:"window_ids"`
	Layout    string   `json:"layout"`
	Bounds    []int    `json:"bounds,omitempty"`
}

// CompositionRequest is the payload for POST /compositions.
type CompositionRequest struct {
	Name           string                 `json:"name"`
	Recordings     []string               `json:"recordings"`
	Layout         string                 `json:"layout,omitempty"`
	Labels         bool                   `json:"labels"`
	Highlights     []CompositionHighlight `json:"highlights,omitempty"`
	HighlightColor string                 `json:"highlight_color,omitempty"`
	HighlightWidth int                    `json:"highlight_width,omitempty"`
}

// CompositionStatus is the payload returned by composition endpoints.
type CompositionStatus struct {
	Name       string   `json:"name"`
	Status     string   `json:"status"`
	Recordings []string `json:"recordings"`
	OutputPath string   `json:"output_path,omitempty"`
	OutputSize int64    `json:"output_size,omitempty"`
	Error      string   `json:"error,omitempty"`
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

// Client communicates with the thea-recorder HTTP server.
type Client struct {
	baseURL    string
	httpClient *http.Client
	readyOnce  sync.Once
	readyErr   error
}

// NewClient creates a new Client. If baseURL is empty the THEA_URL
// environment variable is used. If that is also empty, "http://localhost:9123"
// is used as the default.
func NewClient(baseURL string) *Client {
	if baseURL == "" {
		baseURL = os.Getenv("THEA_URL")
	}
	if baseURL == "" {
		baseURL = "http://localhost:9123"
	}
	baseURL = strings.TrimRight(baseURL, "/")
	return &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// SetTimeout configures the underlying HTTP client timeout.
func (c *Client) SetTimeout(d time.Duration) {
	c.httpClient.Timeout = d
}

// BaseURL returns the base URL of the recorder server this client targets.
func (c *Client) BaseURL() string {
	return c.baseURL
}

// ---------------------------------------------------------------------------
// Display
// ---------------------------------------------------------------------------

// StartDisplay starts the virtual display (POST /display/start).
// An optional displaySize (e.g. "1920x1080") overrides the server default.
func (c *Client) StartDisplay(ctx context.Context, displaySize ...string) error {
	var body map[string]any
	if len(displaySize) > 0 && displaySize[0] != "" {
		body = map[string]any{"display_size": displaySize[0]}
	}
	return c.doSimple(ctx, http.MethodPost, "/display/start", body, http.StatusCreated)
}

// StopDisplay stops the virtual display (POST /display/stop).
func (c *Client) StopDisplay(ctx context.Context) error {
	return c.doSimple(ctx, http.MethodPost, "/display/stop", nil, http.StatusOK)
}

// DisplayScreenshot captures a JPEG screenshot of the live display
// (GET /display/screenshot?quality=N). Returns the raw JPEG bytes.
func (c *Client) DisplayScreenshot(ctx context.Context, quality int) ([]byte, error) {
	return c.doRawGet(ctx, fmt.Sprintf("/display/screenshot?quality=%d", quality))
}

// DisplayStreamURL returns the URL for the live MJPEG stream. No HTTP call
// is made.
func (c *Client) DisplayStreamURL(fps int) string {
	return fmt.Sprintf("%s/display/stream?fps=%d", c.baseURL, fps)
}

// DisplayViewerURL returns the URL for the HTML live viewer page. No HTTP
// call is made.
func (c *Client) DisplayViewerURL() string {
	return c.baseURL + "/display/view"
}

// ---------------------------------------------------------------------------
// Panels
// ---------------------------------------------------------------------------

// AddPanel creates a new panel (POST /panels).
// Pass nil for height to omit it from the request.
func (c *Client) AddPanel(ctx context.Context, name, title string, width int, height *int) (*AddPanelResult, error) {
	body := map[string]any{"name": name, "title": title, "width": width}
	if height != nil {
		body["height"] = *height
	}
	var result AddPanelResult
	if err := c.doJSON(ctx, http.MethodPost, "/panels", body, http.StatusCreated, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// UpdatePanel updates the content of an existing panel (PUT /panels/{name}).
func (c *Client) UpdatePanel(ctx context.Context, name, text string, focusLine int) error {
	body := map[string]any{"text": text, "focus_line": focusLine}
	return c.doSimple(ctx, http.MethodPut, "/panels/"+name, body, http.StatusOK)
}

// RemovePanel deletes a panel (DELETE /panels/{name}).
func (c *Client) RemovePanel(ctx context.Context, name string) error {
	return c.doSimple(ctx, http.MethodDelete, "/panels/"+name, nil, http.StatusOK)
}

// ListPanels returns all panels (GET /panels).
func (c *Client) ListPanels(ctx context.Context) ([]Panel, error) {
	var panels []Panel
	if err := c.doJSON(ctx, http.MethodGet, "/panels", nil, http.StatusOK, &panels); err != nil {
		return nil, err
	}
	return panels, nil
}

// WithPanel is a scoped helper that creates a panel, calls fn, then removes
// the panel regardless of whether fn returned an error.
func (c *Client) WithPanel(ctx context.Context, name, title string, width int, height *int, fn func() error) error {
	if _, err := c.AddPanel(ctx, name, title, width, height); err != nil {
		return fmt.Errorf("add panel: %w", err)
	}
	defer c.RemovePanel(ctx, name) //nolint:errcheck
	return fn()
}

// ---------------------------------------------------------------------------
// Recording
// ---------------------------------------------------------------------------

// StopRecordingOptions configures additional output formats when stopping.
type StopRecordingOptions struct {
	GIF           bool     `json:"gif,omitempty"`
	GIFFps        int      `json:"gif_fps,omitempty"`
	GIFWidth      int      `json:"gif_width,omitempty"`
	OutputFormats []string `json:"output_formats,omitempty"`
}

// StartRecording begins recording (POST /recording/start).
func (c *Client) StartRecording(ctx context.Context, name string) (*StartRecordingResult, error) {
	body := map[string]any{"name": name}
	var result StartRecordingResult
	if err := c.doJSON(ctx, http.MethodPost, "/recording/start", body, http.StatusCreated, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// StopRecording stops the active recording (POST /recording/stop).
// Optional StopRecordingOptions can request additional output formats (e.g. GIF).
func (c *Client) StopRecording(ctx context.Context, opts ...StopRecordingOptions) (*RecordingResult, error) {
	var body any
	if len(opts) > 0 {
		body = opts[0]
	}
	var result RecordingResult
	if err := c.doJSON(ctx, http.MethodPost, "/recording/stop", body, http.StatusOK, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// ConvertToGIF converts an existing recording to GIF
// (POST /recordings/{name}/gif).
func (c *Client) ConvertToGIF(ctx context.Context, name string, fps, width int) (map[string]any, error) {
	body := map[string]any{"fps": fps, "width": width}
	var result map[string]any
	if err := c.doJSON(ctx, http.MethodPost, "/recordings/"+name+"/gif", body, http.StatusCreated, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// RecordingElapsed returns the elapsed time of the current recording
// (GET /recording/elapsed).
func (c *Client) RecordingElapsed(ctx context.Context) (float64, error) {
	var result struct {
		Elapsed float64 `json:"elapsed"`
	}
	if err := c.doJSON(ctx, http.MethodGet, "/recording/elapsed", nil, http.StatusOK, &result); err != nil {
		return 0, err
	}
	return result.Elapsed, nil
}

// RecordingStatusInfo returns the status of the current recording
// (GET /recording/status).
func (c *Client) RecordingStatusInfo(ctx context.Context) (*RecordingStatus, error) {
	var status RecordingStatus
	if err := c.doJSON(ctx, http.MethodGet, "/recording/status", nil, http.StatusOK, &status); err != nil {
		return nil, err
	}
	return &status, nil
}

// AddAnnotation adds an annotation to the active recording
// (POST /recording/annotations).
func (c *Client) AddAnnotation(ctx context.Context, req AddAnnotationRequest) (*Annotation, error) {
	var ann Annotation
	if err := c.doJSON(ctx, http.MethodPost, "/recording/annotations", req, http.StatusCreated, &ann); err != nil {
		return nil, err
	}
	return &ann, nil
}

// ListAnnotations returns all annotations for the active recording
// (GET /recording/annotations).
func (c *Client) ListAnnotations(ctx context.Context) ([]Annotation, error) {
	var anns []Annotation
	if err := c.doJSON(ctx, http.MethodGet, "/recording/annotations", nil, http.StatusOK, &anns); err != nil {
		return nil, err
	}
	return anns, nil
}

// ListRecordings returns all stored recordings (GET /recordings).
func (c *Client) ListRecordings(ctx context.Context) ([]RecordingInfo, error) {
	var list []RecordingInfo
	if err := c.doJSON(ctx, http.MethodGet, "/recordings", nil, http.StatusOK, &list); err != nil {
		return nil, err
	}
	return list, nil
}

// GetRecordingInfo returns metadata for a single recording
// (GET /recordings/{name}/info).
func (c *Client) GetRecordingInfo(ctx context.Context, name string) (*RecordingInfo, error) {
	var info RecordingInfo
	if err := c.doJSON(ctx, http.MethodGet, "/recordings/"+name+"/info", nil, http.StatusOK, &info); err != nil {
		return nil, err
	}
	return &info, nil
}

// RecordingScreenshot extracts a JPEG frame from a saved recording
// (GET /recordings/{name}/screenshot?t=N&quality=N). Returns the raw JPEG bytes.
func (c *Client) RecordingScreenshot(ctx context.Context, name string, timeOffset float64, quality int) ([]byte, error) {
	path := fmt.Sprintf("/recordings/%s/screenshot?t=%.3f&quality=%d", name, timeOffset, quality)
	return c.doRawGet(ctx, path)
}

// DownloadRecording streams the recording for the named recording into w
// (GET /recordings/{name}).
func (c *Client) DownloadRecording(ctx context.Context, name string, w io.Writer) error {
	if err := c.ensureReady(ctx); err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/recordings/"+name, nil)
	if err != nil {
		return err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		body, _ := io.ReadAll(resp.Body)
		return &RecorderError{StatusCode: resp.StatusCode, Status: resp.Status, Body: string(body)}
	}
	_, err = io.Copy(w, resp.Body)
	return err
}

// DownloadRecordingToFile downloads the named recording to a local file.
func (c *Client) DownloadRecordingToFile(ctx context.Context, name, filePath string) error {
	f, err := os.Create(filePath)
	if err != nil {
		return err
	}
	defer f.Close()
	if err := c.DownloadRecording(ctx, name, f); err != nil {
		os.Remove(filePath)
		return err
	}
	return f.Close()
}

// DownloadRecordingFormat streams a recording in the given format into w
// (GET /recordings/{name}?format=...). Format can be "mp4", "gif", or "webm".
func (c *Client) DownloadRecordingFormat(ctx context.Context, name, format string, w io.Writer) error {
	if err := c.ensureReady(ctx); err != nil {
		return err
	}
	u := fmt.Sprintf("%s/recordings/%s?format=%s", c.baseURL, name, format)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		body, _ := io.ReadAll(resp.Body)
		return &RecorderError{StatusCode: resp.StatusCode, Status: resp.Status, Body: string(body)}
	}
	_, err = io.Copy(w, resp.Body)
	return err
}

// Recording is a context-manager-style helper. It starts a recording and
// returns a stop function. Calling stop (or deferring it) will stop the
// recording and return the result.
//
//	stop, err := client.Recording(ctx, "demo")
//	if err != nil { ... }
//	defer stop()
func (c *Client) Recording(ctx context.Context, name string, opts ...StopRecordingOptions) (stop func() (*RecordingResult, error), err error) {
	if _, err := c.StartRecording(ctx, name); err != nil {
		return nil, err
	}
	return func() (*RecordingResult, error) {
		return c.StopRecording(ctx, opts...)
	}, nil
}

// EnsureRecording starts a recording if one is not already active. If the
// server returns 409 Conflict (already recording), it fetches and returns the
// current recording status instead of failing. This makes the call idempotent.
func (c *Client) EnsureRecording(ctx context.Context, name string) (*RecordingStatus, error) {
	_, err := c.StartRecording(ctx, name)
	if err != nil {
		if !IsConflict(err) {
			return nil, err
		}
		// Already recording — return current status.
	}
	return c.RecordingStatusInfo(ctx)
}

// CreateCompositionAndWait creates a composition and polls until it completes,
// fails, or the timeout elapses. If the composition already exists (409) or
// was accepted for async processing (202), it falls through to polling.
func (c *Client) CreateCompositionAndWait(ctx context.Context, req CompositionRequest, timeout time.Duration) (*CompositionStatus, error) {
	_, err := c.CreateComposition(ctx, req)
	if err != nil {
		if !IsConflict(err) && !IsAccepted(err) {
			return nil, err
		}
		// 409 Conflict: composition already exists — poll it.
		// 202 Accepted: composition created asynchronously — poll it.
	}
	return c.WaitForComposition(ctx, req.Name, timeout)
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

// SessionInfo is returned by session management endpoints.
type SessionInfo struct {
	Name          string `json:"name"`
	Display       int    `json:"display"`
	URLPrefix     string `json:"url_prefix,omitempty"`
	Recording     bool   `json:"recording,omitempty"`
	RecordingName string `json:"recording_name,omitempty"`
}

// CreateSession creates a new named recording session (POST /sessions).
func (c *Client) CreateSession(ctx context.Context, name string, display ...int) (*SessionInfo, error) {
	body := map[string]any{"name": name}
	if len(display) > 0 {
		body["display"] = display[0]
	}
	var info SessionInfo
	if err := c.doJSON(ctx, http.MethodPost, "/sessions", body, http.StatusCreated, &info); err != nil {
		return nil, err
	}
	return &info, nil
}

// UseSession returns a new Client whose requests are scoped to the named
// session. Call with "" to target the default session.
func (c *Client) UseSession(name string) *Client {
	prefix := ""
	if name != "" {
		prefix = "/sessions/" + name
	}
	return &Client{
		baseURL:    c.baseURL + prefix,
		httpClient: c.httpClient,
	}
}

// DeleteSession removes a named session (DELETE /sessions/{name}).
func (c *Client) DeleteSession(ctx context.Context, name string) error {
	return c.doSimple(ctx, http.MethodDelete, "/sessions/"+name, nil, http.StatusOK)
}

// ListSessions returns all active sessions (GET /sessions).
func (c *Client) ListSessions(ctx context.Context) ([]SessionInfo, error) {
	var list []SessionInfo
	if err := c.doJSON(ctx, http.MethodGet, "/sessions", nil, http.StatusOK, &list); err != nil {
		return nil, err
	}
	return list, nil
}

// ---------------------------------------------------------------------------
// Compositions
// ---------------------------------------------------------------------------

// CreateComposition creates a new composition (POST /compositions).
func (c *Client) CreateComposition(ctx context.Context, req CompositionRequest) (*CompositionStatus, error) {
	var status CompositionStatus
	if err := c.doJSON(ctx, http.MethodPost, "/compositions", req, http.StatusCreated, &status); err != nil {
		return nil, err
	}
	return &status, nil
}

// CompositionStatus returns the status of a composition
// (GET /compositions/{name}).
func (c *Client) CompositionStatus(ctx context.Context, name string) (*CompositionStatus, error) {
	var status CompositionStatus
	if err := c.doJSON(ctx, http.MethodGet, "/compositions/"+name, nil, http.StatusOK, &status); err != nil {
		return nil, err
	}
	return &status, nil
}

// ListCompositions returns all compositions (GET /compositions).
func (c *Client) ListCompositions(ctx context.Context) ([]CompositionStatus, error) {
	var list []CompositionStatus
	if err := c.doJSON(ctx, http.MethodGet, "/compositions", nil, http.StatusOK, &list); err != nil {
		return nil, err
	}
	return list, nil
}

// DeleteComposition deletes a composition (DELETE /compositions/{name}).
func (c *Client) DeleteComposition(ctx context.Context, name string) error {
	return c.doSimple(ctx, http.MethodDelete, "/compositions/"+name, nil, http.StatusOK)
}

// AddHighlight adds a highlight to a composition
// (POST /compositions/{name}/highlights).
func (c *Client) AddHighlight(ctx context.Context, compositionName string, h CompositionHighlight) error {
	return c.doSimple(ctx, http.MethodPost, "/compositions/"+compositionName+"/highlights", h, http.StatusCreated)
}

// WaitForComposition polls the composition status until it reaches "complete"
// or "failed", or the timeout elapses.
func (c *Client) WaitForComposition(ctx context.Context, name string, timeout time.Duration) (*CompositionStatus, error) {
	deadline := time.Now().Add(timeout)
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	for {
		status, err := c.CompositionStatus(ctx, name)
		if err != nil {
			return nil, err
		}
		if status.Status == "complete" || status.Status == "failed" {
			return status, nil
		}
		if time.Now().After(deadline) {
			return status, fmt.Errorf("recorder: composition %q not finished after %s (status: %s)", name, timeout, status.Status)
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-ticker.C:
		}
	}
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

// Events returns the event log for the current session (GET /events).
// An optional since value filters to events with elapsed greater than that value.
func (c *Client) Events(ctx context.Context, since ...float64) ([]Event, error) {
	urlPath := "/events"
	if len(since) > 0 {
		urlPath = fmt.Sprintf("/events?since=%g", since[0])
	}
	var events []Event
	// Events endpoint may have query params, use doRawGet + decode.
	if len(since) > 0 {
		data, err := c.doRawGet(ctx, urlPath)
		if err != nil {
			return nil, err
		}
		if err := json.Unmarshal(data, &events); err != nil {
			return nil, err
		}
		return events, nil
	}
	if err := c.doJSON(ctx, http.MethodGet, urlPath, nil, http.StatusOK, &events); err != nil {
		return nil, err
	}
	return events, nil
}

// DashboardURL returns the URL for the HTML dashboard page. No HTTP call
// is made.
func (c *Client) DashboardURL() string {
	return c.baseURL + "/dashboard"
}

// ---------------------------------------------------------------------------
// Layout validation / Testcard
// ---------------------------------------------------------------------------

// ValidateLayout checks whether the current panel layout fits within the
// display (GET /validate-layout).
func (c *Client) ValidateLayout(ctx context.Context) (*LayoutValidation, error) {
	var v LayoutValidation
	if err := c.doJSON(ctx, http.MethodGet, "/validate-layout", nil, http.StatusOK, &v); err != nil {
		return nil, err
	}
	return &v, nil
}

// Testcard returns an SVG test card image for the current display and panel
// layout (GET /testcard).
func (c *Client) Testcard(ctx context.Context) (string, error) {
	if err := c.ensureReady(ctx); err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/testcard", nil)
	if err != nil {
		return "", err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return "", &RecorderError{StatusCode: resp.StatusCode, Status: resp.Status, Body: string(b)}
	}
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// ---------------------------------------------------------------------------
// Health / Cleanup
// ---------------------------------------------------------------------------

// Health returns server health information (GET /health).
func (c *Client) Health(ctx context.Context) (*Health, error) {
	var h Health
	if err := c.doJSON(ctx, http.MethodGet, "/health", nil, http.StatusOK, &h); err != nil {
		return nil, err
	}
	return &h, nil
}

// Cleanup triggers server-side cleanup (POST /cleanup).
func (c *Client) Cleanup(ctx context.Context) error {
	return c.doSimple(ctx, http.MethodPost, "/cleanup", nil, http.StatusOK)
}

// WaitUntilReady polls GET /health until it succeeds or the timeout elapses.
func (c *Client) WaitUntilReady(ctx context.Context, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()

	for {
		reqCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
		_, err := c.Health(reqCtx)
		cancel()
		if err == nil {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("recorder: server not ready after %s: %w", timeout, err)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

// ---------------------------------------------------------------------------
// Director — Mouse
// ---------------------------------------------------------------------------

// MouseMove moves the mouse cursor (POST /director/mouse/move).
func (c *Client) MouseMove(ctx context.Context, req MouseMoveRequest) error {
	return c.doSimple(ctx, http.MethodPost, "/director/mouse/move", req, http.StatusOK)
}

// MouseClick clicks the mouse (POST /director/mouse/click).
func (c *Client) MouseClick(ctx context.Context, req MouseClickRequest) error {
	if req.Button == 0 {
		req.Button = 1
	}
	return c.doSimple(ctx, http.MethodPost, "/director/mouse/click", req, http.StatusOK)
}

// MouseDoubleClick double-clicks the mouse (POST /director/mouse/double-click).
func (c *Client) MouseDoubleClick(ctx context.Context, x, y *int) error {
	body := map[string]any{}
	if x != nil {
		body["x"] = *x
	}
	if y != nil {
		body["y"] = *y
	}
	return c.doSimple(ctx, http.MethodPost, "/director/mouse/double-click", body, http.StatusOK)
}

// MouseRightClick right-clicks the mouse (POST /director/mouse/right-click).
func (c *Client) MouseRightClick(ctx context.Context, x, y *int) error {
	body := map[string]any{}
	if x != nil {
		body["x"] = *x
	}
	if y != nil {
		body["y"] = *y
	}
	return c.doSimple(ctx, http.MethodPost, "/director/mouse/right-click", body, http.StatusOK)
}

// MouseDrag drags from one point to another (POST /director/mouse/drag).
func (c *Client) MouseDrag(ctx context.Context, req MouseDragRequest) error {
	if req.Button == 0 {
		req.Button = 1
	}
	return c.doSimple(ctx, http.MethodPost, "/director/mouse/drag", req, http.StatusOK)
}

// MouseScroll scrolls the mouse wheel (POST /director/mouse/scroll).
func (c *Client) MouseScroll(ctx context.Context, req MouseScrollRequest) error {
	return c.doSimple(ctx, http.MethodPost, "/director/mouse/scroll", req, http.StatusOK)
}

// MousePosition returns the current cursor position
// (GET /director/mouse/position).
func (c *Client) MousePosition(ctx context.Context) (*MousePos, error) {
	var pos MousePos
	if err := c.doJSON(ctx, http.MethodGet, "/director/mouse/position", nil, http.StatusOK, &pos); err != nil {
		return nil, err
	}
	return &pos, nil
}

// ---------------------------------------------------------------------------
// Director — Keyboard
// ---------------------------------------------------------------------------

// KeyboardType types text with human-like rhythm
// (POST /director/keyboard/type).
func (c *Client) KeyboardType(ctx context.Context, req KeyboardTypeRequest) error {
	return c.doSimple(ctx, http.MethodPost, "/director/keyboard/type", req, http.StatusOK)
}

// KeyboardPress presses one or more keys (POST /director/keyboard/press).
func (c *Client) KeyboardPress(ctx context.Context, keys ...string) error {
	body := map[string]any{"keys": keys}
	return c.doSimple(ctx, http.MethodPost, "/director/keyboard/press", body, http.StatusOK)
}

// KeyboardHold holds a key down (POST /director/keyboard/hold).
func (c *Client) KeyboardHold(ctx context.Context, key string) error {
	body := map[string]any{"key": key}
	return c.doSimple(ctx, http.MethodPost, "/director/keyboard/hold", body, http.StatusOK)
}

// KeyboardRelease releases a held key (POST /director/keyboard/release).
func (c *Client) KeyboardRelease(ctx context.Context, key string) error {
	body := map[string]any{"key": key}
	return c.doSimple(ctx, http.MethodPost, "/director/keyboard/release", body, http.StatusOK)
}

// ---------------------------------------------------------------------------
// Director — Window
// ---------------------------------------------------------------------------

// WindowFind finds a window by name or WM_CLASS
// (POST /director/window/find).
func (c *Client) WindowFind(ctx context.Context, req WindowFindRequest) (*WindowInfo, error) {
	if req.Timeout == 0 {
		req.Timeout = 10.0
	}
	var info WindowInfo
	if err := c.doJSON(ctx, http.MethodPost, "/director/window/find", req, http.StatusOK, &info); err != nil {
		return nil, err
	}
	return &info, nil
}

// WindowFocus focuses a window (POST /director/window/{id}/focus).
func (c *Client) WindowFocus(ctx context.Context, windowID string) error {
	return c.doSimple(ctx, http.MethodPost, "/director/window/"+windowID+"/focus", nil, http.StatusOK)
}

// WindowMove moves a window (POST /director/window/{id}/move).
func (c *Client) WindowMove(ctx context.Context, windowID string, x, y int) error {
	body := map[string]any{"x": x, "y": y}
	return c.doSimple(ctx, http.MethodPost, "/director/window/"+windowID+"/move", body, http.StatusOK)
}

// WindowResize resizes a window (POST /director/window/{id}/resize).
func (c *Client) WindowResize(ctx context.Context, windowID string, width, height int) error {
	body := map[string]any{"width": width, "height": height}
	return c.doSimple(ctx, http.MethodPost, "/director/window/"+windowID+"/resize", body, http.StatusOK)
}

// WindowMinimize minimizes a window (POST /director/window/{id}/minimize).
func (c *Client) WindowMinimize(ctx context.Context, windowID string) error {
	return c.doSimple(ctx, http.MethodPost, "/director/window/"+windowID+"/minimize", nil, http.StatusOK)
}

// WindowGeometry returns the geometry of a window
// (GET /director/window/{id}/geometry).
func (c *Client) WindowGeometry(ctx context.Context, windowID string) (*WindowGeometryInfo, error) {
	var geo WindowGeometryInfo
	if err := c.doJSON(ctx, http.MethodGet, "/director/window/"+windowID+"/geometry", nil, http.StatusOK, &geo); err != nil {
		return nil, err
	}
	return &geo, nil
}

// WindowTile tiles windows (POST /director/window/tile).
func (c *Client) WindowTile(ctx context.Context, req WindowTileRequest) error {
	return c.doSimple(ctx, http.MethodPost, "/director/window/tile", req, http.StatusOK)
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

// doRawGet performs a GET request and returns the raw response bytes. It
// constructs the URL directly (no path.Clean) so query strings are preserved.
func (c *Client) doRawGet(ctx context.Context, rawPath string) ([]byte, error) {
	if err := c.ensureReady(ctx); err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+rawPath, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return nil, &RecorderError{StatusCode: resp.StatusCode, Status: resp.Status, Body: string(b)}
	}
	return io.ReadAll(resp.Body)
}

func (c *Client) doSimple(ctx context.Context, method, urlPath string, body any, wantStatus int) error {
	resp, err := c.doRequest(ctx, method, urlPath, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != wantStatus {
		b, _ := io.ReadAll(resp.Body)
		return &RecorderError{StatusCode: resp.StatusCode, Status: resp.Status, Body: string(b)}
	}
	io.Copy(io.Discard, resp.Body) //nolint:errcheck
	return nil
}

func (c *Client) doJSON(ctx context.Context, method, urlPath string, body any, wantStatus int, dest any) error {
	resp, err := c.doRequest(ctx, method, urlPath, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != wantStatus {
		b, _ := io.ReadAll(resp.Body)
		return &RecorderError{StatusCode: resp.StatusCode, Status: resp.Status, Body: string(b)}
	}
	return json.NewDecoder(resp.Body).Decode(dest)
}

func (c *Client) ensureReady(ctx context.Context) error {
	c.readyOnce.Do(func() {
		c.readyErr = c.WaitUntilReady(ctx, 30*time.Second)
	})
	return c.readyErr
}

func (c *Client) doRequest(ctx context.Context, method, urlPath string, body any) (*http.Response, error) {
	// Auto-ready: wait for the server on the first non-health request.
	if urlPath != "/health" {
		if err := c.ensureReady(ctx); err != nil {
			return nil, err
		}
	}
	u := c.baseURL + path.Clean("/"+urlPath)
	var bodyReader io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		bodyReader = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, u, bodyReader)
	if err != nil {
		return nil, err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	return c.httpClient.Do(req)
}
