"""HTTP server wrapping one or more named Recorder sessions.

Each session has its own Xvfb display, ffmpeg process, and panel set —
browsers in different sessions are completely isolated from each other.

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

from .recorder import Recorder

logger = logging.getLogger("recorder.server")


def create_app(
    output_dir: str = "/tmp/recordings",
    display: int = 99,
    browser_size: str = "1920x1080",
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
                browser_size=browser_size,
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
        with sess_lock:
            if rec._xvfb_proc is not None:
                return jsonify({"error": "display already started"}), 409
            rec.start_display()
            return jsonify({"status": "started", "display": rec.display_string}), 201

    def _impl_display_stop(rec, sess_lock):
        with sess_lock:
            rec.stop_display()
            return jsonify({"status": "stopped"}), 200

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
            if not isinstance(width, int) or width <= 0:
                return jsonify({"error": "field 'width' must be a positive integer"}), 400
        with sess_lock:
            rec.add_panel(name, title=title, width=width)
        return jsonify({"name": name, "title": title, "width": width}), 201

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
            rec.start_recording(name)
        return jsonify({"status": "recording", "name": name}), 201

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

    # ── Default session endpoints (backward-compatible) ───────────────────

    @app.route("/display/start", methods=["POST"])
    def display_start():
        return _impl_display_start(recorder, lock)

    @app.route("/display/stop", methods=["POST"])
    def display_stop():
        return _impl_display_stop(recorder, lock)

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

    @app.route("/cleanup", methods=["POST"])
    def cleanup():
        return _impl_cleanup(recorder, lock, current_recording_name)

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
