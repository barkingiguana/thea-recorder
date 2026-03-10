# Orchestration: Demos and Parallel Sessions

thea-recorder isn't only for E2E test suites.  Any time you need a scripted
browser session captured to video, it works — product demos, release
walkthroughs, compliance evidence, or simulating multiple concurrent users.

## Recording a product demo

Instead of writing a test, write a script.  Point it at a running recorder
server and annotate what's happening in the overlay panels:

```python
from thea import RecorderClient

client = RecorderClient("http://localhost:9123")
client.start_display()
client.add_panel("scene",  title="Scene",  width=260)
client.add_panel("action", title="Action")

def narrate(scene, action):
    client.update_panel("scene",  scene)
    client.update_panel("action", action)

with client.recording("product_demo_v2") as result:
    narrate("Login", "Navigating to the login page")
    # driver.get("https://app.example.com/login")

    narrate("Login", "Entering credentials")
    # driver.find_element(...).send_keys(...)

    narrate("Dashboard", "Dashboard loaded — showing key metrics")

print(f"Video: {result.path}  ({result.elapsed:.1f}s)")
client.cleanup()
```

Full example: [`examples/product_demo.py`](../examples/product_demo.py)

### Use cases for demo recordings

| Audience | What they get |
|---|---|
| Sales & marketing | Always-fresh product walkthrough, no presenter required |
| Stakeholders | Sprint demo that actually shows the browser, not slides |
| New hires | Video onboarding — watch what the app does, step by step |
| Compliance / audit | Timestamped evidence of manual verification steps |

### Running on a schedule

Pair it with cron or a CI schedule to regenerate the demo video automatically:

```yaml
# GitHub Actions — regenerate demo on every main push
on:
  push:
    branches: [main]
jobs:
  demo:
    runs-on: ubuntu-latest
    services:
      recorder:
        image: ghcr.io/barkingiguana/thea-recorder:latest
        ports: ["9123:9123"]
    steps:
      - uses: actions/checkout@v4
      - run: pip install thea-recorder
      - run: python examples/product_demo.py
      - uses: actions/upload-artifact@v4
        with:
          name: demo-video
          path: recordings/*.mp4
```

---

## Parallel recordings — simulating multiple users

Some scenarios need more than one browser at a time: collaborative features,
real-time data sync, multi-tenant workflows, or simulating 2–3 concurrent
users to make a demo more compelling.

A **single** recorder server manages any number of parallel sessions.
Each session has its own Xvfb display, its own ffmpeg recording process,
and its own set of overlay panels — browsers in different sessions are
completely isolated from each other.

### Session API overview

| Endpoint | Description |
|---|---|
| `POST /sessions` | Create a named session (auto-allocates display) |
| `GET /sessions` | List all sessions |
| `DELETE /sessions/{name}` | Destroy a session |
| `POST /sessions/{name}/display/start` | Start that session's Xvfb |
| `POST /sessions/{name}/panels` | Add a panel to that session |
| `POST /sessions/{name}/recording/start` | Begin recording that session |
| `POST /sessions/{name}/recording/stop` | Stop recording that session |
| *(all other session-scoped endpoints follow the same pattern)* | |

The existing `/display/start`, `/panels`, `/recording/start`, etc. endpoints
all continue to work unchanged — they operate on the implicit **default**
session.

### Python example

```python
import threading
from thea import RecorderClient

THEA_URL = "http://localhost:9123"

def user_session(user_id):
    session_name = f"user_{user_id}"
    client = RecorderClient(THEA_URL)

    client.create_session(session_name)   # server allocates a display
    try:
        client.use_session(session_name)  # route all calls through it
        client.start_display()
        client.add_panel("user",   title="User",   width=160)
        client.add_panel("status", title="Status")

        client.update_panel("user",   f"User {user_id}")
        client.update_panel("status", "Logging in…")

        # Launch your browser pointed at this session's display, e.g.:
        #   display = f":{client.create_session(session_name)['display']}"
        #   os.environ["DISPLAY"] = display
        #   driver = webdriver.Chrome()

        with client.recording(f"session_user_{user_id}") as result:
            # ... browser automation for this user ...
            pass

        print(f"[user {user_id}] {result.path}  ({result.elapsed:.1f}s)")
    finally:
        client.delete_session(session_name)  # stops display + recording


# Run all users in parallel
threads = [threading.Thread(target=user_session, args=(i,)) for i in [1, 2, 3]]
for t in threads: t.start()
for t in threads: t.join()
```

Full example: [`examples/parallel_users.py`](../examples/parallel_users.py)

### Creating a session via curl

```bash
# Create a session — server auto-allocates display :100
curl -X POST http://localhost:9123/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "alice"}'
# → {"name": "alice", "display": 100, "url_prefix": "/sessions/alice"}

# Start the display for that session
curl -X POST http://localhost:9123/sessions/alice/display/start

# Start recording
curl -X POST http://localhost:9123/sessions/alice/recording/start \
  -H "Content-Type: application/json" \
  -d '{"name": "alice_checkout"}'

# List all sessions
curl http://localhost:9123/sessions

# Stop and delete
curl -X POST http://localhost:9123/sessions/alice/recording/stop
curl -X DELETE http://localhost:9123/sessions/alice
```

### With Docker Compose

Start one recorder server, let it manage all sessions:

```yaml
services:
  recorder:
    image: ghcr.io/barkingiguana/thea-recorder:latest
    command: thea serve --port 9123 --output-dir /recordings
    ports: ["9123:9123"]
    shm_size: "2g"
    volumes: ["./recordings:/recordings"]

  tests:
    build: .
    depends_on: [recorder]
    command: python examples/parallel_users.py
    environment:
      THEA_URL: http://recorder:9123
```

### Parallel recordings in test frameworks

If your test runner parallelises workers (pytest-xdist, parallel Cucumber,
etc.), assign each worker its own named session:

```python
# conftest.py (pytest-xdist)
import pytest
from thea import RecorderClient

@pytest.fixture(scope="session")
def recorder(worker_id):
    # worker_id is "gw0", "gw1", … or "master"
    session_name = worker_id if worker_id != "master" else "gw0"
    client = RecorderClient("http://localhost:9123")
    client.create_session(session_name)
    client.use_session(session_name)
    client.start_display()
    yield client
    client.delete_session(session_name)
```

```bash
# Start one server, run 4 parallel workers
thea serve --port 9123
pytest -n 4
```
