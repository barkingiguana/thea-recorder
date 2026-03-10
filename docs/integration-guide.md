# Test Framework Integration Guide

How to integrate the recorder into your existing test framework. Each example shows the complete setup: start server, record scenarios, update panels during steps, download recordings, and generate reports.

## Architecture

```
┌──────────────┐     HTTP      ┌──────────────────┐
│  Test Suite   │ ──────────── │  Recorder Server  │
│  (any lang)   │   SDK calls  │  (thea serve) │
└──────────────┘               └──────┬───────────┘
                                      │
                               ┌──────┴───────────┐
                               │  Xvfb + ffmpeg    │
                               │  Panel overlays   │
                               └──────┬───────────┘
                                      │
                               ┌──────┴───────────┐
                               │  MP4 files +      │
                               │  HTML report      │
                               └──────────────────┘
```

Your test suite connects to the server via an SDK. The server manages the virtual display and recording. Videos and reports are written to the output directory.

## Prerequisites

Start the server before your tests run:

```bash
thea serve --port 9123 --output-dir ./recordings --display 99
```

Or in Docker:

```yaml
services:
  recorder:
    image: my-recorder-image
    command: thea serve --port 9123 --output-dir /recordings
    shm_size: "2g"
    volumes:
      - ./recordings:/recordings
```

## Go (godog)

```go
package e2e

import (
    "context"
    "fmt"
    "time"

    "github.com/cucumber/godog"
    recorder "github.com/barkingiguana/thea-recorder/sdks/go/recorder"
)

var (
    client     *recorder.Client
    stepEvents []StepEvent
)

func InitializeTestSuite(ctx *godog.TestSuiteContext) {
    ctx.BeforeSuite(func() {
        client = recorder.NewClient("http://localhost:9123")
        c := context.Background()
        client.WaitUntilReady(c, 30*time.Second)
        client.StartDisplay(c)
        client.AddPanel(c, "status", "Status", intPtr(120))
        client.AddPanel(c, "scenario", "Scenario", nil)
    })

    ctx.AfterSuite(func() {
        client.Cleanup(context.Background())
    })
}

func InitializeScenario(ctx *godog.ScenarioContext) {
    ctx.Before(func(ctx context.Context, sc *godog.Scenario) (context.Context, error) {
        stepEvents = nil
        client.UpdatePanel(ctx, "status", "Running", -1)
        client.StartRecording(ctx, sc.Name)
        return ctx, nil
    })

    ctx.StepContext().Before(func(ctx context.Context, st *godog.Step) (context.Context, error) {
        stepEvents = append(stepEvents, StepEvent{Keyword: st.Text, Status: "running"})
        renderScenarioPanel()
        return ctx, nil
    })

    ctx.StepContext().After(func(ctx context.Context, st *godog.Step, status godog.StepResultStatus, err error) (context.Context, error) {
        if len(stepEvents) > 0 {
            stepEvents[len(stepEvents)-1].Status = "passed"
            if err != nil {
                stepEvents[len(stepEvents)-1].Status = "failed"
            }
        }
        renderScenarioPanel()
        return ctx, nil
    })

    ctx.After(func(ctx context.Context, sc *godog.Scenario, err error) (context.Context, error) {
        result, _ := client.StopRecording(ctx)
        fmt.Printf("Video: %s (%.1fs)\n", result.Path, result.Elapsed)
        return ctx, nil
    })
}
```

## Python (Behave)

```python
# features/environment.py
import os
from thea import RecorderClient

client = RecorderClient(os.environ.get("THEA_URL", "http://localhost:9123"))

def before_all(context):
    client.wait_until_ready(timeout=30)
    client.start_display()
    client.add_panel("status", title="Status", width=120)
    client.add_panel("scenario", title="Scenario")
    context.recorded_videos = []

def before_scenario(context, scenario):
    client.update_panel("status", "Running")
    client.start_recording(scenario.name)
    context._step_events = []

def before_step(context, step):
    context._step_events.append({"keyword": step.keyword, "name": step.name, "status": "running"})
    _render_steps(context)

def after_step(context, step):
    if context._step_events:
        context._step_events[-1]["status"] = step.status.name
    _render_steps(context)

def after_scenario(context, scenario):
    result = client.stop_recording()
    context.recorded_videos.append({
        "feature": scenario.feature.name,
        "scenario": scenario.name,
        "status": scenario.status.name,
        "video": result["path"],
    })

def after_all(context):
    client.cleanup()

def _render_steps(context):
    lines = []
    for ev in context._step_events:
        marker = "*" if ev["status"] == "running" else " "
        lines.append(f" {marker} {ev['keyword']} {ev['name']}")
    client.update_panel("scenario", "\n".join(lines))
```

