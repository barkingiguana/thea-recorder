"""Video recording via Xvfb + ffmpeg with a panel-based overlay.

Any windowed application (browser, GUI app, desktop automation) runs on
a virtual framebuffer (Xvfb).  ffmpeg captures the display to MP4 and
renders an info bar below the application viewport with named panels
arranged as columns.

Panels with an explicit *width* (pixels) are allocated first; the
remaining space is shared equally among panels with no width set.

Zero panels -> no bar at all, just raw screen capture.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import time

from .layout import Region, generate_testcard, validate_regions

logger = logging.getLogger("recorder")

# Height of the info bar rendered below the application viewport.
PANEL_HEIGHT = 300

# Line height for panel text: 14pt font + 4px line_spacing.
LINE_HEIGHT = 18

# Search paths for monospace TTF fonts, in preference order.
_FONT_SEARCH = [
    # Linux (Debian/Ubuntu)
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
    # Linux (Arch/Fedora)
    ("/usr/share/fonts/TTF/DejaVuSansMono.ttf",
     "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf"),
    # Linux (Liberation Mono)
    ("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"),
    # macOS
    ("/System/Library/Fonts/Menlo.ttc",
     "/System/Library/Fonts/Menlo.ttc"),
    ("/System/Library/Fonts/Courier.dfont",
     "/System/Library/Fonts/Courier.dfont"),
]


def _find_system_fonts():
    """Find the best available monospace font pair on the system.

    Returns (font, font_bold) paths.  Falls back to empty strings
    if nothing is found (ffmpeg will use its built-in fallback).
    """
    for regular, bold in _FONT_SEARCH:
        if os.path.exists(regular):
            return regular, bold
    return "", ""


class Recorder:
    """Records the virtual display to MP4 with a panel-based info bar.

    Args:
        output_dir: Where MP4 files are saved.
        display: X11 display number (99 -> ``:99``).
        display_size: Application viewport resolution (``WxH``).
        framerate: Recording framerate (fps).
        font: Path to a regular-weight TTF font for panel content.
            *None* searches for a suitable monospace font on the system.
        font_bold: Path to a bold-weight TTF font for panel titles.
            *None* searches for a suitable monospace font on the system.
    """

    def __init__(
        self,
        output_dir: str = "/tmp/recordings",
        display: int = 99,
        display_size: str = "1920x1080",
        framerate: int = 15,
        font: str = None,
        font_bold: str = None,
    ):
        self._output_dir = output_dir
        self._display = display
        self._display_size = display_size
        self._framerate = framerate

        if font is None or font_bold is None:
            sys_font, sys_bold = _find_system_fonts()
            self._font = font or sys_font
            self._font_bold = font_bold or sys_bold
        else:
            self._font = font
            self._font_bold = font_bold

        self._xvfb_proc = None
        self._ffmpeg_proc = None
        self._output_path = None
        self._recording_start = None
        self._allocated_bar_height = PANEL_HEIGHT
        self._panels = {}  # name -> {"title": str, "path": str, "width": int|None, "height": int|None, "bg_color": str, "opacity": float}
        self._launched_apps = []  # Popen instances launched via launch_app()
        self._director = None  # Lazy-initialised Director instance
        self._annotations = []
        self._last_annotations = []

    # -- Display -----------------------------------------------------------

    @property
    def display_string(self) -> str:
        """X11 display identifier, e.g. ``:99``."""
        return f":{self._display}"

    @property
    def display_env(self) -> dict:
        """Environment dict with ``DISPLAY`` set to this recorder's Xvfb.

        Use this when launching applications on the recorder's display::

            subprocess.Popen(["chromium"], env=rec.display_env)
        """
        return {**os.environ, "DISPLAY": self.display_string}

    def start_display(self, display_size: str = None):
        """Launch Xvfb on the configured display number.

        Args:
            display_size: Override the display resolution for this session
                (``WxH``).  *None* uses the default set at construction.
        """
        if display_size is not None:
            self._display_size = display_size
        w, h = self._display_size.split("x")
        # Always allocate space for the panel bar so panels can be added
        # after the display has started without causing ffmpeg capture
        # failures (the panel bar region is just black when unused).
        total_h = int(h) + PANEL_HEIGHT
        cmd = [
            "Xvfb", self.display_string,
            "-screen", "0", f"{w}x{total_h}x24",
            "-ac",
        ]
        self._xvfb_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # Wait for the display socket to appear.
        socket_path = f"/tmp/.X11-unix/X{self._display}"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if os.path.exists(socket_path):
                break
            time.sleep(0.05)

        env = {**os.environ, "DISPLAY": self.display_string}
        subprocess.run(
            ["xsetroot", "-cursor_name", "left_ptr"],
            env=env, capture_output=True,
        )
        logger.debug("Xvfb started on %s (%sx%s)", self.display_string, w, total_h)

    def stop_display(self):
        """Terminate Xvfb."""
        if self._xvfb_proc:
            self._xvfb_proc.terminate()
            try:
                self._xvfb_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._xvfb_proc.kill()
            self._xvfb_proc = None
            logger.debug("Xvfb stopped")

    # -- Director ----------------------------------------------------------

    @property
    def director(self):
        """A :class:`thea.director.Director` for human-like interaction on this display.

        The Director is created lazily on first access and reused thereafter.
        """
        if self._director is None:
            from .director import Director
            self._director = Director(self.display_env)
        return self._director

    # -- Input convenience (delegates to Director) -------------------------

    def keyboard_type(self, text: str, *, wpm: float = None):
        """Type text with human-like rhythm. Delegates to the Director's keyboard."""
        self.director.keyboard.type(text, wpm=wpm)

    def keyboard_press(self, *keys: str):
        """Press one or more keys. Delegates to the Director's keyboard."""
        self.director.keyboard.press(*keys)

    def mouse_move(self, x: int, y: int, *, duration: float = None):
        """Move the mouse with human-like motion. Delegates to the Director's mouse."""
        self.director.mouse.move(x, y, duration=duration)

    def mouse_click(self, x: int, y: int = None, *, button: int = 1):
        """Click at a position. Delegates to the Director's mouse."""
        if y is not None:
            self.director.mouse.click(x, y, button=button)
        else:
            self.director.mouse.click(x, button=button)

    # -- Annotations -------------------------------------------------------

    def add_annotation(self, label: str, *, time: float = None, details: str = None) -> dict:
        """Add an annotation to the current recording.

        Args:
            label: Short label for the annotation.
            time: Time offset in seconds. *None* uses recording_elapsed.
            details: Optional longer description.

        Returns:
            The annotation dict.

        Raises:
            RuntimeError: If not currently recording.
        """
        if self._ffmpeg_proc is None:
            raise RuntimeError("Not recording")
        if time is None:
            time = round(self.recording_elapsed, 3)
        annotation = {"label": label, "time": round(time, 3)}
        if details is not None:
            annotation["details"] = details
        self._annotations.append(annotation)
        return annotation

    def list_annotations(self) -> list[dict]:
        """Return annotations for the current recording."""
        return list(self._annotations)

    # -- Application launching ---------------------------------------------

    def launch_app(self, cmd: list[str], *, env: dict = None, **kwargs) -> subprocess.Popen:
        """Launch an application on the recorder's Xvfb display.

        The process is tracked and will be terminated automatically when
        :meth:`cleanup` is called.  ``DISPLAY`` is set to this recorder's
        display — you do not need to set it yourself.

        Thea, Xvfb, and the launched application **must** all run on the same
        machine.  This method launches a local subprocess; it is not a remote
        execution mechanism.

        Args:
            cmd: Command and arguments, e.g. ``["chromium", "--no-sandbox"]``.
            env: Extra environment variables.  These are merged on top of
                :attr:`display_env`.  If *None*, only ``DISPLAY`` is added.
            **kwargs: Passed through to :class:`subprocess.Popen`.

        Returns:
            The :class:`subprocess.Popen` instance.
        """
        merged_env = self.display_env
        if env:
            merged_env.update(env)
        proc = subprocess.Popen(cmd, env=merged_env, **kwargs)
        self._launched_apps.append(proc)
        logger.debug("Launched app (pid %d): %s", proc.pid, cmd)
        return proc

    # -- Panels ------------------------------------------------------------

    @property
    def panel_bar_height(self) -> int:
        """Effective bar height based on panel configurations.

        Returns the maximum of all explicit panel heights.  If no panel
        specifies an explicit height, falls back to :data:`PANEL_HEIGHT`.
        Returns ``0`` when there are no panels.
        """
        if not self._panels:
            return 0
        heights = []
        for p in self._panels.values():
            if p["height"] is not None:
                heights.append(p["height"])
            else:
                heights.append(PANEL_HEIGHT)
        return max(heights)

    def add_panel(
        self,
        name: str,
        title: str = "",
        width: int = None,
        height: int = None,
        bg_color: str = None,
        opacity: float = None,
    ) -> list[str]:
        """Register a named panel.

        Args:
            name: Unique panel identifier.
            title: Bold heading rendered above the panel content.
            width: Fixed width in pixels.  *None* means share the
                   remaining space equally with other auto-width panels.
            height: Panel content height in pixels.  *None* means use the
                   bar height (which defaults to :data:`PANEL_HEIGHT`).
            bg_color: Background colour as a hex string (e.g. ``"#1a1a2e"``
                   or ``"1a1a2e"``).  *None* uses the default dark theme.
            opacity: Background opacity from ``0.0`` (fully transparent) to
                   ``1.0`` (fully opaque).  *None* defaults to ``1.0``.

        Returns:
            List of layout validation warnings (may be empty).
        """
        if name in self._panels:
            self._remove_panel_files(self._panels[name])
        fd, path = tempfile.mkstemp(suffix=".txt", prefix=f"panel_{name}_")
        os.close(fd)
        with open(path, "w") as f:
            f.write("")
        # Normalise colour: strip leading '#' if present
        if bg_color is not None:
            bg_color = bg_color.lstrip("#")
        if opacity is not None:
            opacity = max(0.0, min(1.0, opacity))
        self._panels[name] = {
            "title": title, "path": path, "width": width, "height": height,
            "bg_color": bg_color, "opacity": opacity,
        }
        return self.validate_layout()

    def remove_panel(self, name: str):
        """Remove a panel and delete its temp file. No-op if not present."""
        panel = self._panels.pop(name, None)
        if panel:
            self._remove_panel_files(panel)

    def update_panel(self, name: str, text: str, *, focus_line: int = -1):
        """Atomically update a panel's content.

        Args:
            name: Panel identifier (must already exist via :meth:`add_panel`).
            text: Full text content for the panel.
            focus_line: Line index (0-based) to keep visible.  ``-1``
                (the default) focuses on the last line.
        """
        panel = self._panels.get(name)
        if not panel:
            return

        panel_h = panel["height"] if panel["height"] is not None else self.panel_bar_height or PANEL_HEIGHT
        visible_lines = (panel_h - 28) // LINE_HEIGHT
        lines = text.split("\n")

        if len(lines) > visible_lines:
            if focus_line == -1:
                focus_line = len(lines) - 1
            half = visible_lines // 2
            start = max(0, focus_line - half)
            end = start + visible_lines
            if end > len(lines):
                end = len(lines)
                start = max(0, end - visible_lines)
            visible = lines[start:end]
            if start > 0:
                visible.insert(0, f"  ... {start} more above")
            if end < len(lines):
                visible.append(f"  ... {len(lines) - end} more below")
            text = "\n".join(visible)

        tmp = panel["path"] + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.rename(tmp, panel["path"])

    @staticmethod
    def _remove_panel_files(panel):
        for suffix in ("", ".tmp"):
            try:
                os.unlink(panel["path"] + suffix)
            except FileNotFoundError:
                pass

    # -- Screenshots -------------------------------------------------------

    def screenshot(self, quality: int = 80) -> bytes:
        """Capture the current display as a JPEG image.

        Args:
            quality: JPEG quality (1-100).

        Returns:
            Raw JPEG bytes.
        """
        if self._xvfb_proc is None:
            raise RuntimeError("Display not started")

        w, h = self._display_size.split("x")
        w_int, h_int = int(w), int(h)
        bar_h = self.panel_bar_height if self._panels else 0
        total_h = h_int + bar_h

        # Map quality 1-100 to ffmpeg q:v 31-1 (lower q:v = higher quality)
        qv = max(1, min(31, 31 - (quality * 30 // 100)))

        cmd = [
            "ffmpeg", "-y",
            "-f", "x11grab",
            "-video_size", f"{w_int}x{total_h}",
            "-i", self.display_string,
            "-vframes", "1",
            "-q:v", str(qv),
            "-f", "mjpeg",
            "-",
        ]
        result = subprocess.run(
            cmd, capture_output=True, timeout=5,
            env=self.display_env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Screenshot failed: {result.stderr.decode('utf-8', errors='replace')[:200]}"
            )
        return result.stdout

    @staticmethod
    def screenshot_from_video(video_path: str, time_offset: float, quality: int = 80) -> bytes:
        """Extract a frame from a recorded video at a given time offset.

        Args:
            video_path: Path to the MP4 file.
            time_offset: Time in seconds.
            quality: JPEG quality (1-100).

        Returns:
            Raw JPEG bytes.
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        qv = max(1, min(31, 31 - (quality * 30 // 100)))

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{time_offset:.3f}",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", str(qv),
            "-f", "mjpeg",
            "-",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(
                f"Frame extraction failed: {result.stderr.decode('utf-8', errors='replace')[:200]}"
            )
        return result.stdout

    # -- Recording ---------------------------------------------------------

    @property
    def recording_elapsed(self) -> float:
        """Seconds since start_recording was called, or 0.0 if not recording."""
        if self._recording_start is None:
            return 0.0
        return time.monotonic() - self._recording_start

    def start_recording(self, filename: str) -> list[str]:
        """Begin ffmpeg recording of the virtual display.

        Returns:
            List of layout validation warnings (may be empty).
        """
        warnings = self.validate_layout()
        os.makedirs(self._output_dir, exist_ok=True)
        self._recording_start = time.monotonic()
        self._annotations = []

        safe = re.sub(r"[^\w\-.]", "_", filename)[:120]
        self._output_path = os.path.join(self._output_dir, f"{safe}.mp4")

        w, h = self._display_size.split("x")
        w_int, h_int = int(w), int(h)

        if self._panels:
            bar_h = min(self.panel_bar_height, self._allocated_bar_height)
            total_h = h_int + bar_h
            vf = self._build_panel_filter(w_int, h_int)
            cmd = [
                "ffmpeg", "-y",
                "-f", "x11grab",
                "-video_size", f"{w_int}x{total_h}",
                "-framerate", str(self._framerate),
                "-draw_mouse", "1",
                "-i", self.display_string,
                "-vf", vf,
                "-codec:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-threads", "1",
                self._output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-f", "x11grab",
                "-video_size", f"{w_int}x{h_int}",
                "-framerate", str(self._framerate),
                "-draw_mouse", "1",
                "-i", self.display_string,
                "-codec:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-threads", "1",
                self._output_path,
            ]

        self._ffmpeg_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        logger.debug("Recording started -> %s", self._output_path)
        return warnings

    def _panel_layout(self, total_w: int):
        """Compute (name, panel, x, width) for each panel."""
        fixed_sum = sum(
            p["width"] for p in self._panels.values() if p["width"] is not None
        )
        auto_panels = [n for n, p in self._panels.items() if p["width"] is None]
        auto_w = (total_w - fixed_sum) // len(auto_panels) if auto_panels else 0

        layout = []
        x = 0
        for name, panel in self._panels.items():
            w = panel["width"] if panel["width"] is not None else auto_w
            layout.append((name, panel, x, w))
            x += w
        return layout

    def _build_panel_filter(self, w: int, h: int) -> str:
        """Build the ffmpeg -vf filter string for the panel bar."""
        bar_y = h
        bar_h = min(self.panel_bar_height, self._allocated_bar_height)
        font = self._font
        font_bold = self._font_bold

        layout = self._panel_layout(w)

        # Check if all panels share the same background
        default_bg = "1a1a2e"
        default_opacity = 1.0
        all_same_bg = all(
            (p.get("bg_color") or default_bg) == (layout[0][1].get("bg_color") or default_bg)
            and (p.get("opacity") if p.get("opacity") is not None else default_opacity)
            == (layout[0][1].get("opacity") if layout[0][1].get("opacity") is not None else default_opacity)
            for _, p, _, _ in layout
        )

        parts = []
        if all_same_bg:
            # Single background for the whole bar
            bg = layout[0][1].get("bg_color") or default_bg
            op = layout[0][1].get("opacity") if layout[0][1].get("opacity") is not None else default_opacity
            parts.append(
                f"drawbox=x=0:y={bar_y}:w={w}:h={bar_h}"
                f":color=0x{bg}@{op}:t=fill"
            )
        else:
            # Per-panel backgrounds
            for _, panel, panel_x, panel_w in layout:
                bg = panel.get("bg_color") or default_bg
                op = panel.get("opacity") if panel.get("opacity") is not None else default_opacity
                parts.append(
                    f"drawbox=x={panel_x}:y={bar_y}:w={panel_w}:h={bar_h}"
                    f":color=0x{bg}@{op}:t=fill"
                )

        # Thin separator line at top of bar
        parts.append(
            f"drawbox=x=0:y={bar_y}:w={w}:h=1"
            f":color=0x30363d@1:t=fill"
        )

        for i, (name, panel, panel_x, panel_w) in enumerate(layout):
            # Vertical separator (skip first panel)
            if i > 0:
                parts.append(
                    f"drawbox=x={panel_x}:y={bar_y}:w=1:h={bar_h}"
                    f":color=0x30363d@1:t=fill"
                )

            # Title
            if panel["title"]:
                title_escaped = panel["title"].replace("'", "\u2019").replace(":", "\\:")
                parts.append(
                    f"drawtext=text='{title_escaped}'"
                    f":fontfile={font_bold}:fontsize=14:fontcolor=0x58a6ff"
                    f":x={panel_x + 10}:y={bar_y + 10}"
                )

            # Content (reloading text file)
            parts.append(
                f"drawtext=textfile={panel['path']}:reload=1"
                f":fontfile={font}:fontsize=14:fontcolor=0xc9d1d9"
                f":x={panel_x + 10}:y={bar_y + 28}:line_spacing=4"
            )

        # Clock + REC in top-right of bar
        clock_x = w - 240
        clock_y = bar_y + 10
        rec_x = w - 60
        rec_y = bar_y + 10

        parts.append(
            f"drawtext=text='%{{localtime\\:%Y-%m-%d  %H\\:%M\\:%S}}'"
            f":fontfile={font_bold}:fontsize=16:fontcolor=0x58a6ff"
            f":x={clock_x}:y={clock_y}"
        )
        parts.append(
            f"drawtext=text='REC'"
            f":fontfile={font_bold}:fontsize=14:fontcolor=0xf85149"
            f":x={rec_x}:y={rec_y}"
        )

        return ",".join(parts)

    def _build_regions(self) -> tuple[int, int, list[Region]]:
        """Build layout regions from the current panel configuration.

        Returns:
            (canvas_width, canvas_height, regions)
        """
        w, h = self._display_size.split("x")
        w_int, h_int = int(w), int(h)
        bar_h = self.panel_bar_height if self._panels else 0
        canvas_h = h_int + bar_h

        regions: list[Region] = [
            Region("viewport", 0, 0, w_int, h_int, kind="app"),
        ]

        if self._panels:
            for name, panel, x, pw in self._panel_layout(w_int):
                regions.append(Region(name, x, h_int, pw, bar_h, kind="panel"))

        return w_int, canvas_h, regions

    def validate_layout(self) -> list[str]:
        """Validate the current layout.

        Checks for overlapping regions, regions exceeding the canvas,
        and panel bar height exceeding the allocated display space.

        Returns:
            List of warning strings.  Empty means the layout is valid.
        """
        w_int, canvas_h, regions = self._build_regions()
        warnings = validate_regions(w_int, canvas_h, regions)

        bar_h = self.panel_bar_height
        if bar_h > self._allocated_bar_height:
            warnings.append(
                f"Panel bar needs {bar_h}px but only "
                f"{self._allocated_bar_height}px was allocated in the display. "
                f"Recording will be capped at {self._allocated_bar_height}px."
            )

        return warnings

    def generate_testcard(self) -> str:
        """Generate an SVG testcard showing the current layout.

        Returns:
            SVG markup as a string.
        """
        w_int, canvas_h, regions = self._build_regions()
        warnings = self.validate_layout()
        return generate_testcard(w_int, canvas_h, regions, warnings=warnings)

    def stop_recording(self):
        """Stop ffmpeg gracefully and return the output path, or *None*."""
        if not self._ffmpeg_proc:
            return None

        try:
            self._ffmpeg_proc.stdin.write(b"q")
            self._ffmpeg_proc.stdin.flush()
            self._ffmpeg_proc.wait(timeout=10)
        except Exception:
            self._ffmpeg_proc.terminate()
            try:
                self._ffmpeg_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._ffmpeg_proc.kill()

        returncode = self._ffmpeg_proc.returncode
        stderr_output = b""
        if self._ffmpeg_proc.stderr:
            try:
                stderr_output = self._ffmpeg_proc.stderr.read()
            except Exception:
                pass
        if returncode and returncode != 0:
            stderr_text = stderr_output.decode("utf-8", errors="replace").strip()
            logger.warning(
                "ffmpeg exited with code %d for %s: %s",
                returncode, self._output_path,
                stderr_text[-2000:] if stderr_text else "(no stderr)",
            )

        path = self._output_path
        self._last_annotations = list(self._annotations)
        self._ffmpeg_proc = None
        self._output_path = None
        self._recording_start = None

        logger.debug("Recording stopped -> %s", path)
        return path

    # -- Lifecycle ---------------------------------------------------------

    def cleanup(self):
        """Stop recording and display, terminate launched apps, remove panel temp files."""
        self.stop_recording()
        for proc in self._launched_apps:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._launched_apps.clear()
        self.stop_display()
        for panel in self._panels.values():
            self._remove_panel_files(panel)
        self._panels.clear()
