package thea_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/barkingiguana/thea-recorder/sdks/go/thea"
)

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

// fakeServer returns an *httptest.Server that mimics the recorder HTTP API.
func fakeServer() *httptest.Server {
	mux := http.NewServeMux()

	// Display
	mux.HandleFunc("/display/start", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusCreated)
	})
	mux.HandleFunc("/display/stop", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})

	// Panels
	var panels []thea.Panel
	var mu sync.Mutex

	mux.HandleFunc("/panels", func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		switch r.Method {
		case http.MethodGet:
			json.NewEncoder(w).Encode(panels)
		case http.MethodPost:
			var p thea.Panel
			json.NewDecoder(r.Body).Decode(&p)
			panels = append(panels, p)
			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(map[string]any{"warnings": []string{}})
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
	mux.HandleFunc("/panels/", func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		name := strings.TrimPrefix(r.URL.Path, "/panels/")
		switch r.Method {
		case http.MethodPut:
			for i := range panels {
				if panels[i].Name == name {
					var body struct {
						Text      string `json:"text"`
						FocusLine int    `json:"focus_line"`
					}
					json.NewDecoder(r.Body).Decode(&body)
					panels[i].Text = body.Text
					w.WriteHeader(http.StatusOK)
					return
				}
			}
			http.Error(w, "not found", http.StatusNotFound)
		case http.MethodDelete:
			for i := range panels {
				if panels[i].Name == name {
					panels = append(panels[:i], panels[i+1:]...)
					w.WriteHeader(http.StatusOK)
					return
				}
			}
			http.Error(w, "not found", http.StatusNotFound)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})

	// Recording
	var recording atomic.Bool
	var recName atomic.Value
	recName.Store("")

	mux.HandleFunc("/recording/start", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body struct {
			Name string `json:"name"`
		}
		json.NewDecoder(r.Body).Decode(&body)
		if recording.Load() {
			http.Error(w, `{"error":"already recording"}`, http.StatusConflict)
			return
		}
		recording.Store(true)
		recName.Store(body.Name)
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(map[string]any{"warnings": []string{}})
	})
	mux.HandleFunc("/recording/stop", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		recording.Store(false)
		name := recName.Load().(string)
		json.NewEncoder(w).Encode(thea.RecordingResult{
			Path:    "/recordings/" + name + ".mp4",
			Elapsed: 5.2,
			Name:    name,
		})
	})
	mux.HandleFunc("/recording/elapsed", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]float64{"elapsed": 3.7})
	})
	mux.HandleFunc("/recording/status", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(thea.RecordingStatus{
			Recording: recording.Load(),
			Name:      recName.Load().(string),
			Elapsed:   3.7,
		})
	})

	// Recordings list & download
	mux.HandleFunc("/recordings", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/recordings" {
			// fall through to /recordings/ handler
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		json.NewEncoder(w).Encode([]thea.RecordingInfo{
			{Name: "demo", Path: "/recordings/demo.mp4", Size: 1024, Created: "2025-01-01T00:00:00Z"},
		})
	})
	mux.HandleFunc("/recordings/", func(w http.ResponseWriter, r *http.Request) {
		rest := strings.TrimPrefix(r.URL.Path, "/recordings/")
		if strings.Contains(rest, "/screenshot") {
			w.Header().Set("Content-Type", "image/jpeg")
			w.Write([]byte("fake-recording-jpeg"))
			return
		}
		if strings.HasSuffix(rest, "/info") {
			name := strings.TrimSuffix(rest, "/info")
			json.NewEncoder(w).Encode(thea.RecordingInfo{
				Name: name, Path: "/recordings/" + name + ".mp4", Size: 1024, Created: "2025-01-01T00:00:00Z",
			})
			return
		}
		// binary download
		w.Header().Set("Content-Type", "video/mp4")
		w.Write([]byte("fake-mp4-data"))
	})

	// Compositions
	var compositions sync.Map // name -> *thea.CompositionStatus

	mux.HandleFunc("/compositions", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/compositions" {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		switch r.Method {
		case http.MethodPost:
			var req thea.CompositionRequest
			json.NewDecoder(r.Body).Decode(&req)
			if _, exists := compositions.Load(req.Name); exists {
				http.Error(w, `{"error":"composition already exists"}`, http.StatusConflict)
				return
			}
			cs := &thea.CompositionStatus{
				Name:       req.Name,
				Status:     "complete",
				Recordings: req.Recordings,
				OutputPath: "/compositions/" + req.Name + ".mp4",
			}
			compositions.Store(req.Name, cs)
			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(cs)
		case http.MethodGet:
			var list []thea.CompositionStatus
			compositions.Range(func(_, v any) bool {
				list = append(list, *v.(*thea.CompositionStatus))
				return true
			})
			if list == nil {
				list = []thea.CompositionStatus{}
			}
			json.NewEncoder(w).Encode(list)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
	mux.HandleFunc("/compositions/", func(w http.ResponseWriter, r *http.Request) {
		name := strings.TrimPrefix(r.URL.Path, "/compositions/")
		name = strings.TrimSuffix(name, "/highlights")
		if strings.Contains(r.URL.Path, "/highlights") {
			if r.Method == http.MethodPost {
				w.WriteHeader(http.StatusCreated)
				return
			}
		}
		switch r.Method {
		case http.MethodGet:
			if v, ok := compositions.Load(name); ok {
				json.NewEncoder(w).Encode(v)
			} else {
				http.Error(w, "not found", http.StatusNotFound)
			}
		case http.MethodDelete:
			compositions.Delete(name)
			w.WriteHeader(http.StatusOK)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})

	// Display screenshot & stream
	mux.HandleFunc("/display/screenshot", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/jpeg")
		w.Write([]byte("fake-jpeg-data"))
	})
	mux.HandleFunc("/display/stream", func(w http.ResponseWriter, r *http.Request) {
		// Not actually called in tests, just registered for completeness.
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/display/view", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	// Annotations
	var annotations []thea.Annotation
	var annMu sync.Mutex

	mux.HandleFunc("/recording/annotations", func(w http.ResponseWriter, r *http.Request) {
		annMu.Lock()
		defer annMu.Unlock()
		switch r.Method {
		case http.MethodPost:
			var req thea.AddAnnotationRequest
			json.NewDecoder(r.Body).Decode(&req)
			ann := thea.Annotation{Label: req.Label, Time: 1.5, Details: req.Details}
			if req.Time != nil {
				ann.Time = *req.Time
			}
			annotations = append(annotations, ann)
			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(ann)
		case http.MethodGet:
			if annotations == nil {
				annotations = []thea.Annotation{}
			}
			json.NewEncoder(w).Encode(annotations)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})

	// Events
	mux.HandleFunc("/events", func(w http.ResponseWriter, r *http.Request) {
		events := []thea.Event{
			{Event: "display_started", Time: "2025-01-01T00:00:00Z", Elapsed: 0.0, Details: map[string]any{"display": ":99"}},
			{Event: "recording_started", Time: "2025-01-01T00:00:01Z", Elapsed: 1.0},
		}
		sinceStr := r.URL.Query().Get("since")
		if sinceStr != "" {
			// Simple filter: return only the second event.
			events = events[1:]
		}
		json.NewEncoder(w).Encode(events)
	})

	// Director — Mouse
	mux.HandleFunc("/director/mouse/move", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/mouse/click", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/mouse/double-click", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/mouse/right-click", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/mouse/drag", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/mouse/scroll", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/mouse/position", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(thea.MousePos{X: 100, Y: 200})
	})

	// Director — Keyboard
	mux.HandleFunc("/director/keyboard/type", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/keyboard/press", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/keyboard/hold", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/keyboard/release", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})

	// Director — Window
	mux.HandleFunc("/director/window/find", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		json.NewEncoder(w).Encode(thea.WindowInfo{WindowID: "12345", Name: "xterm", Class: "XTerm"})
	})
	mux.HandleFunc("/director/window/tile", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/director/window/", func(w http.ResponseWriter, r *http.Request) {
		// Handle /director/window/{id}/focus, /move, /resize, /minimize, /geometry
		rest := strings.TrimPrefix(r.URL.Path, "/director/window/")
		parts := strings.SplitN(rest, "/", 2)
		if len(parts) < 2 {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		action := parts[1]
		switch action {
		case "focus", "move", "resize", "minimize":
			if r.Method != http.MethodPost {
				http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
				return
			}
			w.WriteHeader(http.StatusOK)
		case "geometry":
			if r.Method != http.MethodGet {
				http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
				return
			}
			json.NewEncoder(w).Encode(thea.WindowGeometryInfo{X: 0, Y: 0, Width: 1280, Height: 720})
		default:
			http.Error(w, "not found", http.StatusNotFound)
		}
	})

	// Health
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(thea.Health{
			Status: "ok", Recording: false, Display: ":99", Panels: []string{}, Uptime: 42.5,
		})
	})

	// Cleanup
	mux.HandleFunc("/cleanup", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		w.WriteHeader(http.StatusOK)
	})

	return httptest.NewServer(mux)
}

