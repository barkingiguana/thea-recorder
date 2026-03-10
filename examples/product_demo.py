"""Product demo orchestration with thea-recorder.

Records a scripted walkthrough of a web application and produces a
polished MP4 — no test framework required.  Run this from a CI pipeline
or a developer's laptop to generate a fresh demo video on demand.

Requirements:
  - thea serve running  (thea serve --port 9123 --output-dir ./recordings)
  - Selenium or Playwright installed in your environment
  - Browser configured to use DISPLAY=:99 (the display managed by thea)
"""

import os
import time

# pip install thea-recorder   (or: from sdks/python)
from thea import RecorderClient

RECORDER_URL = os.environ.get("RECORDER_URL", "http://localhost:9123")

# ── Connect ───────────────────────────────────────────────────────────────

client = RecorderClient(RECORDER_URL)
client.wait_until_ready(timeout=30)

# ── Set up overlay panels ─────────────────────────────────────────────────

client.start_display()
client.add_panel("scene",  title="Scene",    width=260)
client.add_panel("action", title="Action")

# ── Helper: narrate what's happening on screen ────────────────────────────

def narrate(scene: str, action: str):
    client.update_panel("scene",  scene)
    client.update_panel("action", action)


# ── Record the demo ───────────────────────────────────────────────────────

with client.recording("product_demo_v2") as result:
    # In a real script you'd launch a browser here, e.g.:
    #   from selenium import webdriver
    #   driver = webdriver.Chrome()          # DISPLAY=:99 set in environment
    #   driver.maximize_window()

    narrate("Login", "Navigating to the login page")
    time.sleep(1.5)  # replace with: driver.get("https://app.example.com/login")

    narrate("Login", "Entering credentials")
    time.sleep(1.0)  # replace with: driver.find_element(...).send_keys(...)

    narrate("Dashboard", "Dashboard loaded — showing key metrics")
    time.sleep(2.0)

    narrate("Dashboard → Reports", "Opening the monthly report")
    time.sleep(1.5)

    narrate("Reports", "Filtering by date range: last 30 days")
    time.sleep(1.0)

    narrate("Reports", "Exporting PDF…")
    time.sleep(2.0)

    narrate("Done", "Demo complete")
    time.sleep(0.5)

print(f"Demo video: {result.path}  ({result.elapsed:.1f}s)")

# ── Teardown ──────────────────────────────────────────────────────────────

client.cleanup()
