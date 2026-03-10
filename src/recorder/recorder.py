"""Video recording via Xvfb + ffmpeg with a panel-based overlay.

When enabled, Chrome runs non-headless on a virtual framebuffer (Xvfb).
ffmpeg captures the display to MP4 and renders an info bar below the
browser viewport with named panels arranged as columns.

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

logger = logging.getLogger("recorder")

# Height of the info bar rendered below the browser viewport.
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
        browser_size: Browser viewport resolution (``WxH``).
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
        browser_size: str = "1920x1080",
        framerate: int = 15,
        font: str = None,
        font_bold: str = None,
    ):
        self._output_dir = output_dir
        self._display = display
        self._browser_size = browser_size
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
        self._panels = {}  # name -> {"title": str, "path": str, "width": int|None}

    # -- Display -----------------------------------------------------------

    @property
    def display_string(self) -> str:
        """X11 display identifier, e.g. ``:99``."""
        return f":{self._display}"

    def start_display(self):
        """Launch Xvfb on the configured display number."""
        w, h = self._browser_size.split("x")
        if self._panels:
            total_h = int(h) + PANEL_HEIGHT
        else:
            total_h = int(h)
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

    # -- Panels ------------------------------------------------------------

    def add_panel(self, name: str, title: str = "", width: int = None):
        """Register a named panel.

        Args:
            name: Unique panel identifier.
            title: Bold heading rendered above the panel content.
            width: Fixed width in pixels.  *None* means share the
                   remaining space equally with other auto-width panels.
        """
        if name in self._panels:
            self._remove_panel_files(self._panels[name])
        fd, path = tempfile.mkstemp(suffix=".txt", prefix=f"panel_{name}_")
        os.close(fd)
        with open(path, "w") as f:
            f.write("")
        self._panels[name] = {"title": title, "path": path, "width": width}

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

        visible_lines = (PANEL_HEIGHT - 28) // LINE_HEIGHT
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

    # -- Recording ---------------------------------------------------------

    @property
    def recording_elapsed(self) -> float:
        """Seconds since start_recording was called, or 0.0 if not recording."""
        if self._recording_start is None:
            return 0.0
        return time.monotonic() - self._recording_start

    def start_recording(self, filename: str):
        """Begin ffmpeg recording of the virtual display."""
        os.makedirs(self._output_dir, exist_ok=True)
        self._recording_start = time.monotonic()

        safe = re.sub(r"[^\w\-.]", "_", filename)[:120]
        self._output_path = os.path.join(self._output_dir, f"{safe}.mp4")

        w, h = self._browser_size.split("x")
        w_int, h_int = int(w), int(h)

        if self._panels:
            total_h = h_int + PANEL_HEIGHT
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
            stderr=subprocess.DEVNULL,
        )
        logger.debug("Recording started -> %s", self._output_path)

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
        font = self._font
        font_bold = self._font_bold

        layout = self._panel_layout(w)

        parts = [
            # Dark background bar below the viewport
            f"drawbox=x=0:y={bar_y}:w={w}:h={PANEL_HEIGHT}"
            f":color=0x1a1a2e@1:t=fill",
            # Thin separator line at top of bar
            f"drawbox=x=0:y={bar_y}:w={w}:h=1"
            f":color=0x30363d@1:t=fill",
        ]

        for i, (name, panel, panel_x, panel_w) in enumerate(layout):
            # Vertical separator (skip first panel)
            if i > 0:
                parts.append(
                    f"drawbox=x={panel_x}:y={bar_y}:w=1:h={PANEL_HEIGHT}"
                    f":color=0x30363d@1:t=fill"
                )

            # Title
            if panel["title"]:
                title_escaped = panel["title"].replace(":", "\\:")
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

        path = self._output_path
        self._ffmpeg_proc = None
        self._output_path = None
        self._recording_start = None

        logger.debug("Recording stopped -> %s", path)
        return path

    # -- Lifecycle ---------------------------------------------------------

    def cleanup(self):
        """Stop recording and display, remove panel temp files."""
        self.stop_recording()
        self.stop_display()
        for panel in self._panels.values():
            self._remove_panel_files(panel)
        self._panels.clear()
