"""CLI for the recorder: server mode and client mode.

Server mode starts a long-running HTTP server wrapping a Recorder instance.
Client mode sends HTTP requests to a running server.

Usage::

    thea serve --port 9123 --output-dir ./recordings
    thea start-display
    thea add-panel --name status --title Status --width 120
    thea start-recording --name my_scenario
    thea stop-recording
    thea download --name my_scenario --output ./local.mp4
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

import click


def _server_url(ctx: click.Context) -> str:
    return ctx.obj["server"]


def _request(url: str, method: str = "GET", data: dict = None) -> tuple[int, dict | bytes]:
    """Make an HTTP request and return (status_code, parsed_json_or_bytes)."""
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = Request(url, data=body, headers=headers, method=method)
    try:
        resp = urlopen(req, timeout=30)
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read()
        if "json" in content_type:
            return resp.status, json.loads(raw)
        return resp.status, raw
    except URLError as e:
        if hasattr(e, "read"):
            try:
                body = json.loads(e.read())
                return e.code, body
            except Exception:
                pass
        raise


def _print_result(data, quiet: bool, pretty: bool):
    if quiet:
        return
    if isinstance(data, bytes):
        sys.stdout.buffer.write(data)
        return
    if pretty:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(json.dumps(data))


def _handle_connection_error(server: str):
    click.echo(
        f"Error: cannot reach recorder server at {server} — is 'thea serve' running?",
        err=True,
    )
    sys.exit(1)


# ── Main group ───────────────────────────────────────────────────────────

def _print_warnings(warnings, ignore):
    """Print layout warnings to stderr unless ignored."""
    if ignore or not warnings:
        return
    for w in warnings:
        click.echo(f"Warning: {w}", err=True)


@click.group()
@click.option("--server", envvar="THEA_URL", default="http://localhost:9123",
              help="Recorder server URL (or set THEA_URL).")
@click.option("--quiet", is_flag=True, default=False, help="Suppress output (exit code only).")
@click.option("--pretty", is_flag=True, default=False, help="Pretty-print JSON output.")
@click.option("--ignore-warnings", is_flag=True, default=False,
              help="Suppress layout validation warnings.")
@click.pass_context
def main(ctx, server, quiet, pretty, ignore_warnings):
    """Record Xvfb virtual displays as MP4 video with panel overlays."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server.rstrip("/")
    ctx.obj["quiet"] = quiet
    ctx.obj["pretty"] = pretty
    ctx.obj["ignore_warnings"] = ignore_warnings


# ── Server mode ──────────────────────────────────────────────────────────

@main.command()
@click.option("--host", default="0.0.0.0", envvar="THEA_HOST", help="Host to bind to.")
@click.option("--port", default=9123, type=int, help="Port to listen on.")
@click.option("--display", default=99, type=int, help="X11 display number.")
@click.option("--output-dir", default="/tmp/recordings", help="Video output directory.")
@click.option("--default-display-size", default="1920x1080", envvar="THEA_DISPLAY_SIZE",
              help="Default display resolution for new sessions (WxH).")
@click.option("--framerate", default=15, type=int, help="Recording framerate (fps).")
@click.option("--cors", is_flag=True, default=False, help="Enable CORS headers.")
def serve(host, port, display, output_dir, default_display_size, framerate, cors):
    """Start the recorder HTTP server."""
    from .server import create_app

    app = create_app(
        output_dir=output_dir,
        display=display,
        display_size=default_display_size,
        framerate=framerate,
        enable_cors=cors,
    )
    click.echo(f"Thea recorder server starting on http://{host}:{port}")
    click.echo(f"  Display: :{display}  Output: {output_dir}  FPS: {framerate}")
    click.echo(f"  Default resolution: {default_display_size}")
    if cors:
        click.echo("  CORS: enabled")
    app.run(host=host, port=port, threaded=True)


# ── Display commands ─────────────────────────────────────────────────────

@main.command("start-display")
@click.option("--display-size", default=None, help="Override display resolution (WxH) for this session.")
@click.pass_context
def start_display(ctx, display_size):
    """Start the Xvfb virtual display."""
    server = _server_url(ctx)
    body = {}
    if display_size is not None:
        body["display_size"] = display_size
    try:
        status, data = _request(f"{server}/display/start", method="POST", data=body or None)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("screenshot")
