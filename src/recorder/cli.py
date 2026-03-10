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

@click.group()
@click.option("--server", envvar="THEA_URL", default="http://localhost:9123",
              help="Recorder server URL (or set THEA_URL).")
@click.option("--quiet", is_flag=True, default=False, help="Suppress output (exit code only).")
@click.option("--pretty", is_flag=True, default=False, help="Pretty-print JSON output.")
@click.pass_context
def main(ctx, server, quiet, pretty):
    """Record E2E tests as MP4 video with panel overlays."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server.rstrip("/")
    ctx.obj["quiet"] = quiet
    ctx.obj["pretty"] = pretty


# ── Server mode ──────────────────────────────────────────────────────────

@main.command()
@click.option("--port", default=9123, type=int, help="Port to listen on.")
@click.option("--display", default=99, type=int, help="X11 display number.")
@click.option("--output-dir", default="/tmp/recordings", help="Video output directory.")
@click.option("--browser-size", default="1920x1080", help="Browser viewport size (WxH).")
@click.option("--framerate", default=15, type=int, help="Recording framerate (fps).")
@click.option("--cors", is_flag=True, default=False, help="Enable CORS headers.")
def serve(port, display, output_dir, browser_size, framerate, cors):
    """Start the recorder HTTP server."""
    from .server import create_app

    app = create_app(
        output_dir=output_dir,
        display=display,
        browser_size=browser_size,
        framerate=framerate,
        enable_cors=cors,
    )
    click.echo(f"Thea recorder server starting on http://0.0.0.0:{port}")
    click.echo(f"  Display: :{display}  Output: {output_dir}  FPS: {framerate}")
    if cors:
        click.echo("  CORS: enabled")
    app.run(host="0.0.0.0", port=port, threaded=True)


# ── Display commands ─────────────────────────────────────────────────────

@main.command("start-display")
@click.pass_context
def start_display(ctx):
    """Start the Xvfb virtual display."""
    server = _server_url(ctx)
    try:
        status, data = _request(f"{server}/display/start", method="POST")
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
    _print_result(data, ctx.obj["quiet"], ctx.obj["pretty"])


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
@click.pass_context
def add_panel(ctx, name, title, width):
    """Add a named panel to the overlay bar."""
    server = _server_url(ctx)
    body = {"name": name, "title": title}
    if width is not None:
        body["width"] = width
    try:
        status, data = _request(f"{server}/panels", method="POST", data=body)
    except (URLError, ConnectionError, OSError):
        _handle_connection_error(server)
    if status >= 400:
        click.echo(f"Error: {data.get('error', 'unknown')}", err=True)
        sys.exit(1)
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
    _print_result({"version": "0.2.0"}, ctx.obj["quiet"], ctx.obj["pretty"])


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
@click.option("--browser-size", default="1920x1080", show_default=True,
              help="Browser viewport size (WxH).")
@click.option("--framerate", default=15, type=int, show_default=True,
              help="Recording framerate (fps).")
@click.option("--cors", is_flag=True, default=False, help="Enable CORS headers on all instances.")
def multi(instances, base_port, base_display, output_dir, browser_size, framerate, cors):
    """Start N independent recorder servers for parallel browser sessions.

    Each instance gets its own port and Xvfb display so browsers run
    completely independently.  Point each browser at the matching
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
            "--browser-size", browser_size,
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
