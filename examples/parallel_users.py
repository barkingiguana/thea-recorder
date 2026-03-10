"""Parallel multi-user recording with thea-recorder.

Simulates 3 independent users interacting with the same application
simultaneously.  A *single* recorder server manages all sessions — each
session has its own Xvfb display, ffmpeg process, and set of overlay panels.

Prerequisites:
  Start one recorder server:

    thea serve --port 9123 --output-dir ./recordings

Then run this script.  Sessions are created and destroyed automatically.
"""

import os
import time
import threading

from thea import RecorderClient

THEA_URL = os.environ.get("THEA_URL", "http://localhost:9123")

# ── Per-user scenario ──────────────────────────────────────────────────────

def user_session(user_id: int):
    """Drive one browser in its own isolated session."""
    session_name = f"user_{user_id}"
    client = RecorderClient(THEA_URL)

    # Create a dedicated session — the server allocates a free display number.
    client.create_session(session_name)
    try:
        client.use_session(session_name)
        client.start_display()
        client.add_panel("user",   title="User",   width=160)
        client.add_panel("status", title="Status")

        client.update_panel("user",   f"User {user_id}")
        client.update_panel("status", "Initialising…")

        # In a real script, launch a browser against the session's display:
        #   display = client.session_display()       # e.g. ":100"
        #   os.environ["DISPLAY"] = display
        #   driver = webdriver.Chrome()

        with client.recording(f"scenario_user_{user_id}") as result:
            # Stagger start times so the recording shows independent pacing
            delay = (user_id - 1) * 0.8

            time.sleep(delay)
            client.update_panel("status", "Logging in")
            time.sleep(1.2)

            client.update_panel("status", "Browsing product catalogue")
            time.sleep(1.5 + delay * 0.3)

            client.update_panel("status", "Adding item to cart")
            time.sleep(0.8)

            client.update_panel("status", "Checking out")
            time.sleep(1.0)

            client.update_panel("status", "Order confirmed ✓")
            time.sleep(0.5)

        print(f"[user {user_id}] {result.path}  ({result.elapsed:.1f}s)")

    finally:
        # Teardown the session (stops its display and ffmpeg, frees the display number)
        client.delete_session(session_name)


# ── Launch all users in parallel ───────────────────────────────────────────

USER_IDS = [1, 2, 3]

threads = [
    threading.Thread(target=user_session, args=(uid,), name=f"user-{uid}")
    for uid in USER_IDS
]

print(f"Starting {len(threads)} parallel user sessions…\n")
for t in threads:
    t.start()
for t in threads:
    t.join()

print("\nAll sessions complete.")