@click.option("--output", "-o", required=True, help="Output JPEG file path.")
@click.option("--quality", default=80, type=int, help="JPEG quality (1-100).")
@click.pass_context
def screenshot(ctx, output, quality):
    """Capture a screenshot of the live display."""
    server = _server_url(ctx)
    try:
        req = Request(f"{server}/display/screenshot?quality={quality}")
        resp = urlopen(req, timeout=10)
        data = resp.read()
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    with open(output, "wb") as f:
        f.write(data)
    if not ctx.obj["quiet"]:
        click.echo(json.dumps({"path": output, "size": len(data)}))


@main.command("recording-screenshot")
@click.option("--name", required=True, help="Recording name.")
@click.option("--time", "time_offset", required=True, type=float, help="Time offset in seconds.")
@click.option("--output", "-o", required=True, help="Output JPEG file path.")
@click.option("--quality", default=80, type=int, help="JPEG quality (1-100).")
@click.pass_context
def recording_screenshot(ctx, name, time_offset, output, quality):
    """Extract a frame from a recorded video at a given time offset."""
    server = _server_url(ctx)
    url = f"{server}/recordings/{name}/screenshot?t={time_offset}&quality={quality}"
    try:
        req = Request(url)
        resp = urlopen(req, timeout=30)
        data = resp.read()
    except URLError as e:
        if hasattr(e, "code") and e.code == 404:
            click.echo(f"Error: recording '{name}' not found", err=True)
            sys.exit(1)
        if hasattr(e, "code") and e.code == 400:
            click.echo(f"Error: {e.read().decode('utf-8', errors='replace')}", err=True)
            sys.exit(1)
        _handle_connection_error(server)
    except (ConnectionError, OSError):
        _handle_connection_error(server)
    with open(output, "wb") as f:
        f.write(data)
    if not ctx.obj["quiet"]:
        click.echo(json.dumps({"path": output, "size": len(data)}))


@main.command("stream-url")
@click.option("--fps", default=5, type=int, help="Frames per second (1-15).")
@click.pass_context
def stream_url(ctx, fps):
    """Print the MJPEG stream URL for the live display."""
    server = _server_url(ctx)
    url = f"{server}/display/stream?fps={fps}"
    if not ctx.obj["quiet"]:
        click.echo(url)


@main.command("view-url")
@click.pass_context
def view_url(ctx):
    """Print the URL for the HTML live viewer page."""
    server = _server_url(ctx)
    url = f"{server}/display/view"
    if not ctx.obj["quiet"]:
        click.echo(url)


@main.command("stop-display")
@click.pass_context
def stop_display(ctx):
    """Stop the Xvfb virtual display."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/display/stop", method="POST")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


# ── Panel commands ───────────────────────────────────────────────────────

@main.command("add-panel")
@click.option("--name", required=True, help="Panel identifier.")
@click.option("--title", default="", help="Panel heading.")
@click.option("--width", default=None, type=int, help="Fixed width in pixels.")
@click.option("--height", default=None, type=int, help="Panel height in pixels.")
@click.option("--bg-color", default=None, help="Background colour (hex, e.g. '1a1a2e').")
@click.option("--opacity", default=None, type=float, help="Background opacity (0.0-1.0).")
@click.pass_context
def add_panel(ctx, name, title, width, height, bg_color, opacity):
    """Add a named panel to the overlay bar."""
    server = _server_url(ctx)
    body = {"name": name, "title": title}
    if width is not None:
        body["width"] = width
    if height is not None:
        body["height"] = height
    if bg_color is not None:
        body["bg_color"] = bg_color
    if opacity is not None:
        body["opacity"] = opacity
    try:
        status, data = _request(f"{server}/panels", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_warnings(data.get("warnings", []), ctx.obj["ignore_warnings"])
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("update-panel")
@click.option("--name", required=True, help="Panel identifier.")
@click.option("--text", required=True, help="Panel content.")
@click.option("--focus-line", default=-1, type=int, help="Line to keep visible.")
@click.pass_context
def update_panel(ctx, name, text, focus_line):
    """Update a panel's content."""
    server = _server_url(ctx)
    body = {"text": text, "focus_line": focus_line}
    try:
        status, data = _request(f"{server}/panels/{name}", method="PUT", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("remove-panel")
@click.option("--name", required=True, help="Panel identifier.")
@click.pass_context
def remove_panel(ctx, name):
    """Remove a panel from the overlay bar."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/panels/{name}", method="DELETE")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


# ── Recording commands ───────────────────────────────────────────────────

@main.command("start-recording")
@click.option("--name", required=True, help="Recording filename (sans .mp4).")
@click.pass_context
def start_recording(ctx, name):
    """Begin recording the virtual display."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/recording/start", method="POST", data={"name": name})
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_warnings(data.get("warnings", []), ctx.obj["ignore_warnings"])
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("stop-recording")
@click.pass_context
def stop_recording(ctx):
    """Stop recording and print the video path."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/recording/stop", method="POST")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("elapsed")
@click.pass_context
def elapsed(ctx):
    """Print elapsed recording time."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/recording/elapsed")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("annotate")
