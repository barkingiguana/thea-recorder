"""HTTP server wrapping one or more named Recorder sessions.

Each session has its own Xvfb display, ffmpeg process, and panel set —
applications in different sessions are completely isolated from each other.

A *default* session is created at startup using the configured display
number.  Additional sessions can be created dynamically via the REST API.

Start with::

    thea serve --port 9123 --output-dir ./recordings
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import signal
import threading
import time
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, Response, jsonify, request, send_file

from .composer import CompositionManager, CompositionSpec, Highlight
from .recorder import Recorder

logger = logging.getLogger("recorder.server")


def create_app(
    output_dir: str = "/tmp/recordings",
    display: int = 99,
    display_size: str = "1920x1080",
    framerate: int = 15,
    enable_cors: bool = False,
) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

    # -- Session store -----------------------------------------------------
    #
    # Each session is a dict:
    #   recorder      – Recorder instance
    #   lock          – threading.Lock protecting the recorder
    #   current_name  – {"name": str|None} (active recording name)
    #   display       – X11 display number (int)

    _sessions: dict[str, dict] = {}
    _sessions_lock = threading.Lock()
    _next_display = [display + 1]   # auto-allocate display numbers

    def _make_session(display_num: int) -> dict:
        return {
            "recorder": Recorder(
                output_dir=output_dir,
                display=display_num,
                display_size=display_size,
                framerate=framerate,
            ),
            "lock": threading.Lock(),
            "current_name": {"name": None},
            "display": display_num,
        }

    # default session (backward-compat — existing endpoints use this)
    _default = _make_session(display)
    _sessions["default"] = _default

    # Convenience aliases for all the existing route handlers below
    recorder              = _default["recorder"]
    lock                  = _default["lock"]
    current_recording_name = _default["current_name"]

    start_time = time.monotonic()

    # -- Helpers -----------------------------------------------------------

    def locked(f):
        """Decorator that acquires the *default* session lock."""
        @wraps(f)
        def wrapper(*args, **kwargs):
            with lock:
                return f(*args, **kwargs)
        return wrapper

    def _safe_recording_name(name: str) -> bool:
        return ".." not in name and "/" not in name and "\\" not in name and name.strip() != ""

    def _resolve_recording_path(name: str) -> str | None:
        safe = re.sub(r"[^\w\-.]", "_", name)[:120]
        path = os.path.join(output_dir, f"{safe}.mp4")
        return path if os.path.isfile(path) else None

    def _list_mp4s() -> list[dict]:
        os.makedirs(output_dir, exist_ok=True)
        result = []
        for fname in sorted(os.listdir(output_dir)):
            if not fname.endswith(".mp4"):
                continue
            fpath = os.path.join(output_dir, fname)
            stat = os.stat(fpath)
            result.append({
                "name": fname[:-4],
                "path": fpath,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
            })
        return result

    def _session_or_404(name: str):
        """Return (session, None) or (None, error_response)."""
        with _sessions_lock:
            sess = _sessions.get(name)
        if sess is None:
            return None, (jsonify({"error": f"session '{name}' not found"}), 404)
        return sess, None

    # -- Per-session business logic ----------------------------------------
    # Each function accepts explicit session components so it can be
    # called from both the default routes and the /sessions/<name>/... routes.

    def _impl_display_start(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        req_display_size = data.get("display_size")
        with sess_lock:
            if rec._xvfb_proc is not None:
                return jsonify({"error": "display already started"}), 409
            rec.start_display(display_size=req_display_size)
            return jsonify({"status": "started", "display": rec.display_string}), 201

    def _impl_display_stop(rec, sess_lock):
        with sess_lock:
            rec.stop_display()
            return jsonify({"status": "stopped"}), 200

    def _impl_display_screenshot(rec, sess_lock):
        quality = request.args.get("quality", 80, type=int)
        quality = max(1, min(100, quality))
        with sess_lock:
            if rec._xvfb_proc is None:
                return jsonify({"error": "display not started"}), 409
        try:
            data = rec.screenshot(quality=quality)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500
        return Response(data, mimetype="image/jpeg")

    def _impl_display_stream(rec, sess_lock):
        fps = request.args.get("fps", 5, type=int)
        fps = max(1, min(15, fps))
        with sess_lock:
            if rec._xvfb_proc is None:
                return jsonify({"error": "display not started"}), 409

        def _generate():
            interval = 1.0 / fps
            while True:
                try:
                    jpeg = rec.screenshot()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                        + jpeg + b"\r\n"
                    )
                    time.sleep(interval)
                except GeneratorExit:
                    break
                except Exception:
                    break

        return Response(
            _generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    def _impl_display_view(rec, sess_lock):
        with sess_lock:
            display = rec.display_string
            display_size = rec._display_size
            recording = rec._ffmpeg_proc is not None
        # Build the stream URL relative to the current request
        stream_path = request.path.rsplit("/view", 1)[0] + "/stream"
        html = f"""\
