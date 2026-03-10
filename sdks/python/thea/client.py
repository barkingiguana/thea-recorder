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


class RecorderClient:
    """Synchronous HTTP client for the thea-recorder server.

    Parameters
    ----------
    url:
        Base URL of the recorder server (e.g. ``http://localhost:8080``).
        Falls back to the ``RECORDER_URL`` environment variable.
    timeout:
        Default request timeout in seconds.
    """

    def __init__(
        self,
        url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        resolved = url or os.environ.get("RECORDER_URL")
        if not resolved:
            raise RecorderError(
                "No URL provided and RECORDER_URL environment variable is not set"
            )
        self.base_url: str = resolved.rstrip("/")
        self.timeout: float = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a JSON request and return the decoded response body."""
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

    def start_display(self) -> dict[str, Any]:
        """POST /display/start — start the virtual display."""
        return self._request("POST", "/display/start")

    def stop_display(self) -> dict[str, Any]:
        """POST /display/stop — stop the virtual display."""
        return self._request("POST", "/display/stop")

    # ------------------------------------------------------------------
    # Panels
    # ------------------------------------------------------------------

    def add_panel(
        self, name: str, title: str, width: int
    ) -> dict[str, Any]:
        """POST /panels — create a new panel."""
        return self._request(
            "POST", "/panels", {"name": name, "title": title, "width": width}
        )

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
    ) -> Generator[dict[str, Any], None, None]:
        """Context manager that starts and stops a recording.

        Usage::

            with client.recording("demo") as info:
                ...  # info is the start response
            # recording is automatically stopped

        The recording is stopped even if the body raises an exception.
        The stop response is attached as ``info["_stop"]`` after exit.
        """
        info = self.start_recording(name)
        try:
            yield info
        finally:
            stop = self.stop_recording()
            info["_stop"] = stop

    @contextmanager
    def panel(
        self, name: str, title: str, width: int
    ) -> Generator[dict[str, Any], None, None]:
        """Context manager that creates and removes a panel.

        Usage::

            with client.panel("code", "Source", 80) as info:
                client.update_panel("code", "hello world")
            # panel is removed automatically
        """
        info = self.add_panel(name, title, width)
        try:
            yield info
        finally:
            self.remove_panel(name)