@click.option("--label", required=True, help="Annotation label.")
@click.option("--time", "time_offset", type=float, default=None, help="Time offset in seconds (default: current elapsed).")
@click.option("--details", default=None, help="Optional details text.")
@click.pass_context
def annotate(ctx, label, time_offset, details):
    """Add an annotation to the active recording."""
    server = _server_url(ctx)
    body = {"label": label}
    if time_offset is not None:
        body["time"] = time_offset
    if details is not None:
        body["details"] = details
    try:
        status, data = _request(f"{server}/recording/annotations", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("list-annotations")
@click.pass_context
def list_annotations(ctx):
    """List annotations for the active recording."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/recording/annotations")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


# ── File commands ────────────────────────────────────────────────────────

@main.command("list-recordings")
@click.pass_context
def list_recordings(ctx):
    """List available recordings."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/recordings")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("download")
@click.option("--name", required=True, help="Recording name.")
@click.option("--output", required=True, help="Local output file path.")
@click.pass_context
def download(ctx, name, output):
    """Download a recording to a local file."""
    server = _server_url(ctx)
    url = f"{server}/recordings/{name}"
    try:
        req = Request(url)
        resp = urlopen(req, timeout=300)
        with open(output, "wb") as f:
            shutil.copyfileobj(resp, f)
        if not ctx.obj["quiet"]:
            size = os.path.getsize(output)
            click.echo(json.dumps({"path": output, "size": size}))
    except URLError as e:
        if hasattr(e, "code") and e.code == 404:
            click.echo(f"Error: recording '{name}' not found", err=True)
            sys.exit(1)
        _handle_connection_error(server)
    except (ConnectionError, OSError):
        _handle_connection_error(server)


# ── Events and dashboard commands ────────────────────────────────────────

@main.command("events")
@click.option("--since", default=None, type=float, help="Only show events after this elapsed time.")
@click.pass_context
def events(ctx, since):
    """List events from the session event log."""
    server = _server_url(ctx)
    url = f"{server}/events"
    if since is not None:
        url += f"?since={since}"
    try:
        status, data = _request(url)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("dashboard-url")
@click.pass_context
def dashboard_url(ctx):
    """Print the URL for the HTML dashboard page."""
    server = _server_url(ctx)
    if not ctx.obj["quiet"]:
        click.echo(f"{server}/dashboard")


# ── Utility commands ─────────────────────────────────────────────────────

@main.command("health")
@click.pass_context
def health(ctx):
    """Check server health."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/health")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("cleanup")
@click.pass_context
def cleanup(ctx):
    """Full teardown: stop recording, display, remove panels."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/cleanup", method="POST")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("version")
@click.pass_context
def version(ctx):
    """Print the recorder version."""
    _print_result({"version": "0.12.0"}, ctx.obj["quiet"], ctx.obj["pretty"])


# ── Layout commands ──────────────────────────────────────────────────

@main.command("validate-layout")
@click.pass_context
def validate_layout(ctx):
    """Validate the current panel layout and print warnings."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/validate-layout")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    warnings = data.get("warnings", [])
    if warnings:
        for w in warnings:
            click.echo(f"Warning: {w}", err=True)
    elif not ctx.obj["quiet"]:
        click.echo("Layout is valid.", err=True)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("testcard")
@click.option("--output", "-o", default=None, help="Write SVG to file instead of stdout.")
@click.pass_context
def testcard(ctx, output):
    """Generate an SVG testcard of the current layout."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/testcard")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if isinstance(data, bytes):
        svg = data.decode("utf-8", errors="replace")
    else:
        svg = str(data)
    if output:
        with open(output, "w") as f:
            f.write(svg)
        if not ctx.obj["quiet"]:
            click.echo(f"Testcard saved to {output}", err=True)
    else:
        click.echo(svg)


# ── Composition commands ──────────────────────────────────────────────────

