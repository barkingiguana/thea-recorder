"""HTTP server wrapping a single Recorder instance.

Provides a REST API for display management, panel control, recording
lifecycle, and file downloads.  Designed to be consumed by SDKs in any
language or directly via curl.

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

    recorder = Recorder(
        output_dir=output_dir,
        display=display,
        browser_size=browser_size,
        framerate=framerate,
    )

    lock = threading.Lock()
    start_time = time.monotonic()
    current_recording_name: dict = {"name": None}

    # -- Helpers -----------------------------------------------------------

    def locked(f):
        """Decorator that acquires the recorder lock for the duration."""
        @wraps(f)
        def wrapper(*args, **kwargs):
            with lock:
                return f(*args, **kwargs)
        return wrapper

    def _safe_recording_name(name: str) -> bool:
        """Reject path traversal attempts."""
        return ".." not in name and "/" not in name and "\\" not in name and name.strip() != ""

    def _resolve_recording_path(name: str) -> str | None:
        """Resolve a recording name to a file path, or None."""
        safe = re.sub(r"[^\w\-.]", "_", name)[:120]
        path = os.path.join(output_dir, f"{safe}.mp4")
        if os.path.isfile(path):
            return path
        return None

    def _list_mp4s() -> list[dict]:
        """List all MP4 files in the output directory."""
        os.makedirs(output_dir, exist_ok=True)
        result = []
        for fname in sorted(os.listdir(output_dir)):
            if not fname.endswith(".mp4"):
                continue
            fpath = os.path.join(output_dir, fname)
            stat = os.stat(fpath)
            result.append({
                "name": fname[:-4],  # strip .mp4
                "path": fpath,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
            })
        return result

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

    # -- Display endpoints -------------------------------------------------

    @app.route("/display/start", methods=["POST"])
    @locked
    def display_start():
        if recorder._xvfb_proc is not None:
            return jsonify({"error": "display already started"}), 409
        recorder.start_display()
        return jsonify({"status": "started", "display": recorder.display_string}), 201

    @app.route("/display/stop", methods=["POST"])
    @locked
    def display_stop():
        recorder.stop_display()
        return jsonify({"status": "stopped"}), 200

    # -- Panel endpoints ---------------------------------------------------

    @app.route("/panels", methods=["GET"])
    @locked
    def panels_list():
        panels = [
            {"name": name, "title": p["title"], "width": p["width"]}
            for name, p in recorder._panels.items()
        ]
        return jsonify(panels), 200

    @app.route("/panels", methods=["POST"])
    @locked
    def panels_create():
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        if not name or not isinstance(name, str) or name.strip() == "":
            return jsonify({"error": "field 'name' is required and must be a non-empty string"}), 400
        title = data.get("title", "")
        width = data.get("width")
        if width is not None:
            if not isinstance(width, int) or width <= 0:
                return jsonify({"error": "field 'width' must be a positive integer"}), 400
        recorder.add_panel(name, title=title, width=width)
        return jsonify({"name": name, "title": title, "width": width}), 201

    @app.route("/panels/<name>", methods=["PUT"])
    @locked
    def panels_update(name):
        if name not in recorder._panels:
            return jsonify({"error": f"panel '{name}' not found"}), 404
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
        focus_line = data.get("focus_line", -1)
        recorder.update_panel(name, text, focus_line=focus_line)
        return jsonify({"name": name, "text": text}), 200

    @app.route("/panels/<name>", methods=["DELETE"])
    @locked
    def panels_delete(name):
        if name not in recorder._panels:
            return jsonify({"error": f"panel '{name}' not found"}), 404
        recorder.remove_panel(name)
        return jsonify({"status": "removed"}), 200

    # -- Recording endpoints -----------------------------------------------

    @app.route("/recording/start", methods=["POST"])
    @locked
    def recording_start():
        if recorder._ffmpeg_proc is not None:
            return jsonify({"error": "already recording"}), 409
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        if not name or not isinstance(name, str) or name.strip() == "":
            return jsonify({"error": "field 'name' is required and must be a non-empty string"}), 400
        current_recording_name["name"] = name
        recorder.start_recording(name)
        return jsonify({"status": "recording", "name": name}), 201

    @app.route("/recording/stop", methods=["POST"])
    @locked
    def recording_stop():
        if recorder._ffmpeg_proc is None:
            return jsonify({"error": "not recording"}), 409
        elapsed = recorder.recording_elapsed
        path = recorder.stop_recording()
        name = current_recording_name["name"]
        current_recording_name["name"] = None
        return jsonify({"path": path, "elapsed": round(elapsed, 2), "name": name}), 200

    @app.route("/recording/elapsed", methods=["GET"])
    @locked
    def recording_elapsed():
        return jsonify({"elapsed": round(recorder.recording_elapsed, 2)}), 200

    @app.route("/recording/status", methods=["GET"])
    @locked
    def recording_status():
        is_recording = recorder._ffmpeg_proc is not None
        return jsonify({
            "recording": is_recording,
            "name": current_recording_name["name"] if is_recording else None,
            "elapsed": round(recorder.recording_elapsed, 2),
        }), 200

    # -- File access endpoints ---------------------------------------------

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

        # Support Range requests for video seeking
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
    @locked
    def health():
        return jsonify({
            "status": "ok",
            "recording": recorder._ffmpeg_proc is not None,
            "display": recorder.display_string,
            "panels": list(recorder._panels.keys()),
            "uptime": round(time.monotonic() - start_time, 1),
        }), 200

    @app.route("/cleanup", methods=["POST"])
    @locked
    def cleanup():
        current_recording_name["name"] = None
        recorder.cleanup()
        return jsonify({"status": "cleaned"}), 200

    # -- Graceful shutdown -------------------------------------------------

    def _shutdown_handler(signum, frame):
        logger.info("Received signal %s, cleaning up...", signum)
        with lock:
            recorder.cleanup()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown_handler)

    # Store recorder on app for testing
    app._recorder = recorder
    app._lock = lock
    app._current_recording_name = current_recording_name

    return app
