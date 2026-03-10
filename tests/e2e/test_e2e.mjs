// E2E test for the Node.js SDK against a live recorder server.

import { RecorderClient } from "./dist/index.js";

const url = process.env.RECORDER_URL || "http://localhost:9123";
const client = new RecorderClient({ url });

async function main() {
  console.log("[node] Waiting for server...");
  await client.waitUntilReady(30_000);

  console.log("[node] Starting display...");
  await client.startDisplay();

  console.log("[node] Health check...");
  const health = await client.health();
  assert(health.status === "ok", `expected ok, got ${health.status}`);
  console.log(`[node] Health: status=${health.status} display=${health.display}`);

  console.log("[node] Adding panel...");
  await client.addPanel({ name: "editor", title: "Code Editor", width: 80 });

  console.log("[node] Updating panel...");
  await client.updatePanel("editor", {
    text: "console.log('hello from Node')",
    focus_line: 1,
  });

  console.log("[node] Listing panels...");
  const panels = await client.listPanels();
  assert(panels.length === 1, `expected 1 panel, got ${panels.length}`);
  assert(panels[0].name === "editor", `expected editor, got ${panels[0].name}`);

  console.log("[node] Starting recording...");
  await client.startRecording("node-e2e-test");

  await sleep(2000);

  console.log("[node] Checking recording status...");
  const status = await client.recordingStatus();
  assert(status.recording === true, `expected recording=true`);

  console.log("[node] Stopping recording...");
  const result = await client.stopRecording();
  assert(result.path, "expected non-empty path");
  console.log(
    `[node] Recording saved: ${result.path} (${result.elapsed.toFixed(1)}s)`
  );

  console.log("[node] Removing panel...");
  await client.removePanel("editor");

  console.log("[node] Listing recordings...");
  const recordings = await client.listRecordings();
  assert(recordings.length >= 1, `expected >= 1 recording`);

  console.log("[node] Stopping display...");
  await client.stopDisplay();

  console.log("[node] Cleanup...");
  await client.cleanup();

  console.log("[node] ALL PASSED");
}

function assert(cond, msg) {
  if (!cond) {
    console.error(`[node] ASSERTION FAILED: ${msg}`);
    process.exit(1);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((err) => {
  console.error(`[node] FAIL: ${err.message}`);
  process.exit(1);
});