@main.command("compose")
@click.option("--name", required=True, help="Name for the composed video.")
@click.option("--recordings", required=True, help="Comma-separated list of recording names.")
@click.option("--layout", default="row", type=click.Choice(["row", "column", "grid"]),
              help="Tile layout.")
@click.option("--labels/--no-labels", default=True, help="Show recording names on each tile.")
@click.option("--highlight", "highlights", multiple=True,
              help="Highlight event as 'recording:time:duration' (repeatable).")
@click.option("--highlight-color", default="00d4aa", help="Hex colour for highlight border.")
@click.option("--highlight-width", default=6, type=int, help="Highlight border width in pixels.")
@click.option("--wait/--no-wait", default=True, help="Wait for composition to finish.")
@click.pass_context
def compose(ctx, name, recordings, layout, labels, highlights, highlight_color, highlight_width, wait):
    """Compose multiple recordings into a single side-by-side video.

    \b
    Example — two recordings side by side:
      thea compose --name demo --recordings user_1,user_2

    \b
    Example — with highlight borders:
      thea compose --name demo --recordings alice,bob \\
        --highlight alice:3.5:2.0 --highlight bob:6.0:1.5
    """
    server = _server_url(ctx)
    recording_list = [r.strip() for r in recordings.split(",") if r.strip()]

    # Parse highlight flags.
    parsed_highlights = []
    for h in highlights:
        parts = h.split(":")
        if len(parts) < 2:
            click.echo(f"Error: highlight '{h}' must be 'recording:time' or 'recording:time:duration'", err=True)
            sys.exit(1)
        rec = parts[0]
        t = float(parts[1])
        dur = float(parts[2]) if len(parts) > 2 else 1.0
        parsed_highlights.append({"recording": rec, "time": t, "duration": dur})

    body = {
        "name": name,
        "recordings": recording_list,
        "layout": layout,
        "labels": labels,
        "highlights": parsed_highlights,
        "highlight_color": highlight_color,
        "highlight_width": highlight_width,
    }

    try:
        status, data = _request(f"{server}/compositions", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)

    if not wait:
        _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])
        return

    # Poll until complete.
    import time as _time
    while True:
        _time.sleep(1)
        try:
            status, data = _request(f"{server}/compositions/{name}")
        except (URLError, ConnectionError, OSError):
            _handle_connection_error(server)
        if data.get("status") in ("complete", "failed"):
            break

    if data.get("status") == "failed":
        click.echo(f"Error: composition failed — {data.get('error', 'unknown')}", err=True)
        sys.exit(1)

    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("compose-status")
@click.option("--name", required=True, help="Composition name.")
@click.pass_context
def compose_status(ctx, name):
    """Check the status of a composition."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/compositions/{name}")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("list-compositions")
@click.pass_context
def list_compositions(ctx):
    """List all compositions."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/compositions")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


# ── Parallel mode ─────────────────────────────────────────────────────────

@main.command("multi")
@click.option("--instances", default=3, type=int, show_default=True,
              help="Number of parallel recorder instances.")
@click.option("--base-port", default=9123, type=int, show_default=True,
              help="Port for the first instance; subsequent instances use base+1, base+2, …")
@click.option("--base-display", default=99, type=int, show_default=True,
              help="X11 display for the first instance; subsequent instances use base+1, base+2, …")
@click.option("--output-dir", default="/tmp/recordings", show_default=True,
              help="Shared MP4 output directory.")
@click.option("--default-display-size", default="1920x1080", show_default=True,
              envvar="THEA_DISPLAY_SIZE", help="Default display resolution for new sessions (WxH).")
@click.option("--framerate", default=15, type=int, show_default=True,
              help="Recording framerate (fps).")
