"""E2E test: record a GUI application (Gnumeric spreadsheet).

Demonstrates that Thea can record any X11 GUI application, not just
browsers or terminals. Gnumeric is a lightweight spreadsheet app that
draws its own windows — Thea simply captures whatever appears on the
Xvfb display.

The test drives Gnumeric via xdotool keyboard input: navigating cells,
typing values and formulas, and saving the file. This shows that any
GUI app can be recorded and driven programmatically — Thea doesn't
need app-specific knowledge.

Everything runs in one container — Thea, Xvfb, and the application
being recorded must all be co-located because Thea records a local
virtual display.
"""

import os
import shutil
import subprocess
import time

from conftest import FIXTURES_DIR


class VirtualKeyboard:
    """Sends keystrokes and text to an X11 window via xdotool.

    Uses windowfocus + unfocused key/type sends (no --window flag)
    because many X11 applications ignore XSendEvent-based input.

    Args:
        env: Environment dict with DISPLAY set.
        type_delay_ms: Delay between keystrokes when typing text.
        key_pause: Seconds to pause after each key press.
    """

    def __init__(self, env, type_delay_ms=50, key_pause=0.2):
        self._env = env
        self._type_delay_ms = type_delay_ms
        self._key_pause = key_pause

    def _xdotool(self, *args):
        return subprocess.run(
            ["xdotool", *args],
            env=self._env,
            capture_output=True,
            text=True,
        )

    def type(self, text):
        """Type text character by character."""
        self._xdotool(
            "type", "--clearmodifiers",
            "--delay", str(self._type_delay_ms),
            text,
        )

    def key(self, *keys):
        """Send one or more key presses (e.g. 'Return', 'ctrl+s')."""
        for k in keys:
            self._xdotool("key", "--clearmodifiers", k)
            time.sleep(self._key_pause)

    def focus_window(self, window_id):
        """Activate and focus a window by ID."""
        self._xdotool("windowactivate", "--sync", window_id)
        self._xdotool("windowfocus", "--sync", window_id)
        time.sleep(0.5)

    def find_and_focus(self, name, timeout=10):
        """Wait for a window matching `name`, focus it, return its ID."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self._xdotool("search", "--name", name)
            if result.returncode == 0 and result.stdout.strip():
                wid = result.stdout.strip().split("\n")[0]
                self.focus_window(wid)
                return wid
            time.sleep(0.5)
        raise RuntimeError(f"Window matching '{name}' not found within {timeout}s")


def test_record_gnumeric(recorder, output_dir):
    """Record Gnumeric: fill a column with a formula, add totals, save."""
    recorder.add_panel("test", title="GUI App Test", width=300)
    recorder.add_panel("info", title="Activity")

    recorder.update_panel("test", "Launching Gnumeric...")

    # Work on a copy so we can verify the saved file
    csv_src = os.path.join(FIXTURES_DIR, "test_spreadsheet.csv")
    work_path = os.path.join(output_dir, "working_spreadsheet.csv")
    shutil.copy2(csv_src, work_path)

    gnumeric_proc = recorder.launch_app(
        ["gnumeric", "--no-splash", work_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    kb = VirtualKeyboard(recorder.display_env)
    wid = kb.find_and_focus("Gnumeric")

    recorder.update_panel("test", f"Gnumeric running\nWindow ID: {wid}")
    time.sleep(1)

    recorder.start_recording("gnumeric-spreadsheet")
    recorder.update_panel("info", "Opened test_spreadsheet.csv\nwith monthly revenue data")
    time.sleep(1)

    # --- Step 1: Navigate to E1 and add a "Margin %" header ---
    recorder.update_panel("info", "Step 1: Add column header\n\nNavigating to cell E1")

    # Click on the Name Box (cell reference area) and type a cell address
    # This is more reliable than arrow keys
    kb.key("ctrl+Home")
    time.sleep(0.5)

    # Navigate right to column E
    kb.key("Right", "Right", "Right", "Right")
    time.sleep(0.5)

    kb.type("Margin %")
    kb.key("Return")
    time.sleep(0.5)

    # --- Step 2: Enter margin formulas in E2:E7 ---
    recorder.update_panel("info", "Step 2: Enter formulas\n\nCalculating profit margin\n=D/B*100 for each month")

    for row in range(2, 8):
        formula = f"=D{row}/B{row}*100"
        kb.type(formula)
        kb.key("Return")
        time.sleep(0.3)
        recorder.update_panel("info", f"Step 2: Enter formulas\n\nRow {row}: {formula}")

    time.sleep(0.5)

    # --- Step 3: Add a totals row ---
    recorder.update_panel("info", "Step 3: Add totals row\n\nSUM formulas for\nrevenue, costs, profit")

    # We're now in E8 after entering the last formula — go to A9
    kb.key("Home")  # Go to column A
    kb.key("Down")  # Down to row 9
    time.sleep(0.3)

    kb.type("TOTAL")
    kb.key("Tab")
    time.sleep(0.3)

    kb.type("=SUM(B2:B7)")
    kb.key("Tab")
    time.sleep(0.3)

    kb.type("=SUM(C2:C7)")
    kb.key("Tab")
    time.sleep(0.3)

    kb.type("=SUM(D2:D7)")
    kb.key("Tab")
    time.sleep(0.3)

    kb.type("=D9/B9*100")
    kb.key("Return")
    time.sleep(1)

    recorder.update_panel("info", "Step 3 complete\n\nTotal revenue: =SUM(B2:B7)\nTotal costs: =SUM(C2:C7)\nTotal profit: =SUM(D2:D7)\nOverall margin: =D9/B9*100")

    time.sleep(1)

    # --- Step 4: Save the file ---
    recorder.update_panel("info", "Step 4: Save file\n\nCtrl+S to save")

    # Re-focus the main window before save
    kb.find_and_focus("Gnumeric")
    time.sleep(0.3)

    kb.key("ctrl+s")
    time.sleep(2)

    # Ctrl+S on a CSV opens a "Save As" dialog (GTK file chooser).
    # The dialog has a filename field at the top. Click it to focus,
    # clear it, type a .gnumeric filename (matching the default file
    # type), then press Enter to save.
    subprocess.run(
        ["xdotool", "mousemove", "--sync", "500", "44",
         "click", "1"],
        env=recorder.display_env,
    )
    time.sleep(0.5)
    # Select all text in the filename field and replace it
    kb.key("ctrl+a")
    time.sleep(0.2)
    kb.type("working_spreadsheet.gnumeric")
    time.sleep(0.3)
    kb.key("Return")
    time.sleep(2)

    recorder.update_panel("test", "All steps complete!")
    recorder.update_panel(
        "info",
        "Done!\n\n"
        "Added: Margin % column (E)\n"
        "Added: TOTAL row with SUMs\n"
        "Saved: working_spreadsheet.csv\n"
        "\n"
        "Thea recorded it all without\n"
        "any app-specific code."
    )
    time.sleep(2)

    video_path = recorder.stop_recording()

    # Verify the recording was created and has content
    assert video_path is not None
    assert os.path.exists(video_path)
    file_size = os.path.getsize(video_path)
    assert file_size > 0
    print(f"Gnumeric recording saved: {video_path} ({file_size:,} bytes)")

    # Gnumeric saves as .gnumeric (XML) format via the Save As dialog.
    # The saved file will be at the same path but with .gnumeric extension,
    # or possibly the original name with .gnumeric appended.
    import glob
    gnumeric_files = glob.glob(os.path.join(output_dir, "*.gnumeric"))
    print(f"Gnumeric files found: {gnumeric_files}")

    assert len(gnumeric_files) > 0, (
        f"Expected a .gnumeric file in {output_dir}, found: "
        f"{os.listdir(output_dir)}"
    )

    # The .gnumeric file is gzipped XML — verify it contains our data
    import gzip
    with gzip.open(gnumeric_files[0], "rt") as f:
        xml_content = f.read()
    print(f"Saved file contains {len(xml_content)} chars of XML")

    assert "Margin" in xml_content, "Expected 'Margin' header in saved file"
    assert "TOTAL" in xml_content, "Expected 'TOTAL' label in saved file"
    # Gnumeric may lowercase function names (SUM -> sum)
    assert "sum" in xml_content.lower(), "Expected SUM formula in saved file"
    print("Verified: saved file contains Margin header, TOTAL row, and SUM formulas")