<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thea Live — {display}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: system-ui, -apple-system, sans-serif;
    background: #0a0e17; color: #e2e8f0;
    display: flex; flex-direction: column; align-items: center;
    min-height: 100vh; padding: 1rem;
}}
.header {{
    display: flex; align-items: center; gap: 1rem;
    padding: 0.75rem 1.5rem; margin-bottom: 1rem;
    background: #111827; border: 1px solid #1e2d45;
    border-radius: 8px; width: fit-content;
}}
.header h1 {{ font-size: 1rem; font-weight: 600; }}
.badge {{
    padding: 3px 10px; border-radius: 12px;
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.5px; font-family: monospace;
}}
.badge.live {{ background: rgba(248, 81, 73, 0.15); color: #f85149; }}
.badge.idle {{ background: rgba(88, 166, 255, 0.15); color: #58a6ff; }}
.info {{ font-size: 0.8rem; color: #94a3b8; font-family: monospace; }}
.stream-container {{
    border: 1px solid #1e2d45; border-radius: 8px; overflow: hidden;
    background: #000; max-width: 100%;
}}
.stream-container img {{
    display: block; max-width: 100%; height: auto;
}}
.reconnect {{
    padding: 2rem; text-align: center; color: #64748b;
    display: none;
}}
</style></head><body>
<div class="header">
    <h1>Thea Live</h1>
    <span class="badge {'live' if recording else 'idle'}">
        {'recording' if recording else 'idle'}
    </span>
    <span class="info">{display} &middot; {display_size}</span>
</div>
<div class="stream-container">
    <img id="stream" src="{stream_path}?fps=5" alt="Live display stream">
    <div class="reconnect" id="reconnect">Reconnecting...</div>
</div>
<script>
var img = document.getElementById('stream');
var msg = document.getElementById('reconnect');
img.onerror = function() {{
    msg.style.display = 'block';
    img.style.display = 'none';
    setTimeout(function() {{
        img.src = '{stream_path}?fps=5&t=' + Date.now();
        img.style.display = 'block';
        msg.style.display = 'none';
    }}, 2000);
}};
</script>
</body></html>"""
        return Response(html, mimetype="text/html")

    def _impl_recording_screenshot(rec, sess_lock, recording_name):
        t = request.args.get("t", type=float)
        if t is None:
            return jsonify({"error": "query parameter 't' (time in seconds) is required"}), 400
        quality = request.args.get("quality", 80, type=int)
        quality = max(1, min(100, quality))
        # Find the video file
        safe = re.sub(r"[^\w\-.]", "_", recording_name)[:120]
        video_path = os.path.join(rec._output_dir, f"{safe}.mp4")
        try:
            data = Recorder.screenshot_from_video(video_path, t, quality=quality)
        except FileNotFoundError:
            return jsonify({"error": f"recording '{recording_name}' not found"}), 404
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500
        return Response(data, mimetype="image/jpeg")

    def _impl_panels_list(rec, sess_lock):
        with sess_lock:
            panels = [
                {"name": n, "title": p["title"], "width": p["width"]}
                for n, p in rec._panels.items()
            ]
        return jsonify(panels), 200

    def _impl_panels_create(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        if not name or not isinstance(name, str) or name.strip() == "":
            return jsonify({"error": "field 'name' is required and must be a non-empty string"}), 400
        title = data.get("title", "")
        width = data.get("width")
        if width is not None:
            if not isinstance(width, int):
                return jsonify({"error": "field 'width' must be an integer"}), 400
            if width <= 0:
                width = None  # treat zero/negative as auto-width
        height = data.get("height")
        if height is not None:
            if not isinstance(height, int):
                return jsonify({"error": "field 'height' must be an integer"}), 400
            if height <= 0:
                return jsonify({"error": "field 'height' must be positive"}), 400
        bg_color = data.get("bg_color")
        if bg_color is not None:
            if not isinstance(bg_color, str) or not re.fullmatch(r"[0-9a-fA-F]{6}", bg_color):
                return jsonify({"error": "field 'bg_color' must be a 6-digit hex colour string (e.g. 'ff0000')"}), 400
        opacity = data.get("opacity")
        if opacity is not None:
            if not isinstance(opacity, (int, float)):
                return jsonify({"error": "field 'opacity' must be a number between 0 and 1"}), 400
            opacity = float(opacity)
            if opacity < 0.0 or opacity > 1.0:
                return jsonify({"error": "field 'opacity' must be between 0.0 and 1.0"}), 400
        with sess_lock:
            warnings = rec.add_panel(name, title=title, width=width, height=height,
                                     bg_color=bg_color, opacity=opacity)
        result = {"name": name, "title": title, "width": width, "height": height,
                  "bg_color": bg_color, "opacity": opacity}
        if warnings:
            result["warnings"] = warnings
        return jsonify(result), 201

    def _impl_panels_update(rec, sess_lock, panel_name):
        with sess_lock:
            if panel_name not in rec._panels:
                return jsonify({"error": f"panel '{panel_name}' not found"}), 404
            data = request.get_json(silent=True) or {}
            text = data.get("text", "")
            focus_line = data.get("focus_line", -1)
            rec.update_panel(panel_name, text, focus_line=focus_line)
        return jsonify({"name": panel_name, "text": text}), 200

    def _impl_panels_delete(rec, sess_lock, panel_name):
        with sess_lock:
            if panel_name not in rec._panels:
                return jsonify({"error": f"panel '{panel_name}' not found"}), 404
            rec.remove_panel(panel_name)
        return jsonify({"status": "removed"}), 200

    def _impl_recording_start(rec, sess_lock, cur_name):
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        if not name or not isinstance(name, str) or name.strip() == "":
            return jsonify({"error": "field 'name' is required and must be a non-empty string"}), 400
        with sess_lock:
            if rec._ffmpeg_proc is not None:
                return jsonify({"error": "already recording"}), 409
            cur_name["name"] = name
            warnings = rec.start_recording(name)
        result = {"status": "recording", "name": name}
        if warnings:
            result["warnings"] = warnings
        return jsonify(result), 201

    def _impl_recording_stop(rec, sess_lock, cur_name):
        with sess_lock:
            if rec._ffmpeg_proc is None:
                return jsonify({"error": "not recording"}), 409
            elapsed = rec.recording_elapsed
            path = rec.stop_recording()
            name = cur_name["name"]
            cur_name["name"] = None
        return jsonify({"path": path, "elapsed": round(elapsed, 2), "name": name}), 200

    def _impl_recording_elapsed(rec, sess_lock):
        with sess_lock:
            elapsed = rec.recording_elapsed
        return jsonify({"elapsed": round(elapsed, 2)}), 200

    def _impl_recording_status(rec, sess_lock, cur_name):
        with sess_lock:
            is_recording = rec._ffmpeg_proc is not None
            name = cur_name["name"] if is_recording else None
            elapsed = round(rec.recording_elapsed, 2)
        return jsonify({"recording": is_recording, "name": name, "elapsed": elapsed}), 200

    def _impl_cleanup(rec, sess_lock, cur_name):
        with sess_lock:
            cur_name["name"] = None
            rec.cleanup()
        return jsonify({"status": "cleaned"}), 200

    def _impl_validate_layout(rec, sess_lock):
        with sess_lock:
            warnings = rec.validate_layout()
        return jsonify({"warnings": warnings, "valid": len(warnings) == 0}), 200

    def _impl_testcard(rec, sess_lock):
        with sess_lock:
            svg = rec.generate_testcard()
        return Response(svg, mimetype="image/svg+xml")

    def _impl_health(rec, sess_lock, uptime):
        with sess_lock:
            is_recording = rec._ffmpeg_proc is not None
            disp = rec.display_string
            panels = list(rec._panels.keys())
        return jsonify({
            "status": "ok",
            "recording": is_recording,
            "display": disp,
            "panels": panels,
            "uptime": round(uptime, 1),
        }), 200

    # -- CORS --------------------------------------------------------------

    if enable_cors:
        @app.after_request
        def add_cors_headers(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response

        @app.before_request
        def handle_options():
            if request.method == "OPTIONS":
                resp = Response("", status=204)
                resp.headers["Access-Control-Allow-Origin"] = "*"
                resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
                return resp

    # -- Request logging ---------------------------------------------------

    @app.before_request
    def log_request_start():
        request._start_time = time.monotonic()

    @app.after_request
    def log_request_end(response):
        elapsed = time.monotonic() - getattr(request, "_start_time", time.monotonic())
        logger.info(
            "%s %s → %s (%.1fms)",
            request.method, request.path, response.status_code,
            elapsed * 1000,
        )
        return response

    # ── Session management ────────────────────────────────────────────────

    @app.route("/sessions", methods=["POST"])
    def sessions_create():
        """Create a new named session with its own display and recorder."""
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        if not name or not isinstance(name, str) or name.strip() == "":
            return jsonify({"error": "field 'name' is required and must be a non-empty string"}), 400
        if name == "default":
            return jsonify({"error": "session name 'default' is reserved"}), 400

        with _sessions_lock:
            if name in _sessions:
                return jsonify({"error": f"session '{name}' already exists"}), 409
            # Accept explicit display number or auto-allocate
            raw_display = data.get("display")
            if raw_display is not None:
                if not isinstance(raw_display, int) or raw_display < 0:
                    return jsonify({"error": "field 'display' must be a non-negative integer"}), 400
                display_num = raw_display
            else:
                display_num = _next_display[0]
                _next_display[0] += 1
            sess = _make_session(display_num)
            _sessions[name] = sess

        return jsonify({"name": name, "display": display_num, "url_prefix": f"/sessions/{name}"}), 201

    @app.route("/sessions", methods=["GET"])
    def sessions_list():
        """List all active sessions."""
        with _sessions_lock:
            result = []
            for sess_name, sess in _sessions.items():
                with sess["lock"]:
                    is_rec = sess["recorder"]._ffmpeg_proc is not None
                    cur = sess["current_name"]["name"]
                result.append({
                    "name": sess_name,
                    "display": sess["display"],
                    "recording": is_rec,
                    "recording_name": cur,
                })
        return jsonify(result), 200

    @app.route("/sessions/<session_name>", methods=["DELETE"])
    def sessions_delete(session_name):
        """Destroy a named session (cleanup + remove)."""
        if session_name == "default":
            return jsonify({"error": "the default session cannot be deleted"}), 400
        with _sessions_lock:
            sess = _sessions.pop(session_name, None)
        if sess is None:
            return jsonify({"error": f"session '{session_name}' not found"}), 404
        _impl_cleanup(sess["recorder"], sess["lock"], sess["current_name"])
        return jsonify({"status": "removed"}), 200

    # ── Session-scoped endpoints (/sessions/<name>/...) ────────────────────

    @app.route("/sessions/<session_name>/display/start", methods=["POST"])
    def sess_display_start(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_display_start(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/display/stop", methods=["POST"])
    def sess_display_stop(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_display_stop(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/display/screenshot")
    def sess_display_screenshot(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_display_screenshot(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/display/stream")
    def sess_display_stream(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_display_stream(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/display/view")
    def sess_display_view(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_display_view(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/panels", methods=["GET"])
    def sess_panels_list(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_panels_list(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/panels", methods=["POST"])
    def sess_panels_create(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_panels_create(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/panels/<panel_name>", methods=["PUT"])
    def sess_panels_update(session_name, panel_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_panels_update(sess["recorder"], sess["lock"], panel_name)

    @app.route("/sessions/<session_name>/panels/<panel_name>", methods=["DELETE"])
    def sess_panels_delete(session_name, panel_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_panels_delete(sess["recorder"], sess["lock"], panel_name)

    @app.route("/sessions/<session_name>/recording/start", methods=["POST"])
    def sess_recording_start(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_recording_start(sess["recorder"], sess["lock"], sess["current_name"])

    @app.route("/sessions/<session_name>/recording/stop", methods=["POST"])
    def sess_recording_stop(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_recording_stop(sess["recorder"], sess["lock"], sess["current_name"])

    @app.route("/sessions/<session_name>/recording/elapsed", methods=["GET"])
    def sess_recording_elapsed(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_recording_elapsed(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/recording/status", methods=["GET"])
    def sess_recording_status(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_recording_status(sess["recorder"], sess["lock"], sess["current_name"])

    @app.route("/sessions/<session_name>/cleanup", methods=["POST"])
    def sess_cleanup(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_cleanup(sess["recorder"], sess["lock"], sess["current_name"])

    @app.route("/sessions/<session_name>/health", methods=["GET"])
    def sess_health(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_health(sess["recorder"], sess["lock"], time.monotonic() - start_time)

    @app.route("/sessions/<session_name>/validate-layout", methods=["GET"])
    def sess_validate_layout(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_validate_layout(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/testcard", methods=["GET"])
    def sess_testcard(session_name):
        sess, err = _session_or_404(session_name)
        if err:
            return err
        return _impl_testcard(sess["recorder"], sess["lock"])

    # ── Default session endpoints (backward-compatible) ───────────────────

    @app.route("/display/start", methods=["POST"])
    def display_start():
        return _impl_display_start(recorder, lock)

    @app.route("/display/stop", methods=["POST"])
    def display_stop():
        return _impl_display_stop(recorder, lock)

    @app.route("/display/screenshot")
    def display_screenshot():
        return _impl_display_screenshot(recorder, lock)

    @app.route("/display/stream")
    def display_stream():
        return _impl_display_stream(recorder, lock)

    @app.route("/display/view")
    def display_view():
        return _impl_display_view(recorder, lock)

    @app.route("/panels", methods=["GET"])
    def panels_list():
        return _impl_panels_list(recorder, lock)

    @app.route("/panels", methods=["POST"])
    def panels_create():
        return _impl_panels_create(recorder, lock)

    @app.route("/panels/<name>", methods=["PUT"])
    def panels_update(name):
        return _impl_panels_update(recorder, lock, name)

    @app.route("/panels/<name>", methods=["DELETE"])
    def panels_delete(name):
        return _impl_panels_delete(recorder, lock, name)

    @app.route("/recording/start", methods=["POST"])
    def recording_start():
        return _impl_recording_start(recorder, lock, current_recording_name)

    @app.route("/recording/stop", methods=["POST"])
    def recording_stop():
        return _impl_recording_stop(recorder, lock, current_recording_name)

    @app.route("/recording/elapsed", methods=["GET"])
    def recording_elapsed():
        return _impl_recording_elapsed(recorder, lock)

    @app.route("/recording/status", methods=["GET"])
    def recording_status():
        return _impl_recording_status(recorder, lock, current_recording_name)

    # -- File access endpoints (shared across all sessions) ----------------

    @app.route("/recordings", methods=["GET"])
    def recordings_list():
        return jsonify(_list_mp4s()), 200

    @app.route("/recordings/<name>", methods=["GET"])
    def recordings_download(name):
        if not _safe_recording_name(name):
            return jsonify({"error": "invalid recording name"}), 400
        path = _resolve_recording_path(name)
        if not path:
            return jsonify({"error": f"recording '{name}' not found"}), 404

        file_size = os.path.getsize(path)
        range_header = request.headers.get("Range")

        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if not match:
                return jsonify({"error": "invalid Range header"}), 416
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1
            end = min(end, file_size - 1)
            if start > end or start >= file_size:
                return jsonify({"error": "range not satisfiable"}), 416
            length = end - start + 1
            with open(path, "rb") as f:
                f.seek(start)
                data = f.read(length)
            resp = Response(
                data,
                status=206,
                mimetype="video/mp4",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(length),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": f'attachment; filename="{os.path.basename(path)}"',
                },
            )
            return resp

        return send_file(
            path,
            mimetype="video/mp4",
            as_attachment=True,
            download_name=os.path.basename(path),
        )

    @app.route("/recordings/<name>/screenshot", methods=["GET"])
    def recordings_screenshot(name):
        if not _safe_recording_name(name):
            return jsonify({"error": "invalid recording name"}), 400
        return _impl_recording_screenshot(recorder, lock, name)

    @app.route("/recordings/<name>/info", methods=["GET"])
    def recordings_info(name):
        if not _safe_recording_name(name):
            return jsonify({"error": "invalid recording name"}), 400
        path = _resolve_recording_path(name)
        if not path:
            return jsonify({"error": f"recording '{name}' not found"}), 404
        stat = os.stat(path)
        return jsonify({
            "name": name,
            "path": path,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
        }), 200

    # -- Utility endpoints -------------------------------------------------

    @app.route("/health", methods=["GET"])
    def health():
        return _impl_health(recorder, lock, time.monotonic() - start_time)

    @app.route("/validate-layout", methods=["GET"])
    def validate_layout():
        return _impl_validate_layout(recorder, lock)

    @app.route("/testcard", methods=["GET"])
    def testcard():
        return _impl_testcard(recorder, lock)

    @app.route("/cleanup", methods=["POST"])
    def cleanup():
        return _impl_cleanup(recorder, lock, current_recording_name)

    # ── Composition endpoints ─────────────────────────────────────────────

    _composer = CompositionManager(output_dir)

    @app.route("/compositions", methods=["POST"])
    def compositions_create():
        """Create and render a composed video from multiple recordings."""
        data = request.get_json(silent=True) or {}

        name = data.get("name")
        if not name or not isinstance(name, str) or name.strip() == "":
            return jsonify({"error": "field 'name' is required and must be a non-empty string"}), 400

        recordings = data.get("recordings")
        if not recordings or not isinstance(recordings, list) or len(recordings) < 1:
            return jsonify({"error": "field 'recordings' must be a non-empty list of recording names"}), 400

        for rec_name in recordings:
            if not isinstance(rec_name, str) or not rec_name.strip():
                return jsonify({"error": "each recording name must be a non-empty string"}), 400

        layout = data.get("layout", "row")
        if layout not in ("row", "column", "grid"):
            return jsonify({"error": "field 'layout' must be 'row', 'column', or 'grid'"}), 400

        labels = data.get("labels", True)
        highlight_color = data.get("highlight_color", "00d4aa")
        highlight_width = data.get("highlight_width", 6)

        # Parse inline highlights.
        highlights = []
        for h in data.get("highlights", []):
            rec = h.get("recording")
            t = h.get("time")
            dur = h.get("duration", 1.0)
            if not rec or t is None:
                return jsonify({"error": "each highlight needs 'recording' and 'time'"}), 400
            highlights.append(Highlight(recording=rec, time=float(t), duration=float(dur)))

        spec = CompositionSpec(
            name=name,
            recordings=recordings,
            layout=layout,
            labels=bool(labels),
            highlights=highlights,
            highlight_color=str(highlight_color),
            highlight_width=int(highlight_width),
        )

        try:
            result = _composer.create(spec)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409

        return jsonify(result.to_dict()), 202

    @app.route("/compositions", methods=["GET"])
    def compositions_list():
        """List all compositions."""
        return jsonify(_composer.list_all()), 200

    @app.route("/compositions/<comp_name>", methods=["GET"])
    def compositions_get(comp_name):
        """Get composition status."""
        got = _composer.get(comp_name)
        if got is None:
            return jsonify({"error": f"composition '{comp_name}' not found"}), 404
        spec, result = got
        return jsonify({**result.to_dict(), **spec.to_dict()}), 200

    @app.route("/compositions/<comp_name>", methods=["DELETE"])
    def compositions_delete(comp_name):
        """Delete a composition."""
        if _composer.delete(comp_name):
            return jsonify({"status": "removed"}), 200
        return jsonify({"error": f"composition '{comp_name}' not found"}), 404

    @app.route("/compositions/<comp_name>/highlights", methods=["POST"])
    def compositions_add_highlight(comp_name):
        """Add a highlight event to a composition."""
        data = request.get_json(silent=True) or {}
        rec = data.get("recording")
        t = data.get("time")
        dur = data.get("duration", 1.0)
        if not rec or t is None:
            return jsonify({"error": "fields 'recording' and 'time' are required"}), 400
        try:
            _composer.add_highlight(
                comp_name, Highlight(recording=rec, time=float(t), duration=float(dur)),
            )
        except KeyError:
            return jsonify({"error": f"composition '{comp_name}' not found"}), 404
        return jsonify({"status": "added"}), 201

    @app.route("/compositions/<comp_name>/highlights", methods=["GET"])
    def compositions_list_highlights(comp_name):
        """List highlights for a composition."""
        got = _composer.get(comp_name)
        if got is None:
            return jsonify({"error": f"composition '{comp_name}' not found"}), 404
        spec, _ = got
        return jsonify([
            {"recording": h.recording, "time": h.time, "duration": h.duration}
            for h in spec.highlights
        ]), 200

    # Expose for testing
    app._composer = _composer

    # ── Director endpoints ─────────────────────────────────────────────────

    def _impl_director_mouse_move(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        x = data.get("x")
        y = data.get("y")
        if x is None or y is None:
            return jsonify({"error": "fields 'x' and 'y' are required"}), 400
        duration = data.get("duration")
        target_width = data.get("target_width")
        with sess_lock:
            rec.director.mouse.move_to(int(x), int(y), duration=duration, target_width=target_width)
        return jsonify({"status": "ok", "x": int(x), "y": int(y)}), 200

    def _impl_director_mouse_click(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        x = data.get("x")
        y = data.get("y")
        button = data.get("button", 1)
        duration = data.get("duration")
        with sess_lock:
            rec.director.mouse.click(
                int(x) if x is not None else None,
                int(y) if y is not None else None,
                button=int(button),
                duration=duration,
            )
        return jsonify({"status": "ok"}), 200

    def _impl_director_mouse_double_click(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        x = data.get("x")
        y = data.get("y")
        duration = data.get("duration")
        with sess_lock:
            rec.director.mouse.double_click(
                int(x) if x is not None else None,
                int(y) if y is not None else None,
                duration=duration,
            )
        return jsonify({"status": "ok"}), 200

    def _impl_director_mouse_right_click(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        x = data.get("x")
        y = data.get("y")
        duration = data.get("duration")
        with sess_lock:
            rec.director.mouse.right_click(
                int(x) if x is not None else None,
                int(y) if y is not None else None,
                duration=duration,
            )
        return jsonify({"status": "ok"}), 200

    def _impl_director_mouse_drag(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        for field in ("start_x", "start_y", "end_x", "end_y"):
            if data.get(field) is None:
                return jsonify({"error": f"field '{field}' is required"}), 400
        button = data.get("button", 1)
        duration = data.get("duration")
        with sess_lock:
            rec.director.mouse.drag(
                int(data["start_x"]), int(data["start_y"]),
                int(data["end_x"]), int(data["end_y"]),
                button=int(button), duration=duration,
            )
        return jsonify({"status": "ok"}), 200

    def _impl_director_mouse_scroll(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        clicks = data.get("clicks")
        if clicks is None:
            return jsonify({"error": "field 'clicks' is required"}), 400
        x = data.get("x")
        y = data.get("y")
        with sess_lock:
            rec.director.mouse.scroll(
                int(clicks),
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
            )
        return jsonify({"status": "ok"}), 200

    def _impl_director_mouse_position(rec, sess_lock):
        with sess_lock:
            x, y = rec.director.mouse.position()
        return jsonify({"x": x, "y": y}), 200

    def _impl_director_keyboard_type(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        text = data.get("text")
        if text is None:
            return jsonify({"error": "field 'text' is required"}), 400
        wpm = data.get("wpm")
        with sess_lock:
            rec.director.keyboard.type(str(text), wpm=wpm)
        return jsonify({"status": "ok"}), 200

    def _impl_director_keyboard_press(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        keys = data.get("keys")
        if not keys or not isinstance(keys, list):
            return jsonify({"error": "field 'keys' must be a non-empty list of key names"}), 400
        with sess_lock:
            rec.director.keyboard.press(*keys)
        return jsonify({"status": "ok"}), 200

    def _impl_director_keyboard_hold(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        key = data.get("key")
        if not key:
            return jsonify({"error": "field 'key' is required"}), 400
        with sess_lock:
            rec.director.keyboard.hold(str(key))
        return jsonify({"status": "ok"}), 200

    def _impl_director_keyboard_release(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        key = data.get("key")
        if not key:
            return jsonify({"error": "field 'key' is required"}), 400
        with sess_lock:
            rec.director.keyboard.release(str(key))
        return jsonify({"status": "ok"}), 200

    def _impl_director_window_find(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        class_name = data.get("class")
        if not name and not class_name:
            return jsonify({"error": "field 'name' or 'class' is required"}), 400
        timeout = data.get("timeout", 10.0)
        with sess_lock:
            try:
                if class_name:
                    win = rec.director.window_by_class(str(class_name), timeout=float(timeout))
                else:
                    win = rec.director.window(str(name), timeout=float(timeout))
            except RuntimeError as e:
                return jsonify({"error": str(e)}), 404
        return jsonify({"window_id": win.id}), 200

    def _impl_director_window_focus(rec, sess_lock, window_id):
        from .director.window import Window
        with sess_lock:
            Window(window_id, rec.director.env).focus()
        return jsonify({"status": "ok"}), 200

    def _impl_director_window_move(rec, sess_lock, window_id):
        data = request.get_json(silent=True) or {}
        x = data.get("x")
        y = data.get("y")
        if x is None or y is None:
            return jsonify({"error": "fields 'x' and 'y' are required"}), 400
        from .director.window import Window
        with sess_lock:
            Window(window_id, rec.director.env).move(int(x), int(y))
        return jsonify({"status": "ok"}), 200

    def _impl_director_window_resize(rec, sess_lock, window_id):
        data = request.get_json(silent=True) or {}
        width = data.get("width")
        height = data.get("height")
        if width is None or height is None:
            return jsonify({"error": "fields 'width' and 'height' are required"}), 400
        from .director.window import Window
        with sess_lock:
            Window(window_id, rec.director.env).resize(int(width), int(height))
        return jsonify({"status": "ok"}), 200

    def _impl_director_window_minimize(rec, sess_lock, window_id):
        from .director.window import Window
        with sess_lock:
            Window(window_id, rec.director.env).minimize()
        return jsonify({"status": "ok"}), 200

    def _impl_director_window_geometry(rec, sess_lock, window_id):
        from .director.window import Window
        with sess_lock:
            x, y, w, h = Window(window_id, rec.director.env).geometry
        return jsonify({"x": x, "y": y, "width": w, "height": h}), 200

    def _impl_director_window_tile(rec, sess_lock):
        data = request.get_json(silent=True) or {}
        window_ids = data.get("window_ids")
        if not window_ids or not isinstance(window_ids, list):
            return jsonify({"error": "field 'window_ids' must be a non-empty list"}), 400
        layout = data.get("layout", "side-by-side")
        bounds = data.get("bounds")
        from .director.window import Window, tile as tile_windows
        with sess_lock:
            windows = [Window(wid, rec.director.env) for wid in window_ids]
            tile_windows(
                windows, layout,
                bounds=tuple(bounds) if bounds else None,
            )
        return jsonify({"status": "ok"}), 200

    # -- Director: default session routes --

    @app.route("/director/mouse/move", methods=["POST"])
    def director_mouse_move():
        return _impl_director_mouse_move(recorder, lock)

    @app.route("/director/mouse/click", methods=["POST"])
    def director_mouse_click():
        return _impl_director_mouse_click(recorder, lock)

    @app.route("/director/mouse/double-click", methods=["POST"])
    def director_mouse_double_click():
        return _impl_director_mouse_double_click(recorder, lock)

    @app.route("/director/mouse/right-click", methods=["POST"])
    def director_mouse_right_click():
        return _impl_director_mouse_right_click(recorder, lock)

    @app.route("/director/mouse/drag", methods=["POST"])
    def director_mouse_drag():
        return _impl_director_mouse_drag(recorder, lock)

    @app.route("/director/mouse/scroll", methods=["POST"])
    def director_mouse_scroll():
        return _impl_director_mouse_scroll(recorder, lock)

    @app.route("/director/mouse/position", methods=["GET"])
    def director_mouse_position():
        return _impl_director_mouse_position(recorder, lock)

    @app.route("/director/keyboard/type", methods=["POST"])
    def director_keyboard_type():
        return _impl_director_keyboard_type(recorder, lock)

    @app.route("/director/keyboard/press", methods=["POST"])
    def director_keyboard_press():
        return _impl_director_keyboard_press(recorder, lock)

    @app.route("/director/keyboard/hold", methods=["POST"])
    def director_keyboard_hold():
        return _impl_director_keyboard_hold(recorder, lock)

    @app.route("/director/keyboard/release", methods=["POST"])
    def director_keyboard_release():
        return _impl_director_keyboard_release(recorder, lock)

    @app.route("/director/window/find", methods=["POST"])
    def director_window_find():
        return _impl_director_window_find(recorder, lock)

    @app.route("/director/window/<window_id>/focus", methods=["POST"])
    def director_window_focus(window_id):
        return _impl_director_window_focus(recorder, lock, window_id)

    @app.route("/director/window/<window_id>/move", methods=["POST"])
    def director_window_move(window_id):
        return _impl_director_window_move(recorder, lock, window_id)

    @app.route("/director/window/<window_id>/resize", methods=["POST"])
    def director_window_resize(window_id):
        return _impl_director_window_resize(recorder, lock, window_id)

    @app.route("/director/window/<window_id>/minimize", methods=["POST"])
    def director_window_minimize(window_id):
        return _impl_director_window_minimize(recorder, lock, window_id)

    @app.route("/director/window/<window_id>/geometry", methods=["GET"])
    def director_window_geometry(window_id):
        return _impl_director_window_geometry(recorder, lock, window_id)

    @app.route("/director/window/tile", methods=["POST"])
    def director_window_tile():
        return _impl_director_window_tile(recorder, lock)

    # -- Director: session-scoped routes --

    @app.route("/sessions/<session_name>/director/mouse/move", methods=["POST"])
    def sess_director_mouse_move(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_mouse_move(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/mouse/click", methods=["POST"])
    def sess_director_mouse_click(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_mouse_click(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/mouse/double-click", methods=["POST"])
    def sess_director_mouse_double_click(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_mouse_double_click(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/mouse/right-click", methods=["POST"])
    def sess_director_mouse_right_click(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_mouse_right_click(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/mouse/drag", methods=["POST"])
    def sess_director_mouse_drag(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_mouse_drag(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/mouse/scroll", methods=["POST"])
    def sess_director_mouse_scroll(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_mouse_scroll(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/mouse/position", methods=["GET"])
    def sess_director_mouse_position(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_mouse_position(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/keyboard/type", methods=["POST"])
    def sess_director_keyboard_type(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_keyboard_type(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/keyboard/press", methods=["POST"])
    def sess_director_keyboard_press(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_keyboard_press(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/keyboard/hold", methods=["POST"])
    def sess_director_keyboard_hold(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_keyboard_hold(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/keyboard/release", methods=["POST"])
    def sess_director_keyboard_release(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_keyboard_release(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/window/find", methods=["POST"])
    def sess_director_window_find(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_window_find(sess["recorder"], sess["lock"])

    @app.route("/sessions/<session_name>/director/window/<window_id>/focus", methods=["POST"])
    def sess_director_window_focus(session_name, window_id):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_window_focus(sess["recorder"], sess["lock"], window_id)

    @app.route("/sessions/<session_name>/director/window/<window_id>/move", methods=["POST"])
    def sess_director_window_move(session_name, window_id):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_window_move(sess["recorder"], sess["lock"], window_id)

    @app.route("/sessions/<session_name>/director/window/<window_id>/resize", methods=["POST"])
    def sess_director_window_resize(session_name, window_id):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_window_resize(sess["recorder"], sess["lock"], window_id)

    @app.route("/sessions/<session_name>/director/window/<window_id>/minimize", methods=["POST"])
    def sess_director_window_minimize(session_name, window_id):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_window_minimize(sess["recorder"], sess["lock"], window_id)

    @app.route("/sessions/<session_name>/director/window/<window_id>/geometry", methods=["GET"])
    def sess_director_window_geometry(session_name, window_id):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_window_geometry(sess["recorder"], sess["lock"], window_id)

    @app.route("/sessions/<session_name>/director/window/tile", methods=["POST"])
    def sess_director_window_tile(session_name):
        sess, err = _session_or_404(session_name)
        return err if err else _impl_director_window_tile(sess["recorder"], sess["lock"])

    # -- Graceful shutdown -------------------------------------------------

    def _shutdown_handler(signum, frame):
        logger.info("Received signal %s, cleaning up…", signum)
        with _sessions_lock:
            for sess in _sessions.values():
                with sess["lock"]:
                    sess["recorder"].cleanup()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown_handler)

    # Expose internals for testing
    app._recorder = recorder
    app._lock = lock
    app._current_recording_name = current_recording_name
    app._sessions = _sessions
    app._sessions_lock = _sessions_lock

    return app
