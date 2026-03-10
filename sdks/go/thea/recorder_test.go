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

