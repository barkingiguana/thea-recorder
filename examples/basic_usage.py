"""Minimal example: record a virtual display and generate a report.

This shows the core API without any test framework.
Requires Xvfb and ffmpeg to be installed.
"""

from recorder import Recorder, generate_report

# 1. Create a recorder
recorder = Recorder(
    output_dir="./recordings",
    display=99,
    display_size="1920x1080",
    framerate=15,
)

# 2. Add panels (optional — skip for raw screen capture)
recorder.add_panel("status", title="Status", width=120)
recorder.add_panel("log", title="Activity Log")

# 3. Start the virtual display
recorder.start_display()

# 4. Record a session
recorder.start_recording("my_first_recording")
recorder.update_panel("status", "Running")
recorder.update_panel("log", "Step 1: Launching application\nStep 2: Performing action")

# ... your application runs here (browser, GUI app, terminal, etc.) ...
# Configure it to use DISPLAY=:99

# 5. Stop and get the video path
video_path = recorder.stop_recording()
print(f"Video saved: {video_path}")

# 6. Generate an HTML report
videos = [
    {
        "feature": "My Feature",
        "scenario": "My Scenario",
        "status": "passed",
        "video": video_path,
        "steps": [
            {"keyword": "Given", "name": "a browser", "status": "passed", "offset": 0.0},
            {"keyword": "When", "name": "I navigate to the page", "status": "passed", "offset": 2.0},
            {"keyword": "Then", "name": "I see the content", "status": "passed", "offset": 4.5},
        ],
    },
]
report = generate_report(videos, output_dir="./recordings", title="My Test Report")
print(f"Report: {report}")

# 7. Cleanup
recorder.cleanup()
