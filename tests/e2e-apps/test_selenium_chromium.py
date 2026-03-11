"""E2E test: record a Chromium browser driven by Selenium.

Demonstrates that Thea can record browser-based applications. Selenium
controls Chromium, Chromium draws on Thea's Xvfb display, and ffmpeg
captures the result.

Everything runs in one container — Thea, Xvfb, Chromium, and the test
code must all be co-located because Thea records a local virtual display.
"""

import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from conftest import FIXTURES_DIR


def test_record_selenium_chromium(recorder, output_dir):
    """Record Chromium navigating a page and clicking a button."""
    # Set up a panel to show what the test is doing
    recorder.add_panel("test", title="Selenium Test", width=300)
    recorder.add_panel("log", title="Browser Log")

    recorder.update_panel("test", "Starting Chromium...")

    # Configure Chrome to run on Thea's display.
    # No need to set DISPLAY manually — it's inherited from the environment
    # because Thea's start_display() sets it, and Chrome runs in the same
    # container.
    options = Options()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--force-device-scale-factor=1")

    # Set DISPLAY so Chrome draws on Thea's virtual screen
    os.environ["DISPLAY"] = recorder.display_string

    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)

    try:
        recorder.start_recording("selenium-chromium")
        recorder.update_panel("test", "Chromium started\nNavigating to test page...")

        # Load the local test page
        test_page = os.path.join(FIXTURES_DIR, "test_page.html")
        driver.get(f"file://{test_page}")
        time.sleep(1)

        recorder.update_panel("log", f"Page title: {driver.title}")
        recorder.update_panel("test", "Page loaded\nClicking button...")

        # Click the button 3 times
        button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "increment"))
        )
        for i in range(3):
            button.click()
            time.sleep(0.5)
            counter = driver.find_element(By.ID, "counter").text
            recorder.update_panel("log", f"Page title: {driver.title}\nCounter: {counter}")
            recorder.update_panel("test", f"Click {i + 1}/3\nCounter = {counter}")

        # Wait for "Test complete!" to appear
        WebDriverWait(driver, 5).until(
            EC.text_to_be_present_in_element((By.ID, "result"), "Test complete!")
        )
        recorder.update_panel("test", "All clicks done\nTest complete!")
        time.sleep(1)

        video_path = recorder.stop_recording()
    finally:
        driver.quit()

    # Verify the recording was created
    assert video_path is not None
    assert os.path.exists(video_path)
    assert os.path.getsize(video_path) > 0
    print(f"Selenium recording saved: {video_path} ({os.path.getsize(video_path)} bytes)")
