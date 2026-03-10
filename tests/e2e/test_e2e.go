package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/barkingiguana/thea-recorder/sdks/go/thea"
)

func main() {
	url := os.Getenv("THEA_URL")
	if url == "" {
		url = "http://localhost:9123"
	}

	ctx := context.Background()
	client := thea.NewClient(url)

	fmt.Println("[go] Waiting for server...")
	if err := client.WaitUntilReady(ctx, 30*time.Second); err != nil {
		fatal("WaitUntilReady", err)
	}

	fmt.Println("[go] Starting display...")
	if err := client.StartDisplay(ctx); err != nil {
		fatal("StartDisplay", err)
	}

	fmt.Println("[go] Health check...")
	health, err := client.Health(ctx)
	if err != nil {
		fatal("Health", err)
	}
	assertCond(health.Status == "ok", "health.Status == ok, got %q", health.Status)
	fmt.Printf("[go] Health: status=%s display=%s\n", health.Status, health.Display)

	fmt.Println("[go] Adding panel...")
	if err := client.AddPanel(ctx, "editor", "Code Editor", 80); err != nil {
		fatal("AddPanel", err)
	}

	fmt.Println("[go] Updating panel...")
	if err := client.UpdatePanel(ctx, "editor", "fmt.Println(\"hello from Go\")", 1); err != nil {
		fatal("UpdatePanel", err)
	}

	fmt.Println("[go] Listing panels...")
	panels, err := client.ListPanels(ctx)
	if err != nil {
		fatal("ListPanels", err)
	}
	assertCond(len(panels) == 1, "expected 1 panel, got %d", len(panels))
	assertCond(panels[0].Name == "editor", "panel name == editor, got %q", panels[0].Name)

	fmt.Println("[go] Starting recording...")
	if err := client.StartRecording(ctx, "go-e2e-test"); err != nil {
		fatal("StartRecording", err)
	}

	time.Sleep(2 * time.Second)

	fmt.Println("[go] Checking recording status...")
	status, err := client.RecordingStatus(ctx)
	if err != nil {
		fatal("RecordingStatus", err)
	}
	assertCond(status.Recording, "expected recording=true")

	fmt.Println("[go] Stopping recording...")
	result, err := client.StopRecording(ctx)
	if err != nil {
		fatal("StopRecording", err)
	}
	assertCond(result.Path != "", "expected non-empty recording path")
	fmt.Printf("[go] Recording saved: %s (%.1fs)\n", result.Path, result.Elapsed)

	fmt.Println("[go] Removing panel...")
	if err := client.RemovePanel(ctx, "editor"); err != nil {
		fatal("RemovePanel", err)
	}

	fmt.Println("[go] Listing recordings...")
	recordings, err := client.ListRecordings(ctx)
	if err != nil {
		fatal("ListRecordings", err)
	}
	assertCond(len(recordings) >= 1, "expected at least 1 recording, got %d", len(recordings))

	fmt.Println("[go] Stopping display...")
	if err := client.StopDisplay(ctx); err != nil {
		fatal("StopDisplay", err)
	}

	fmt.Println("[go] Cleanup...")
	if err := client.Cleanup(ctx); err != nil {
		fatal("Cleanup", err)
	}

	fmt.Println("[go] ALL PASSED")
}

func fatal(op string, err error) {
	fmt.Fprintf(os.Stderr, "[go] FAIL %s: %v\n", op, err)
	os.Exit(1)
}

func assertCond(cond bool, msg string, args ...any) {
	if !cond {
		fmt.Fprintf(os.Stderr, "[go] ASSERTION FAILED: "+msg+"\n", args...)
		os.Exit(1)
	}
}
