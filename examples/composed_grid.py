"""Composition with 4 tiles in a grid layout.

Records four sessions and composes them into a 2×2 grid.
Great for showing multiple parallel workflows at once.

Prerequisites:
  thea serve --port 9123 --output-dir ./recordings
"""

import threading
import time

from thea import RecorderClient

THEA_URL = "http://localhost:9123"

USERS = {
    "alice":   ["Logging in",  "Dashboard",    "Creating report"],
    "bob":     ["Logging in",  "Inbox",        "Replying to email"],
    "charlie": ["Logging in",  "Settings",     "Updating profile"],
    "diana":   ["Logging in",  "Analytics",    "Exporting data"],
}


def record_user(name: str, steps: list[str]):
    client = RecorderClient(THEA_URL)
    client.create_session(name)
    try:
        client.use_session(name)
        client.start_display()
        client.add_panel("user",   title="User",   width=140)
        client.add_panel("status", title="Status")
        client.update_panel("user", name.title())

        with client.recording(f"rec_{name}"):
            for step in steps:
                client.update_panel("status", step)
                time.sleep(2)
    finally:
        client.delete_session(name)


# ── Record all four in parallel ───────────────────────────────────────────

threads = [
    threading.Thread(target=record_user, args=(name, steps))
    for name, steps in USERS.items()
]
for t in threads:
    t.start()
for t in threads:
    t.join()


# ── Compose into a 2×2 grid ──────────────────────────────────────────────

client = RecorderClient(THEA_URL)

client.create_composition(
    "four_users",
    recordings=["rec_alice", "rec_bob", "rec_charlie", "rec_diana"],
    layout="grid",    # auto 2×2 for 4 tiles
    labels=True,
    highlights=[
        # Highlight each user during their unique action (step 3)
        {"recording": "rec_alice",   "time": 4.0, "duration": 2.0},
        {"recording": "rec_bob",     "time": 4.0, "duration": 2.0},
        {"recording": "rec_charlie", "time": 4.0, "duration": 2.0},
        {"recording": "rec_diana",   "time": 4.0, "duration": 2.0},
    ],
)

result = client.wait_for_composition("four_users")
print(f"Grid video: {result['output_path']}")
