package thea_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"time"

	"github.com/barkingiguana/thea-recorder/sdks/go/thea"
)

// ExampleNewClient demonstrates creating a client with the default URL.
func ExampleNewClient() {
	client := thea.NewClient("http://localhost:9123")
	fmt.Println(client.BaseURL())
	// Output: http://localhost:9123
}

// ExampleClient_SetTimeout demonstrates configuring the HTTP timeout.
func ExampleClient_SetTimeout() {
	client := thea.NewClient("http://localhost:9123")
	client.SetTimeout(60 * time.Second)
	fmt.Println("timeout configured")
	// Output: timeout configured
}

// ExampleClient_WaitUntilReady shows how to poll until the server is up.
// This example uses a fake server so it completes immediately.
func ExampleClient_WaitUntilReady() {
	// In real usage you would connect to the actual recorder server.
	// Here we use a test server for demonstration.
	ts := fakeServer()
	defer ts.Close()

	client := thea.NewClient(ts.URL)
	err := client.WaitUntilReady(context.Background(), 2*time.Second)
	if err != nil {
		fmt.Println("error:", err)
		return
	}
	fmt.Println("server is ready")
	// Output: server is ready
}

// ExampleClient_Health shows how to check server health.
func ExampleClient_Health() {
	ts := fakeServer()
	defer ts.Close()

	client := thea.NewClient(ts.URL)
	h, err := client.Health(context.Background())
	if err != nil {
		fmt.Println("error:", err)
		return
	}
	fmt.Println("status:", h.Status)
	// Output: status: ok
}

// ExampleClient_Recording shows the context-manager-style recording helper.
func ExampleClient_Recording() {
	ts := fakeServer()
	defer ts.Close()

	client := thea.NewClient(ts.URL)
	ctx := context.Background()

	stop, err := client.Recording(ctx, "my-session")
	if err != nil {
		fmt.Println("error:", err)
		return
	}
	// In real code you would defer stop() and perform actions here.
	result, err := stop()
	if err != nil {
		fmt.Println("error:", err)
		return
	}
	fmt.Println("recorded:", result.Name)
	// Output: recorded: my-session
}

// ExampleClient_WithPanel shows the scoped panel helper.
func ExampleClient_WithPanel() {
	ts := fakeServer()
	defer ts.Close()

	client := thea.NewClient(ts.URL)
	ctx := context.Background()

	err := client.WithPanel(ctx, "code", "Code Panel", 80, func() error {
		panels, err := client.ListPanels(ctx)
		if err != nil {
			return err
		}
		fmt.Println("panels during callback:", len(panels))
		return nil
	})
	if err != nil {
		fmt.Println("error:", err)
		return
	}

	panels, _ := client.ListPanels(ctx)
	fmt.Println("panels after callback:", len(panels))
	// Output:
	// panels during callback: 1
	// panels after callback: 0
}

// ExampleRecorderError shows how to inspect HTTP errors.
func ExampleRecorderError() {
	// Create a server that returns 200 for /health but 500 for everything else.
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"status":"ok"}`)
	})
	mux.HandleFunc("/display/start", func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal error", http.StatusInternalServerError)
	})
	ts := httptest.NewServer(mux)
	defer ts.Close()

	client := thea.NewClient(ts.URL)
	err := client.StartDisplay(context.Background())
	if err != nil {
		fmt.Println("got error:", err != nil)
	}
	// Output: got error: true
}