@click.option("--cors", is_flag=True, default=False, help="Enable CORS headers on all instances.")
def multi(instances, base_port, base_display, output_dir, default_display_size, framerate, cors):
    """Start N independent recorder servers for parallel sessions.

    Each instance gets its own port and Xvfb display so applications run
    completely independently.  Point each application at the matching
    DISPLAY and connect your SDK to the matching port.

    \b
    Example — 3 parallel sessions:
      thea multi --instances 3 --base-port 9123 --output-dir ./recordings
      # Instance 1: http://localhost:9123  DISPLAY=:99
      # Instance 2: http://localhost:9124  DISPLAY=:100
      # Instance 3: http://localhost:9125  DISPLAY=:101
    """
    import subprocess
    import signal as _signal

    thea_cmd = shutil.which("thea") or sys.argv[0]

    procs = []
    click.echo(f"Starting {instances} recorder instance(s):\n")
    for i in range(instances):
        port = base_port + i
        display = base_display + i
        cmd = [
            thea_cmd, "serve",
            "--port", str(port),
            "--display", str(display),
            "--output-dir", output_dir,
            "--default-display-size", default_display_size,
            "--framerate", str(framerate),
        ]
        if cors:
            cmd.append("--cors")
        proc = subprocess.Popen(cmd)
        procs.append((port, display, proc))
        click.echo(f"  [{i + 1}] http://localhost:{port}   DISPLAY=:{display}")

    click.echo(f"\nAll {instances} instances running.  Press Ctrl+C to stop.\n")

    def _stop_all(signum=None, frame=None):
        click.echo("\nStopping all recorder instances…")
        for _port, _display, proc in procs:
            proc.terminate()
        for _port, _display, proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    _signal.signal(_signal.SIGTERM, _stop_all)

    try:
        for _port, _display, proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        _stop_all()


# ── Director: Mouse commands ─────────────────────────────────────────────

