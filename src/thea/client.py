"""RecorderClient — stdlib-only HTTP client for thea-recorder."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any, Generator, Optional


class RecorderError(Exception):
    """Raised when the recorder server returns an error or is unreachable."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RecordingResult:
    """Result of a completed recording session.

    Returned by the :meth:`RecorderClient.recording` context manager
    after the ``with`` block exits.

    Attributes
    ----------
    name:    Recording name passed to ``start_recording``.
    path:    Absolute path to the saved MP4 file on the server.
    elapsed: Duration of the recording in seconds.
    """

    def __init__(self) -> None:
        self.name: str | None = None
        self.path: str | None = None
        self.elapsed: float | None = None

    def __repr__(self) -> str:
        return f"RecordingResult(name={self.name!r}, path={self.path!r}, elapsed={self.elapsed})"


class CompositionHelper:
    """Accumulates highlights for a composition being built.

    Created by :meth:`RecorderClient.composed_recording`; not intended
    to be instantiated directly.

    Attributes
    ----------
    result:
        Set to the final composition status dict after the context
        manager exits.  *None* while the ``with`` block is running.
    """

    def __init__(self) -> None:
        self.recording_start: float = time.monotonic()
        self.highlights: list[dict[str, Any]] = []
        self.result: dict[str, Any] | None = None

    def highlight(self, recording: str, duration: float = 1.0) -> None:
        """Record a timestamped highlight event.

        Parameters
        ----------
        recording:
            Name of the recording this highlight applies to.
        duration:
            Duration of the highlight in seconds.
        """
        elapsed = time.monotonic() - self.recording_start
        self.highlights.append({
            "recording": recording,
            "time": elapsed,
            "duration": duration,
        })