func newTestClient(ts *httptest.Server) *thea.Client {
	return thea.NewClient(ts.URL)
}

// ---------------------------------------------------------------------------
// Display tests
// ---------------------------------------------------------------------------

func TestStartDisplay(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	if err := c.StartDisplay(context.Background()); err != nil {
		t.Fatalf("StartDisplay: %v", err)
	}
}

func TestStopDisplay(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	if err := c.StopDisplay(context.Background()); err != nil {
		t.Fatalf("StopDisplay: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Panel tests
// ---------------------------------------------------------------------------

func TestPanelLifecycle(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	if _, err := c.AddPanel(ctx, "code", "Code", 80, nil); err != nil {
		t.Fatalf("AddPanel: %v", err)
	}

	if err := c.UpdatePanel(ctx, "code", "hello world", 1); err != nil {
		t.Fatalf("UpdatePanel: %v", err)
	}

	panels, err := c.ListPanels(ctx)
	if err != nil {
		t.Fatalf("ListPanels: %v", err)
	}
	if len(panels) != 1 {
		t.Fatalf("expected 1 panel, got %d", len(panels))
	}
	if panels[0].Name != "code" {
		t.Fatalf("expected panel name 'code', got %q", panels[0].Name)
	}

	if err := c.RemovePanel(ctx, "code"); err != nil {
		t.Fatalf("RemovePanel: %v", err)
	}

	panels, err = c.ListPanels(ctx)
	if err != nil {
		t.Fatalf("ListPanels after remove: %v", err)
	}
	if len(panels) != 0 {
		t.Fatalf("expected 0 panels after remove, got %d", len(panels))
	}
}

func TestWithPanel(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	called := false
	err := c.WithPanel(ctx, "tmp", "Temp", 60, nil, func() error {
		called = true
		panels, err := c.ListPanels(ctx)
		if err != nil {
			return err
		}
		if len(panels) != 1 {
			t.Errorf("expected 1 panel inside WithPanel, got %d", len(panels))
		}
		return nil
	})
	if err != nil {
		t.Fatalf("WithPanel: %v", err)
	}
	if !called {
		t.Fatal("fn was not called")
	}

	// Panel should be removed after WithPanel returns.
	panels, _ := c.ListPanels(ctx)
	if len(panels) != 0 {
		t.Fatalf("expected 0 panels after WithPanel, got %d", len(panels))
	}
}

// ---------------------------------------------------------------------------
// Recording tests
// ---------------------------------------------------------------------------

func TestRecordingLifecycle(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	if _, err := c.StartRecording(ctx, "test-rec"); err != nil {
		t.Fatalf("StartRecording: %v", err)
	}

	elapsed, err := c.RecordingElapsed(ctx)
	if err != nil {
		t.Fatalf("RecordingElapsed: %v", err)
	}
	if elapsed != 3.7 {
		t.Fatalf("expected elapsed 3.7, got %f", elapsed)
	}

	status, err := c.RecordingStatusInfo(ctx)
	if err != nil {
		t.Fatalf("RecordingStatusInfo: %v", err)
	}
	if !status.Recording {
		t.Fatal("expected recording=true")
	}
	if status.Name != "test-rec" {
		t.Fatalf("expected name 'test-rec', got %q", status.Name)
	}

	result, err := c.StopRecording(ctx)
	if err != nil {
		t.Fatalf("StopRecording: %v", err)
	}
	if result.Name != "test-rec" {
		t.Fatalf("expected result name 'test-rec', got %q", result.Name)
	}
	if result.Elapsed != 5.2 {
		t.Fatalf("expected elapsed 5.2, got %f", result.Elapsed)
	}
}

func TestRecordingHelper(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	stop, err := c.Recording(ctx, "helper-rec")
	if err != nil {
		t.Fatalf("Recording: %v", err)
	}

	status, _ := c.RecordingStatusInfo(ctx)
	if !status.Recording {
		t.Fatal("expected recording to be active")
	}

	result, err := stop()
	if err != nil {
		t.Fatalf("stop: %v", err)
	}
	if result.Name != "helper-rec" {
		t.Fatalf("expected 'helper-rec', got %q", result.Name)
	}
}

func TestListRecordings(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	list, err := c.ListRecordings(context.Background())
	if err != nil {
		t.Fatalf("ListRecordings: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("expected 1 recording, got %d", len(list))
	}
	if list[0].Name != "demo" {
		t.Fatalf("expected 'demo', got %q", list[0].Name)
	}
}

func TestGetRecordingInfo(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	info, err := c.GetRecordingInfo(context.Background(), "demo")
	if err != nil {
		t.Fatalf("GetRecordingInfo: %v", err)
	}
	if info.Name != "demo" {
		t.Fatalf("expected 'demo', got %q", info.Name)
	}
	if info.Size != 1024 {
		t.Fatalf("expected size 1024, got %d", info.Size)
	}
}

func TestDownloadRecording(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	var buf bytes.Buffer
	if err := c.DownloadRecording(context.Background(), "demo", &buf); err != nil {
		t.Fatalf("DownloadRecording: %v", err)
	}
	if buf.String() != "fake-mp4-data" {
		t.Fatalf("unexpected body: %q", buf.String())
	}
}

func TestDownloadRecordingToFile(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	tmp, err := os.CreateTemp("", "recording-*.mp4")
	if err != nil {
		t.Fatal(err)
	}
	tmp.Close()
	defer os.Remove(tmp.Name())

	if err := c.DownloadRecordingToFile(context.Background(), "demo", tmp.Name()); err != nil {
		t.Fatalf("DownloadRecordingToFile: %v", err)
	}
	data, err := os.ReadFile(tmp.Name())
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "fake-mp4-data" {
		t.Fatalf("unexpected file content: %q", string(data))
	}
}

// ---------------------------------------------------------------------------
// Health / Cleanup tests
// ---------------------------------------------------------------------------

func TestHealth(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	h, err := c.Health(context.Background())
	if err != nil {
		t.Fatalf("Health: %v", err)
	}
	if h.Status != "ok" {
		t.Fatalf("expected status 'ok', got %q", h.Status)
	}
	if h.Uptime != 42.5 {
		t.Fatalf("expected uptime 42.5, got %f", h.Uptime)
	}
}

func TestCleanup(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	if err := c.Cleanup(context.Background()); err != nil {
		t.Fatalf("Cleanup: %v", err)
	}
}

func TestWaitUntilReady(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	if err := c.WaitUntilReady(context.Background(), 2*time.Second); err != nil {
		t.Fatalf("WaitUntilReady: %v", err)
	}
}

func TestWaitUntilReadyTimeout(t *testing.T) {
	// Server that never responds with success.
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not ready", http.StatusServiceUnavailable)
	}))
	defer ts.Close()
	c := thea.NewClient(ts.URL)

	err := c.WaitUntilReady(context.Background(), 500*time.Millisecond)
	if err == nil {
		t.Fatal("expected timeout error")
	}
	if !strings.Contains(err.Error(), "not ready") {
		t.Fatalf("unexpected error: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Error handling tests
// ---------------------------------------------------------------------------

func TestRecorderError(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"something broke"}`, http.StatusInternalServerError)
	})
	ts := httptest.NewServer(mux)
	defer ts.Close()
	c := thea.NewClient(ts.URL)

	err := c.StartDisplay(context.Background())
	if err == nil {
		t.Fatal("expected error")
	}
	var recErr *thea.RecorderError
	if !errAs(err, &recErr) {
		t.Fatalf("expected RecorderError, got %T: %v", err, err)
	}
	if recErr.StatusCode != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d", recErr.StatusCode)
	}
}

func TestContextCancellation(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(5 * time.Second)
	})
	ts := httptest.NewServer(mux)
	defer ts.Close()
	c := thea.NewClient(ts.URL)
	c.SetTimeout(10 * time.Second)

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	err := c.StartDisplay(ctx)
	if err == nil {
		t.Fatal("expected context error")
	}
}

func TestNewClientEnvFallback(t *testing.T) {
	os.Setenv("THEA_URL", "http://env-host:9999")
	defer os.Unsetenv("THEA_URL")

	c := thea.NewClient("")
	if c.BaseURL() != "http://env-host:9999" {
		t.Fatalf("expected env URL, got %q", c.BaseURL())
	}
}

func TestNewClientDefault(t *testing.T) {
	os.Unsetenv("THEA_URL")
	c := thea.NewClient("")
	if c.BaseURL() != "http://localhost:9123" {
		t.Fatalf("expected default URL, got %q", c.BaseURL())
	}
}

// ---------------------------------------------------------------------------
// Concurrent access test
// ---------------------------------------------------------------------------

func TestConcurrentHealth(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	var wg sync.WaitGroup
	errs := make(chan error, 20)
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := c.Health(context.Background())
			if err != nil {
				errs <- err
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Errorf("concurrent Health error: %v", err)
	}
}

func TestConcurrentPanels(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			name := fmt.Sprintf("panel-%d", n)
			_, _ = c.AddPanel(ctx, name, "Title", 80, nil)
			_, _ = c.ListPanels(ctx)
		}(i)
	}
	wg.Wait()
}

// ---------------------------------------------------------------------------
// Error helper tests
// ---------------------------------------------------------------------------

func TestIsConflict(t *testing.T) {
	err := &thea.RecorderError{StatusCode: http.StatusConflict, Status: "409 Conflict"}
	if !thea.IsConflict(err) {
		t.Fatal("expected IsConflict to return true for 409")
	}
	if thea.IsConflict(&thea.RecorderError{StatusCode: 500}) {
		t.Fatal("expected IsConflict to return false for 500")
	}
	if thea.IsConflict(fmt.Errorf("other error")) {
		t.Fatal("expected IsConflict to return false for non-RecorderError")
	}
}

func TestIsAccepted(t *testing.T) {
	err := &thea.RecorderError{StatusCode: http.StatusAccepted, Status: "202 Accepted"}
	if !thea.IsAccepted(err) {
		t.Fatal("expected IsAccepted to return true for 202")
	}
	if thea.IsAccepted(&thea.RecorderError{StatusCode: 200}) {
		t.Fatal("expected IsAccepted to return false for 200")
	}
}

func TestIsNotFound(t *testing.T) {
	err := &thea.RecorderError{StatusCode: http.StatusNotFound, Status: "404 Not Found"}
	if !thea.IsNotFound(err) {
		t.Fatal("expected IsNotFound to return true for 404")
	}
	if thea.IsNotFound(&thea.RecorderError{StatusCode: 200}) {
		t.Fatal("expected IsNotFound to return false for 200")
	}
}

// ---------------------------------------------------------------------------
// Idempotent helper tests
// ---------------------------------------------------------------------------

func TestEnsureRecording_Fresh(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	status, err := c.EnsureRecording(ctx, "demo")
	if err != nil {
		t.Fatalf("EnsureRecording: %v", err)
	}
	if !status.Recording {
		t.Fatal("expected recording=true")
	}
	if status.Name != "demo" {
		t.Fatalf("expected name 'demo', got %q", status.Name)
	}
}

func TestEnsureRecording_AlreadyRecording(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	// Start a recording first.
	if _, err := c.StartRecording(ctx, "first"); err != nil {
		t.Fatalf("StartRecording: %v", err)
	}

	// EnsureRecording should succeed even though already recording.
	status, err := c.EnsureRecording(ctx, "second")
	if err != nil {
		t.Fatalf("EnsureRecording: %v", err)
	}
	if !status.Recording {
		t.Fatal("expected recording=true")
	}
	// Name should be the original recording, not the new one.
	if status.Name != "first" {
		t.Fatalf("expected name 'first', got %q", status.Name)
	}
}

func TestCreateCompositionAndWait_Fresh(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	req := thea.CompositionRequest{
		Name:       "comp1",
		Recordings: []string{"a", "b"},
	}
	status, err := c.CreateCompositionAndWait(ctx, req, 5*time.Second)
	if err != nil {
		t.Fatalf("CreateCompositionAndWait: %v", err)
	}
	if status.Status != "complete" {
		t.Fatalf("expected status 'complete', got %q", status.Status)
	}
	if status.Name != "comp1" {
		t.Fatalf("expected name 'comp1', got %q", status.Name)
	}
}

func TestCreateCompositionAndWait_AlreadyExists(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	req := thea.CompositionRequest{
		Name:       "comp2",
		Recordings: []string{"a", "b"},
	}

	// Create it first.
	if _, err := c.CreateComposition(ctx, req); err != nil {
		t.Fatalf("CreateComposition: %v", err)
	}

	// CreateCompositionAndWait should handle the 409 and poll.
	status, err := c.CreateCompositionAndWait(ctx, req, 5*time.Second)
	if err != nil {
		t.Fatalf("CreateCompositionAndWait: %v", err)
	}
	if status.Status != "complete" {
		t.Fatalf("expected status 'complete', got %q", status.Status)
	}
}

func TestCreateCompositionAndWait_Accepted(t *testing.T) {
	// Server that returns 202 Accepted for composition creation.
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/compositions", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			http.Error(w, `{"status":"accepted"}`, http.StatusAccepted)
			return
		}
	})
	mux.HandleFunc("/compositions/", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(thea.CompositionStatus{
			Name:   "async-comp",
			Status: "complete",
		})
	})
	ts := httptest.NewServer(mux)
	defer ts.Close()
	c := thea.NewClient(ts.URL)
	ctx := context.Background()

	req := thea.CompositionRequest{
		Name:       "async-comp",
		Recordings: []string{"a", "b"},
	}
	status, err := c.CreateCompositionAndWait(ctx, req, 5*time.Second)
	if err != nil {
		t.Fatalf("CreateCompositionAndWait with 202: %v", err)
	}
	if status.Status != "complete" {
		t.Fatalf("expected status 'complete', got %q", status.Status)
	}
}

// ---------------------------------------------------------------------------
// Display screenshot / URL tests
// ---------------------------------------------------------------------------

func TestDisplayScreenshot(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	data, err := c.DisplayScreenshot(context.Background(), 80)
	if err != nil {
		t.Fatalf("DisplayScreenshot: %v", err)
	}
	if string(data) != "fake-jpeg-data" {
		t.Fatalf("unexpected data: %q", string(data))
	}
}

func TestDisplayStreamURL(t *testing.T) {
	c := thea.NewClient("http://localhost:9123")
	url := c.DisplayStreamURL(10)
	want := "http://localhost:9123/display/stream?fps=10"
	if url != want {
		t.Fatalf("expected %q, got %q", want, url)
	}
}

func TestDisplayViewerURL(t *testing.T) {
	c := thea.NewClient("http://localhost:9123")
	url := c.DisplayViewerURL()
	want := "http://localhost:9123/display/view"
	if url != want {
		t.Fatalf("expected %q, got %q", want, url)
	}
}

// ---------------------------------------------------------------------------
// Annotation tests
// ---------------------------------------------------------------------------

func TestAnnotationLifecycle(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	timeVal := 2.5
	ann, err := c.AddAnnotation(ctx, thea.AddAnnotationRequest{
		Label:   "step_1",
		Time:    &timeVal,
		Details: "first step",
	})
	if err != nil {
		t.Fatalf("AddAnnotation: %v", err)
	}
	if ann.Label != "step_1" {
		t.Fatalf("expected label 'step_1', got %q", ann.Label)
	}
	if ann.Time != 2.5 {
		t.Fatalf("expected time 2.5, got %f", ann.Time)
	}

	anns, err := c.ListAnnotations(ctx)
	if err != nil {
		t.Fatalf("ListAnnotations: %v", err)
	}
	if len(anns) != 1 {
		t.Fatalf("expected 1 annotation, got %d", len(anns))
	}
}

// ---------------------------------------------------------------------------
// Events tests
// ---------------------------------------------------------------------------

func TestEvents(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	events, err := c.Events(ctx)
	if err != nil {
		t.Fatalf("Events: %v", err)
	}
	if len(events) != 2 {
		t.Fatalf("expected 2 events, got %d", len(events))
	}
	if events[0].Event != "display_started" {
		t.Fatalf("expected 'display_started', got %q", events[0].Event)
	}
}

func TestEventsSince(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)
	ctx := context.Background()

	events, err := c.Events(ctx, 0.5)
	if err != nil {
		t.Fatalf("Events(since): %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].Event != "recording_started" {
		t.Fatalf("expected 'recording_started', got %q", events[0].Event)
	}
}

func TestDashboardURL(t *testing.T) {
	c := thea.NewClient("http://localhost:9123")
	url := c.DashboardURL()
	want := "http://localhost:9123/dashboard"
	if url != want {
		t.Fatalf("expected %q, got %q", want, url)
	}
}

// ---------------------------------------------------------------------------
// Recording screenshot tests
// ---------------------------------------------------------------------------

func TestRecordingScreenshot(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	data, err := c.RecordingScreenshot(context.Background(), "demo", 1.5, 80)
	if err != nil {
		t.Fatalf("RecordingScreenshot: %v", err)
	}
	if string(data) != "fake-recording-jpeg" {
		t.Fatalf("unexpected data: %q", string(data))
	}
}

// ---------------------------------------------------------------------------
// Director — Mouse tests
// ---------------------------------------------------------------------------

func TestMouseMove(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.MouseMove(context.Background(), thea.MouseMoveRequest{X: 100, Y: 200})
	if err != nil {
		t.Fatalf("MouseMove: %v", err)
	}
}

func TestMouseClick(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.MouseClick(context.Background(), thea.MouseClickRequest{Button: 1})
	if err != nil {
		t.Fatalf("MouseClick: %v", err)
	}
}

func TestMouseDoubleClick(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	x, y := 50, 60
	err := c.MouseDoubleClick(context.Background(), &x, &y)
	if err != nil {
		t.Fatalf("MouseDoubleClick: %v", err)
	}
}

func TestMouseRightClick(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.MouseRightClick(context.Background(), nil, nil)
	if err != nil {
		t.Fatalf("MouseRightClick: %v", err)
	}
}

func TestMouseDrag(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.MouseDrag(context.Background(), thea.MouseDragRequest{
		StartX: 10, StartY: 20, EndX: 300, EndY: 400,
	})
	if err != nil {
		t.Fatalf("MouseDrag: %v", err)
	}
}

func TestMouseScroll(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.MouseScroll(context.Background(), thea.MouseScrollRequest{Clicks: 3})
	if err != nil {
		t.Fatalf("MouseScroll: %v", err)
	}
}

func TestMousePosition(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	pos, err := c.MousePosition(context.Background())
	if err != nil {
		t.Fatalf("MousePosition: %v", err)
	}
	if pos.X != 100 || pos.Y != 200 {
		t.Fatalf("expected (100,200), got (%d,%d)", pos.X, pos.Y)
	}
}

// ---------------------------------------------------------------------------
// Director — Keyboard tests
// ---------------------------------------------------------------------------

func TestKeyboardType(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.KeyboardType(context.Background(), thea.KeyboardTypeRequest{Text: "hello"})
	if err != nil {
		t.Fatalf("KeyboardType: %v", err)
	}
}

func TestKeyboardPress(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.KeyboardPress(context.Background(), "Return", "Tab")
	if err != nil {
		t.Fatalf("KeyboardPress: %v", err)
	}
}

func TestKeyboardHold(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.KeyboardHold(context.Background(), "Shift_L")
	if err != nil {
		t.Fatalf("KeyboardHold: %v", err)
	}
}

func TestKeyboardRelease(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.KeyboardRelease(context.Background(), "Shift_L")
	if err != nil {
		t.Fatalf("KeyboardRelease: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Director — Window tests
// ---------------------------------------------------------------------------

func TestWindowFind(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	info, err := c.WindowFind(context.Background(), thea.WindowFindRequest{Name: "xterm"})
	if err != nil {
		t.Fatalf("WindowFind: %v", err)
	}
	if info.WindowID != "12345" {
		t.Fatalf("expected window_id '12345', got %q", info.WindowID)
	}
	if info.Name != "xterm" {
		t.Fatalf("expected name 'xterm', got %q", info.Name)
	}
}

func TestWindowFocus(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.WindowFocus(context.Background(), "12345")
	if err != nil {
		t.Fatalf("WindowFocus: %v", err)
	}
}

func TestWindowMove(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.WindowMove(context.Background(), "12345", 100, 200)
	if err != nil {
		t.Fatalf("WindowMove: %v", err)
	}
}

func TestWindowResize(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.WindowResize(context.Background(), "12345", 1280, 720)
	if err != nil {
		t.Fatalf("WindowResize: %v", err)
	}
}

func TestWindowMinimize(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.WindowMinimize(context.Background(), "12345")
	if err != nil {
		t.Fatalf("WindowMinimize: %v", err)
	}
}

func TestWindowGeometry(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	geo, err := c.WindowGeometry(context.Background(), "12345")
	if err != nil {
		t.Fatalf("WindowGeometry: %v", err)
	}
	if geo.Width != 1280 || geo.Height != 720 {
		t.Fatalf("expected 1280x720, got %dx%d", geo.Width, geo.Height)
	}
}

func TestWindowTile(t *testing.T) {
	ts := fakeServer()
	defer ts.Close()
	c := newTestClient(ts)

	err := c.WindowTile(context.Background(), thea.WindowTileRequest{
		WindowIDs: []string{"12345", "67890"},
		Layout:    "side-by-side",
	})
	if err != nil {
		t.Fatalf("WindowTile: %v", err)
	}
}

// errAs is a helper to avoid importing errors package in test.
func errAs(err error, target any) bool {
	if e, ok := err.(*thea.RecorderError); ok {
		if p, ok2 := target.(**thea.RecorderError); ok2 {
			*p = e
			return true
		}
	}
	return false
}