## Python (pytest)

```python
# conftest.py
import pytest
from thea import RecorderClient

@pytest.fixture(scope="session")
def recorder():
    client = RecorderClient("http://localhost:9123")
    client.wait_until_ready(timeout=30)
    client.start_display()
    client.add_panel("status", title="Status", width=120)
    yield client
    client.cleanup()

@pytest.fixture(autouse=True)
def record_test(request, recorder):
    with recorder.recording(request.node.name):
        recorder.update_panel("status", "Running")
        yield
        recorder.update_panel("status", "Done")
```

## Ruby (Cucumber)

```ruby
# features/support/env.rb
require "recorder"

$recorder = Recorder::Client.new(ENV.fetch("THEA_URL", "http://localhost:9123"))
$recorder.wait_until_ready(timeout: 30)
$recorder.start_display
$recorder.add_panel("status", title: "Status", width: 120)
$recorder.add_panel("scenario", title: "Scenario")

Before do |scenario|
  $recorder.update_panel("status", text: "Running")
  $recorder.start_recording(scenario.name)
  @step_events = []
end

AfterStep do |result, step|
  @step_events << { keyword: step.keyword, name: step.name, status: result.passed? ? "passed" : "failed" }
  lines = @step_events.map { |e| " #{e[:status] == 'running' ? '*' : ' '} #{e[:keyword]} #{e[:name]}" }
  $recorder.update_panel("scenario", text: lines.join("\n"))
end

After do |scenario|
  $recorder.update_panel("status", text: scenario.passed? ? "PASSED" : "FAILED")
  $recorder.stop_recording
end

at_exit do
  $recorder.cleanup
end
```

## Node (Playwright + Jest)

```typescript
// tests/global-setup.ts
import { RecorderClient } from "thea-recorder";

const client = new RecorderClient("http://localhost:9123");

export default async function globalSetup() {
  await client.waitUntilReady(30_000);
  await client.startDisplay();
  await client.addPanel("status", "Status", 120);
}

export async function globalTeardown() {
  await client.cleanup();
}

// tests/login.test.ts
import { test } from "@playwright/test";
import { RecorderClient } from "thea-recorder";

const client = new RecorderClient("http://localhost:9123");

test.beforeEach(async ({}, testInfo) => {
  await client.startRecording(testInfo.title);
  await client.updatePanel("status", "Running");
});

test.afterEach(async ({}, testInfo) => {
  await client.updatePanel("status", testInfo.status === "passed" ? "PASSED" : "FAILED");
  const result = await client.stopRecording();
  console.log(`Video: ${result.path}`);
});

test("login flow", async ({ page }) => {
  await page.goto("http://localhost:3000/login");
  await page.fill("#email", "user@example.com");
  await page.fill("#password", "password");
  await page.click("button[type=submit]");
  await page.waitForURL("**/dashboard");
});
```

## Java (JUnit 5)

```java
import com.recorder.RecorderClient;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.*;

public class E2EExtension implements BeforeAllCallback, AfterAllCallback,
        BeforeEachCallback, AfterEachCallback {

    private static RecorderClient client;

    @Override
    public void beforeAll(ExtensionContext ctx) throws Exception {
        client = new RecorderClient("http://localhost:9123");
        client.waitUntilReady(java.time.Duration.ofSeconds(30));
        client.startDisplay();
        client.addPanel("status", "Status", 120);
        client.addPanel("scenario", "Scenario", null);
    }

    @Override
    public void beforeEach(ExtensionContext ctx) throws Exception {
        client.updatePanel("status", "Running", -1);
        client.startRecording(ctx.getDisplayName());
    }

    @Override
    public void afterEach(ExtensionContext ctx) throws Exception {
        String status = ctx.getExecutionException().isEmpty() ? "PASSED" : "FAILED";
        client.updatePanel("status", status, -1);
        var result = client.stopRecording();
        System.out.println("Video: " + result.path());
    }

    @Override
    public void afterAll(ExtensionContext ctx) throws Exception {
        client.cleanup();
    }
}

// Usage:
@ExtendWith(E2EExtension.class)
class LoginTest {
    @Test
    void successfulLogin() {
        // ... Selenium test code ...
    }
}
```

## Tips

- **Always call `wait_until_ready()`** in your setup hook. The server may take a moment to start, especially in Docker.
- **Use the `recording()` helper** instead of manual start/stop — it handles cleanup on test failure.
- **Update panels in step hooks** for the best video debugging experience.
- **Set `--shm-size=2g`** or higher in Docker — Chrome and Xvfb need shared memory.
- **Mount a volume** for the recordings directory so you can access videos after the container exits.
