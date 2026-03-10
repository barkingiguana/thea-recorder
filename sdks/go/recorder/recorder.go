// Package recorder provides a Go client for the thea-recorder HTTP server.
//
// The client wraps every REST endpoint exposed by the recorder service and
// requires only the standard library (net/http). Every method accepts a
// [context.Context] so callers can control timeouts and cancellation.
package recorder

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
	Name  string `json:"name"`
	Title string `json:"title,omitempty"`
	Width int    `json:"width,omitempty"`
	Text  string `json:"text,omitempty"`
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
	Path    string  `json:"path"`
	Elapsed float64 `json:"elapsed"`
	Name    string  `json:"name"`
}

// RecordingStatus is the payload returned by GET /recording/status.
type RecordingStatus struct {
	Recording bool    `json:"recording"`
	Name      string  `json:"name"`
	Elapsed   float64 `json:"elapsed"`
}

// RecordingInfo describes a single recording file.
type RecordingInfo struct {
	Name    string  `json:"name"`
	Path    string  `json:"path"`
	Size    int64   `json:"size"`
	Created string  `json:"created"`
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

// Client communicates with the thea-recorder HTTP server.
type Client struct {
	baseURL    string
	httpClient *http.Client
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
func (c *Client) StartDisplay(ctx context.Context) error {
	return c.doSimple(ctx, http.MethodPost, "/display/start", nil, http.StatusCreated)
}

// StopDisplay stops the virtual display (POST /display/stop).
func (c *Client) StopDisplay(ctx context.Context) error {
	return c.doSimple(ctx, http.MethodPost, "/display/stop", nil, http.StatusOK)
}

// ---------------------------------------------------------------------------
// Panels
// ---------------------------------------------------------------------------

// AddPanel creates a new panel (POST /panels).
func (c *Client) AddPanel(ctx context.Context, name, title string, width int) error {
	body := map[string]any{"name": name, "title": title, "width": width}
	return c.doSimple(ctx, http.MethodPost, "/panels", body, http.StatusCreated)
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
func (c *Client) WithPanel(ctx context.Context, name, title string, width int, fn func() error) error {
	if err := c.AddPanel(ctx, name, title, width); err != nil {
		return fmt.Errorf("add panel: %w", err)
	}
	defer c.RemovePanel(ctx, name) //nolint:errcheck
	return fn()
}

// ---------------------------------------------------------------------------
// Recording
// ---------------------------------------------------------------------------

// StartRecording begins recording (POST /recording/start).
func (c *Client) StartRecording(ctx context.Context, name string) error {
	body := map[string]any{"name": name}
	return c.doSimple(ctx, http.MethodPost, "/recording/start", body, http.StatusCreated)
}

// StopRecording stops the active recording (POST /recording/stop).
func (c *Client) StopRecording(ctx context.Context) (*RecordingResult, error) {
	var result RecordingResult
	if err := c.doJSON(ctx, http.MethodPost, "/recording/stop", nil, http.StatusOK, &result); err != nil {
		return nil, err
	}
	return &result, nil
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

// DownloadRecording streams the MP4 for the named recording into w
// (GET /recordings/{name}).
func (c *Client) DownloadRecording(ctx context.Context, name string, w io.Writer) error {
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

// Recording is a context-manager-style helper. It starts a recording and
// returns a stop function. Calling stop (or deferring it) will stop the
// recording and return the result.
//
//	stop, err := client.Recording(ctx, "demo")
//	if err != nil { ... }
//	defer stop()
func (c *Client) Recording(ctx context.Context, name string) (stop func() (*RecordingResult, error), err error) {
	if err := c.StartRecording(ctx, name); err != nil {
		return nil, err
	}
	return func() (*RecordingResult, error) {
		return c.StopRecording(ctx)
	}, nil
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
// Internal helpers
// ---------------------------------------------------------------------------

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

func (c *Client) doRequest(ctx context.Context, method, urlPath string, body any) (*http.Response, error) {
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