@main.command("mouse-move")
@click.option("--x", required=True, type=int, help="Target X coordinate.")
@click.option("--y", required=True, type=int, help="Target Y coordinate.")
@click.option("--duration", default=None, type=float, help="Movement duration in seconds.")
@click.option("--target-width", default=None, type=int, help="Target element width for Fitts's Law.")
@click.pass_context
def mouse_move(ctx, x, y, duration, target_width):
    """Move the mouse cursor to (x, y) with human-like motion."""
    server = _server_url(ctx)
    body = {"x": x, "y": y}
    if duration is not None:
        body["duration"] = duration
    if target_width is not None:
        body["target_width"] = target_width
    try:
        status, data = _request(f"{server}/director/mouse/move", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("mouse-click")
@click.option("--x", default=None, type=int, help="X coordinate (omit to click in place).")
@click.option("--y", default=None, type=int, help="Y coordinate (omit to click in place).")
@click.option("--button", default=1, type=int, help="Mouse button (1=left, 2=middle, 3=right).")
@click.option("--duration", default=None, type=float, help="Movement duration in seconds.")
@click.pass_context
def mouse_click(ctx, x, y, button, duration):
    """Click the mouse at (x, y) or in place."""
    server = _server_url(ctx)
    body = {"button": button}
    if x is not None:
        body["x"] = x
    if y is not None:
        body["y"] = y
    if duration is not None:
        body["duration"] = duration
    try:
        status, data = _request(f"{server}/director/mouse/click", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("mouse-double-click")
@click.option("--x", default=None, type=int, help="X coordinate.")
@click.option("--y", default=None, type=int, help="Y coordinate.")
@click.pass_context
def mouse_double_click(ctx, x, y):
    """Double-click at (x, y) or in place."""
    server = _server_url(ctx)
    body = {}
    if x is not None:
        body["x"] = x
    if y is not None:
        body["y"] = y
    try:
        status, data = _request(f"{server}/director/mouse/double-click", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("mouse-right-click")
@click.option("--x", default=None, type=int, help="X coordinate.")
@click.option("--y", default=None, type=int, help="Y coordinate.")
@click.pass_context
def mouse_right_click(ctx, x, y):
    """Right-click at (x, y) or in place."""
    server = _server_url(ctx)
    body = {}
    if x is not None:
        body["x"] = x
    if y is not None:
        body["y"] = y
    try:
        status, data = _request(f"{server}/director/mouse/right-click", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("mouse-drag")
@click.option("--start-x", required=True, type=int, help="Start X.")
@click.option("--start-y", required=True, type=int, help="Start Y.")
@click.option("--end-x", required=True, type=int, help="End X.")
@click.option("--end-y", required=True, type=int, help="End Y.")
@click.option("--button", default=1, type=int, help="Mouse button.")
@click.option("--duration", default=None, type=float, help="Drag duration in seconds.")
@click.pass_context
def mouse_drag(ctx, start_x, start_y, end_x, end_y, button, duration):
    """Drag from (start-x, start-y) to (end-x, end-y)."""
    server = _server_url(ctx)
    body = {"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y, "button": button}
    if duration is not None:
        body["duration"] = duration
    try:
        status, data = _request(f"{server}/director/mouse/drag", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("mouse-scroll")
@click.option("--clicks", required=True, type=int, help="Scroll clicks (positive=up, negative=down).")
@click.option("--x", default=None, type=int, help="X coordinate.")
@click.option("--y", default=None, type=int, help="Y coordinate.")
@click.pass_context
def mouse_scroll(ctx, clicks, x, y):
    """Scroll the mouse wheel."""
    server = _server_url(ctx)
    body = {"clicks": clicks}
    if x is not None:
        body["x"] = x
    if y is not None:
        body["y"] = y
    try:
        status, data = _request(f"{server}/director/mouse/scroll", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("mouse-position")
@click.pass_context
def mouse_position(ctx):
    """Get the current mouse cursor position."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/director/mouse/position")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


# ── Director: Keyboard commands ──────────────────────────────────────────

@main.command("keyboard-type")
@click.argument("text")
@click.option("--wpm", default=None, type=int, help="Typing speed in words per minute.")
@click.pass_context
def keyboard_type(ctx, text, wpm):
    """Type text with human-like rhythm."""
    server = _server_url(ctx)
    body = {"text": text}
    if wpm is not None:
        body["wpm"] = wpm
    try:
        status, data = _request(f"{server}/director/keyboard/type", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("keyboard-press")
@click.argument("keys", nargs=-1, required=True)
@click.pass_context
def keyboard_press(ctx, keys):
    """Press one or more keys (e.g. Return, ctrl+a, Delete)."""
    server = _server_url(ctx)
    body = {"keys": list(keys)}
    try:
        status, data = _request(f"{server}/director/keyboard/press", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("keyboard-hold")
@click.argument("key")
@click.pass_context
def keyboard_hold(ctx, key):
    """Hold a key down (release with keyboard-release)."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/director/keyboard/hold", method="POST", data={"key": key})
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("keyboard-release")
@click.argument("key")
@click.pass_context
def keyboard_release(ctx, key):
    """Release a held key."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/director/keyboard/release", method="POST", data={"key": key})
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


# ── Director: Window commands ────────────────────────────────────────────

@main.command("window-find")
@click.option("--name", default=None, help="Window name/title substring.")
@click.option("--class", "window_class", default=None, help="Window class.")
@click.option("--timeout", default=10.0, type=float, help="Search timeout in seconds.")
@click.pass_context
def window_find(ctx, name, window_class, timeout):
    """Find a window by name or class."""
    server = _server_url(ctx)
    body = {"timeout": timeout}
    if name is not None:
        body["name"] = name
    elif window_class is not None:
        body["class"] = window_class
    else:
        click.echo("Error: --name or --class is required", err=True)
        sys.exit(1)
    try:
        status, data = _request(f"{server}/director/window/find", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("window-focus")
@click.argument("window_id")
@click.pass_context
def window_focus(ctx, window_id):
    """Focus a window by ID."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/director/window/{window_id}/focus", method="POST")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("window-move")
@click.argument("window_id")
@click.option("--x", required=True, type=int, help="X position.")
@click.option("--y", required=True, type=int, help="Y position.")
@click.pass_context
def window_move(ctx, window_id, x, y):
    """Move a window to (x, y)."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/director/window/{window_id}/move", method="POST", data={"x": x, "y": y})
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("window-resize")
@click.argument("window_id")
@click.option("--width", required=True, type=int, help="Width in pixels.")
@click.option("--height", required=True, type=int, help="Height in pixels.")
@click.pass_context
def window_resize(ctx, window_id, width, height):
    """Resize a window."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/director/window/{window_id}/resize", method="POST", data={"width": width, "height": height})
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("window-minimize")
@click.argument("window_id")
@click.pass_context
def window_minimize(ctx, window_id):
    """Minimize a window."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/director/window/{window_id}/minimize", method="POST")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("window-geometry")
@click.argument("window_id")
@click.pass_context
def window_geometry(ctx, window_id):
    """Get window position and size."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/director/window/{window_id}/geometry")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


@main.command("window-tile")
@click.option("--ids", required=True, help="Comma-separated window IDs.")
@click.option("--layout", default="side-by-side", type=click.Choice(["side-by-side", "stacked", "grid"]),
              help="Tile layout.")
@click.pass_context
def window_tile(ctx, ids, layout):
    """Tile multiple windows in the display."""
    server = _server_url(ctx)
    window_ids = [i.strip() for i in ids.split(",") if i.strip()]
    try:
        status, data = _request(f"{server}/director/window/tile", method="POST",
                                data={"window_ids": window_ids, "layout": layout})
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])