class RecorderClient:
    """Synchronous HTTP client for the thea-recorder server.

    Parameters
    ----------
    url:
        Base URL of the recorder server (e.g. ``http://localhost:8080``).
        Falls back to the ``THEA_URL`` environment variable.
    timeout:
        Default request timeout in seconds.
    """

    def __init__(
        self,
        url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        resolved = url or os.environ.get("THEA_URL") or "http://localhost:9123"
        self.base_url: str = resolved.rstrip("/")
        self.timeout: float = timeout
        self._session_prefix: str = ""  # empty = default session
        self._ready: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}{self._session_prefix}{path}"

    def _ensure_ready(self) -> None:
        if not self._ready:
            self.wait_until_ready()
            self._ready = True

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a JSON request and return the decoded response body."""
        if path != "/health":
            self._ensure_ready()
        data: bytes | None = None
        headers: dict[str, str] = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            self._url(path),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(
                req, timeout=timeout or self.timeout
            ) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                msg = detail.get("error", str(detail))
            except Exception:
                msg = exc.reason
            raise RecorderError(msg, status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise RecorderError(f"Connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RecorderError("Request timed out") from exc

    def _request_raw(
        self,
        method: str,
        path: str,
        *,
        timeout: float | None = None,
    ) -> bytes:
        """Send a request and return the raw bytes of the response body."""
        self._ensure_ready()
        req = urllib.request.Request(self._url(path), method=method)
        try:
            with urllib.request.urlopen(
                req, timeout=timeout or self.timeout
            ) as resp:
                return resp.read()  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                msg = detail.get("error", str(detail))
            except Exception:
                msg = exc.reason
            raise RecorderError(msg, status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise RecorderError(f"Connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RecorderError("Request timed out") from exc

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def start_display(self, display_size: str | None = None) -> dict[str, Any]:
        """POST /display/start — start the virtual display.

        Parameters
        ----------
        display_size:
            Override the display resolution for this session (``WxH``).
            *None* uses the server's default.
        """
        body: dict[str, Any] | None = None
        if display_size is not None:
            body = {"display_size": display_size}
        return self._request("POST", "/display/start", body)

    def stop_display(self) -> dict[str, Any]:
        """POST /display/stop — stop the virtual display."""
        return self._request("POST", "/display/stop")

    def display_screenshot(self, *, quality: int = 80) -> bytes:
        """GET /display/screenshot — capture a JPEG screenshot of the live display.

        Parameters
        ----------
        quality:
            JPEG quality (1-100, default 80).

        Returns
        -------
        bytes
            JPEG image data.
        """
        return self._request_raw("GET", f"/display/screenshot?quality={quality}")

    def display_stream_url(self, *, fps: int = 5) -> str:
        """Return the URL for the live MJPEG stream.

        Parameters
        ----------
        fps:
            Frames per second for the stream (1-15, default 5).

        Returns
        -------
        str
            Full URL to the MJPEG stream endpoint.
        """
        return f"{self.base_url}{self._session_prefix}/display/stream?fps={fps}"

    def display_viewer_url(self) -> str:
        """Return the URL for the HTML live viewer page.

        Returns
        -------
        str
            Full URL to the viewer page.
        """
        return f"{self.base_url}{self._session_prefix}/display/view"

    # ------------------------------------------------------------------
    # Panels
    # ------------------------------------------------------------------

    def add_panel(
        self,
        name: str,
        title: str,
        width: int | None = None,
        height: int | None = None,
        bg_color: str | None = None,
        opacity: float | None = None,
    ) -> dict[str, Any]:
        """POST /panels — create a new panel.

        Parameters
        ----------
        name:
            Unique panel identifier.
        title:
            Bold heading for the panel.
        width:
            Fixed width in pixels (*None* = auto).
        height:
            Panel height in pixels (*None* = use bar height default).
        bg_color:
            Background colour as a hex string (e.g. ``"1a1a2e"``).
            *None* uses the recorder default.
        opacity:
            Background opacity from 0.0 (transparent) to 1.0 (opaque).
            *None* uses the recorder default.

        Returns
        -------
        dict
            Response including optional ``warnings`` list.
        """
        body: dict[str, Any] = {"name": name, "title": title}
        if width is not None:
            body["width"] = width
        if height is not None:
            body["height"] = height
        if bg_color is not None:
            body["bg_color"] = bg_color
        if opacity is not None:
            body["opacity"] = opacity
        return self._request("POST", "/panels", body)

    def update_panel(
        self,
        name: str,
        text: str,
        focus_line: int | None = None,
    ) -> dict[str, Any]:
        """PUT /panels/{name} — update panel content."""
        body: dict[str, Any] = {"text": text}
        if focus_line is not None:
            body["focus_line"] = focus_line
        return self._request("PUT", f"/panels/{name}", body)

    def remove_panel(self, name: str) -> dict[str, Any]:
        """DELETE /panels/{name} — remove a panel."""
        return self._request("DELETE", f"/panels/{name}")

    def list_panels(self) -> dict[str, Any]:
        """GET /panels — list all panels."""
        return self._request("GET", "/panels")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def start_recording(self, name: str) -> dict[str, Any]:
        """POST /recording/start — begin recording."""
        return self._request("POST", "/recording/start", {"name": name})

    def stop_recording(self) -> dict[str, Any]:
        """POST /recording/stop — stop current recording.

        Returns dict with ``path``, ``elapsed``, and ``name``.
        """
        return self._request("POST", "/recording/stop")

    def recording_elapsed(self) -> dict[str, Any]:
        """GET /recording/elapsed — seconds elapsed for current recording."""
        return self._request("GET", "/recording/elapsed")

    def recording_status(self) -> dict[str, Any]:
        """GET /recording/status — full recording status."""
        return self._request("GET", "/recording/status")

    # ------------------------------------------------------------------
    # Recordings archive
    # ------------------------------------------------------------------

    def list_recordings(self) -> list[dict[str, Any]]:
        """GET /recordings — list all saved recordings."""
        result = self._request("GET", "/recordings")
        # The server returns a JSON array at the top level.
        if isinstance(result, list):
            return result  # type: ignore[return-value]
        return []

    def download_recording(self, name: str, path: str) -> str:
        """GET /recordings/{name} — download an MP4 to *path*.

        Returns the path written to.
        """
        data = self._request_raw("GET", f"/recordings/{name}")
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def recording_info(self, name: str) -> dict[str, Any]:
        """GET /recordings/{name}/info — metadata for a recording."""
        return self._request("GET", f"/recordings/{name}/info")

    def recording_screenshot(
        self, name: str, time_offset: float, *, quality: int = 80
    ) -> bytes:
        """GET /recordings/{name}/screenshot?t=...&quality=... — extract a frame.

        Parameters
        ----------
        name:
            Recording name.
        time_offset:
            Time offset in seconds into the video.
        quality:
            JPEG quality (1-100, default 80).

        Returns
        -------
        bytes
            JPEG image data.
        """
        params = f"?t={time_offset:.3f}&quality={quality}"
        return self._request_raw("GET", f"/recordings/{name}/screenshot{params}")

    # ------------------------------------------------------------------
    # Health / cleanup
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """GET /health — server health check."""
        return self._request("GET", "/health")

    def cleanup(self) -> dict[str, Any]:
        """POST /cleanup — remove temporary resources."""
        return self._request("POST", "/cleanup")

    # ------------------------------------------------------------------
    # Layout validation
    # ------------------------------------------------------------------

    def validate_layout(self) -> dict[str, Any]:
        """GET /validate-layout — validate the current panel layout.

        Returns
        -------
        dict
            ``{"warnings": [...], "valid": bool}``
        """
        return self._request("GET", "/validate-layout")

    def testcard(self) -> str:
        """GET /testcard — generate an SVG testcard of the current layout.

        Returns
        -------
        str
            SVG markup.
        """
        return self._request_raw("GET", "/testcard").decode("utf-8")

    # ------------------------------------------------------------------
    # Session management (parallel recordings)
    # ------------------------------------------------------------------

    def create_session(
        self, name: str, display: int | None = None
    ) -> dict[str, Any]:
        """POST /sessions — create a new named recording session.

        Each session gets its own Xvfb display, ffmpeg process, and panel
        set, so multiple applications can be recorded fully independently from
        a single server.

        Parameters
        ----------
        name:
            Unique session identifier.
        display:
            Explicit X11 display number.  *None* lets the server
            auto-allocate the next free display.

        Returns
        -------
        dict
            ``{"name": ..., "display": ..., "url_prefix": ...}``
        """
        body: dict[str, Any] = {"name": name}
        if display is not None:
            body["display"] = display
        return self._request("POST", "/sessions", body)

    def use_session(self, name: str) -> None:
        """Route all subsequent calls through a named session.

        After calling ``use_session("alice")``, methods like
        ``start_display()``, ``add_panel()``, ``start_recording()``, etc.
        operate on the *alice* session's isolated display and recorder.

        Call ``use_session("")`` or ``use_default_session()`` to switch
        back to the default session.
        """
        if name:
            self._session_prefix = f"/sessions/{name}"
        else:
            self._session_prefix = ""

    def use_default_session(self) -> None:
        """Route calls back to the default session (undo ``use_session``)."""
        self._session_prefix = ""

    def delete_session(self, name: str) -> dict[str, Any]:
        """DELETE /sessions/{name} — stop and remove a named session.

        Cleans up the session's Xvfb display, any in-progress recording,
        and all panel temp files.  The display number is freed for reuse.
        """
        # Always call on the root (not the session prefix)
        return self._request("DELETE", f"/sessions/{name}")

    def list_sessions(self) -> list[dict[str, Any]]:
        """GET /sessions — list all active sessions."""
        result = self._request("GET", "/sessions")
        if isinstance(result, list):
            return result  # type: ignore[return-value]
        return []

    # ------------------------------------------------------------------
    # Compositions
    # ------------------------------------------------------------------

    def create_composition(
        self,
        name: str,
        recordings: list[str],
        *,
        layout: str = "row",
        labels: bool = True,
        highlights: list[dict[str, Any]] | None = None,
        highlight_color: str = "00d4aa",
        highlight_width: int = 6,
    ) -> dict[str, Any]:
        """POST /compositions — create a new composition.

        Parameters
        ----------
        name:
            Unique composition identifier.
        recordings:
            List of recording names to include.
        layout:
            Layout mode (e.g. ``"row"``).
        labels:
            Whether to show recording labels.
        highlights:
            Optional list of highlight dicts with keys
            ``recording``, ``time``, ``duration``.
        highlight_color:
            Hex colour for highlight borders (without ``#``).
        highlight_width:
            Pixel width of highlight borders.

        Returns
        -------
        dict
            Parsed JSON response from the server.
        """
        body: dict[str, Any] = {
            "name": name,
            "recordings": recordings,
            "layout": layout,
            "labels": labels,
            "highlight_color": highlight_color,
            "highlight_width": highlight_width,
        }
        if highlights is not None:
            body["highlights"] = highlights
        return self._request("POST", "/compositions", body)

    def add_highlight(
        self,
        composition_name: str,
        recording: str,
        time_: float,
        duration: float = 1.0,
    ) -> dict[str, Any]:
        """POST /compositions/{name}/highlights — add a highlight.

        Parameters
        ----------
        composition_name:
            Name of the composition.
        recording:
            Name of the recording this highlight applies to.
        time_:
            Time offset in seconds.
        duration:
            Duration of the highlight in seconds.

        Returns
        -------
        dict
            Parsed JSON response from the server.
        """
        return self._request(
            "POST",
            f"/compositions/{composition_name}/highlights",
            {"recording": recording, "time": time_, "duration": duration},
        )

    def composition_status(self, name: str) -> dict[str, Any]:
        """GET /compositions/{name} — get composition status.

        Returns
        -------
        dict
            Parsed JSON response with composition details.
        """
        return self._request("GET", f"/compositions/{name}")

    def list_compositions(self) -> list[dict[str, Any]]:
        """GET /compositions — list all compositions.

        Returns
        -------
        list
            List of composition dicts.
        """
        result = self._request("GET", "/compositions")
        if isinstance(result, list):
            return result  # type: ignore[return-value]
        return []

    def wait_for_composition(
        self,
        name: str,
        *,
        timeout: float = 120.0,
        interval: float = 1.0,
    ) -> dict[str, Any]:
        """Poll :meth:`composition_status` until complete or failed.

        Parameters
        ----------
        name:
            Composition name to poll.
        timeout:
            Maximum number of seconds to wait.
        interval:
            Seconds between poll attempts.

        Returns
        -------
        dict
            The final composition status dict.

        Raises
        ------
        RecorderError
            If the composition fails or *timeout* expires.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.composition_status(name)
            state = status.get("status")
            if state == "complete":
                return status
            if state == "failed":
                raise RecorderError(
                    f"Composition {name!r} failed: {status.get('error', 'unknown error')}"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))

        raise RecorderError(
            f"Composition {name!r} not ready after {timeout}s"
        )

    @contextmanager
    def composed_recording(
        self,
        name: str,
        recordings: list[str],
        *,
        layout: str = "row",
        labels: bool = True,
        highlight_color: str = "00d4aa",
        highlight_width: int = 6,
    ) -> Generator[CompositionHelper, None, None]:
        """Context manager that creates a composition with accumulated highlights.

        Usage::

            with client.composed_recording("comp", ["rec1", "rec2"]) as comp:
                comp.highlight("rec1", duration=2.0)
                ...
            print(comp.result)  # final composition status

        On exit the composition is created with any recorded highlights,
        then :meth:`wait_for_composition` is called to block until it
        completes.

        Parameters
        ----------
        name:
            Unique composition identifier.
        recordings:
            List of recording names to include.
        layout:
            Layout mode (e.g. ``"row"``).
        labels:
            Whether to show recording labels.
        highlight_color:
            Hex colour for highlight borders (without ``#``).
        highlight_width:
            Pixel width of highlight borders.
        """
        helper = CompositionHelper()
        yield helper
        self.create_composition(
            name,
            recordings,
            layout=layout,
            labels=labels,
            highlights=helper.highlights or None,
            highlight_color=highlight_color,
            highlight_width=highlight_width,
        )
        helper.result = self.wait_for_composition(name)

    # ------------------------------------------------------------------
    # Director — Mouse
    # ------------------------------------------------------------------

    def mouse_move(self, x: int, y: int, *, duration: float | None = None, target_width: float | None = None) -> dict[str, Any]:
        """POST /director/mouse/move — move the mouse cursor."""
        body: dict[str, Any] = {"x": x, "y": y}
        if duration is not None:
            body["duration"] = duration
        if target_width is not None:
            body["target_width"] = target_width
        return self._request("POST", "/director/mouse/move", body)

    def mouse_click(self, x: int | None = None, y: int | None = None, *, button: int = 1, duration: float | None = None) -> dict[str, Any]:
        """POST /director/mouse/click — click the mouse."""
        body: dict[str, Any] = {"button": button}
        if x is not None:
            body["x"] = x
        if y is not None:
            body["y"] = y
        if duration is not None:
            body["duration"] = duration
        return self._request("POST", "/director/mouse/click", body)

    def mouse_double_click(self, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        """POST /director/mouse/double-click — double-click."""
        body: dict[str, Any] = {}
        if x is not None:
            body["x"] = x
        if y is not None:
            body["y"] = y
        return self._request("POST", "/director/mouse/double-click", body)

    def mouse_right_click(self, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        """POST /director/mouse/right-click — right-click."""
        body: dict[str, Any] = {}
        if x is not None:
            body["x"] = x
        if y is not None:
            body["y"] = y
        return self._request("POST", "/director/mouse/right-click", body)

    def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, *, button: int = 1, duration: float | None = None) -> dict[str, Any]:
        """POST /director/mouse/drag — drag from one point to another."""
        body: dict[str, Any] = {"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y, "button": button}
        if duration is not None:
            body["duration"] = duration
        return self._request("POST", "/director/mouse/drag", body)

    def mouse_scroll(self, clicks: int, *, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        """POST /director/mouse/scroll — scroll the mouse wheel."""
        body: dict[str, Any] = {"clicks": clicks}
        if x is not None:
            body["x"] = x
        if y is not None:
            body["y"] = y
        return self._request("POST", "/director/mouse/scroll", body)

    def mouse_position(self) -> dict[str, Any]:
        """GET /director/mouse/position — get cursor position."""
        return self._request("GET", "/director/mouse/position")

    # ------------------------------------------------------------------
    # Director — Keyboard
    # ------------------------------------------------------------------

    def keyboard_type(self, text: str, *, wpm: float | None = None) -> dict[str, Any]:
        """POST /director/keyboard/type — type text with human-like rhythm."""
        body: dict[str, Any] = {"text": text}
        if wpm is not None:
            body["wpm"] = wpm
        return self._request("POST", "/director/keyboard/type", body)

    def keyboard_press(self, *keys: str) -> dict[str, Any]:
        """POST /director/keyboard/press — press key(s)."""
        return self._request("POST", "/director/keyboard/press", {"keys": list(keys)})

    def keyboard_hold(self, key: str) -> dict[str, Any]:
        """POST /director/keyboard/hold — hold a key down."""
        return self._request("POST", "/director/keyboard/hold", {"key": key})

    def keyboard_release(self, key: str) -> dict[str, Any]:
        """POST /director/keyboard/release — release a held key."""
        return self._request("POST", "/director/keyboard/release", {"key": key})

    # ------------------------------------------------------------------
    # Director — Window
    # ------------------------------------------------------------------

    def window_find(self, name: str | None = None, *, class_name: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
        """POST /director/window/find — find a window by name or WM_CLASS."""
        body: dict[str, Any] = {"timeout": timeout}
        if name is not None:
            body["name"] = name
        if class_name is not None:
            body["class"] = class_name
        return self._request("POST", "/director/window/find", body)

    def window_focus(self, window_id: str) -> dict[str, Any]:
        """POST /director/window/{id}/focus — focus a window."""
        return self._request("POST", f"/director/window/{window_id}/focus")

    def window_move(self, window_id: str, x: int, y: int) -> dict[str, Any]:
        """POST /director/window/{id}/move — move a window."""
        return self._request("POST", f"/director/window/{window_id}/move", {"x": x, "y": y})

    def window_resize(self, window_id: str, width: int, height: int) -> dict[str, Any]:
        """POST /director/window/{id}/resize — resize a window."""
        return self._request("POST", f"/director/window/{window_id}/resize", {"width": width, "height": height})

    def window_minimize(self, window_id: str) -> dict[str, Any]:
        """POST /director/window/{id}/minimize — minimize a window."""
        return self._request("POST", f"/director/window/{window_id}/minimize")

    def window_geometry(self, window_id: str) -> dict[str, Any]:
        """GET /director/window/{id}/geometry — get window geometry."""
        return self._request("GET", f"/director/window/{window_id}/geometry")

    def window_tile(self, window_ids: list[str], layout: str = "side-by-side", *, bounds: tuple[int, int, int, int] | None = None) -> dict[str, Any]:
        """POST /director/window/tile — tile windows."""
        body: dict[str, Any] = {"window_ids": window_ids, "layout": layout}
        if bounds is not None:
            body["bounds"] = list(bounds)
        return self._request("POST", "/director/window/tile", body)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def wait_until_ready(
        self,
        timeout: float = 30.0,
        interval: float = 0.5,
    ) -> dict[str, Any]:
        """Poll ``/health`` until the server responds or *timeout* expires.

        Parameters
        ----------
        timeout:
            Maximum number of seconds to wait.
        interval:
            Seconds between poll attempts.

        Returns
        -------
        dict
            The health response once the server is reachable.

        Raises
        ------
        RecorderError
            If the server does not become ready within *timeout*.
        """
        deadline = time.monotonic() + timeout
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self.health()
            except RecorderError as exc:
                last_err = exc
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(interval, remaining))

        raise RecorderError(
            f"Server not ready after {timeout}s: {last_err}"
        )

    @contextmanager
    def recording(
        self, name: str
    ) -> Generator[RecordingResult, None, None]:
        """Context manager that starts and stops a recording.

        Usage::

            with client.recording("demo") as result:
                ...  # drive your application here
            print(result.path)     # MP4 path on server
            print(result.elapsed)  # duration in seconds

        The recording is stopped (and the MP4 finalised) even if the
        body raises an exception.
        """
        result = RecordingResult()
        result.name = name
        self.start_recording(name)
        try:
            yield result
        finally:
            stop = self.stop_recording()
            result.path = stop.get("path")
            result.elapsed = stop.get("elapsed")

    @contextmanager
    def panel(
        self,
        name: str,
        title: str,
        width: int | None = None,
        height: int | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Context manager that creates and removes a panel.

        Usage::

            with client.panel("code", "Source", width=80) as info:
                client.update_panel("code", "hello world")
            # panel is removed automatically
        """
        info = self.add_panel(name, title, width=width, height=height)
        try:
            yield info
        finally:
            self.remove_panel(name)
