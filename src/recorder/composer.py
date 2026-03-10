"""Compose multiple recordings into a single side-by-side video.

Given a list of MP4 files recorded by separate sessions, this module
tiles them into a single video using ffmpeg's ``xstack`` filter.  Each
tile can have a label and a timed highlight border that glows when
the client marks that session as "active".

The composition is a post-processing step — sessions record independently
as usual, and the compose step runs after all recordings are finished.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import threading
from dataclasses import dataclass, field

logger = logging.getLogger("recorder.composer")


# ── Data types ────────────────────────────────────────────────────────────

@dataclass
class Highlight:
    """A timed highlight border on one tile of the composed video.

    Attributes:
        recording: Name of the recording to highlight.
        time: Start time in seconds (relative to that recording).
        duration: How long the highlight lasts, in seconds.
    """
    recording: str
    time: float
    duration: float = 1.0


@dataclass
class CompositionSpec:
    """Everything needed to compose a multi-tile video.

    Attributes:
        name: Output filename (without .mp4 extension).
        recordings: Ordered list of recording names to tile.
        layout: ``"row"`` (side-by-side), ``"column"`` (stacked),
                or ``"grid"`` (auto rows × columns).
        labels: Whether to show recording names above each tile.
        highlights: Timed border-glow events.
        highlight_color: Hex colour for the border, e.g. ``"00d4aa"``.
        highlight_width: Border thickness in pixels.
    """
    name: str
    recordings: list[str]
    layout: str = "row"
    labels: bool = True
    highlights: list[Highlight] = field(default_factory=list)
    highlight_color: str = "00d4aa"
    highlight_width: int = 6

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "recordings": list(self.recordings),
            "layout": self.layout,
            "labels": self.labels,
            "highlights": [
                {"recording": h.recording, "time": h.time, "duration": h.duration}
                for h in self.highlights
            ],
            "highlight_color": self.highlight_color,
            "highlight_width": self.highlight_width,
        }


@dataclass
class CompositionResult:
    """Outcome of a composition render.

    Attributes:
        name: Composition name.
        status: ``"pending"``, ``"rendering"``, ``"complete"``, or ``"failed"``.
        output_path: Path to the composed MP4 (set when complete).
        error: Error message (set when failed).
    """
    name: str
    status: str = "pending"
    output_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "status": self.status}
        if self.output_path:
            d["output_path"] = self.output_path
            try:
                d["output_size"] = os.path.getsize(self.output_path)
            except OSError:
                pass
        if self.error:
            d["error"] = self.error
        return d


# ── Layout computation ────────────────────────────────────────────────────

def compute_layout(
    n: int,
    mode: str,
    tile_w: int,
    tile_h: int,
) -> tuple[list[tuple[int, int]], tuple[int, int]]:
    """Compute tile positions and total canvas size.

    Args:
        n: Number of tiles.
        mode: ``"row"``, ``"column"``, or ``"grid"``.
        tile_w: Width of each tile in pixels.
        tile_h: Height of each tile in pixels.

    Returns:
        ``(positions, canvas_size)`` where *positions* is a list of
        ``(x, y)`` tuples and *canvas_size* is ``(width, height)``.
    """
    if n < 1:
        raise ValueError("need at least 1 recording")

    if mode == "row":
        positions = [(i * tile_w, 0) for i in range(n)]
        canvas = (n * tile_w, tile_h)
    elif mode == "column":
        positions = [(0, i * tile_h) for i in range(n)]
        canvas = (tile_w, n * tile_h)
    elif mode == "grid":
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        positions = [
            ((i % cols) * tile_w, (i // cols) * tile_h) for i in range(n)
        ]
        canvas = (cols * tile_w, rows * tile_h)
    else:
        raise ValueError(f"unknown layout mode: {mode!r}")

    return positions, canvas


# ── ffprobe helpers ───────────────────────────────────────────────────────

def probe_duration(path: str) -> float:
    """Return the duration of an MP4 file in seconds."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr}")
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def probe_resolution(path: str) -> tuple[int, int]:
    """Return (width, height) of the first video stream."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr}")
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    return int(stream["width"]), int(stream["height"])


# ── Filter construction ──────────────────────────────────────────────────

def _build_filter_complex(
    spec: CompositionSpec,
    paths: list[str],
    tile_w: int,
    tile_h: int,
    font: str,
    font_bold: str,
    max_duration: float,
) -> str:
    """Build the full ffmpeg ``-filter_complex`` string.

    The filter graph:
    1. Scale each input to ``tile_w × tile_h``.
    2. Pad shorter inputs to ``max_duration`` with black frames.
    3. Tile them with ``xstack``.
    4. Add highlight borders (timed ``drawbox`` filters).
    5. Add labels (``drawtext`` above each tile).
    """
    n = len(paths)
    positions, (canvas_w, canvas_h) = compute_layout(n, spec.layout, tile_w, tile_h)

    parts: list[str] = []

    # 1+2. Scale each input and pad to max duration.
    for i in range(n):
        parts.append(
            f"[{i}:v]scale={tile_w}:{tile_h}:force_original_aspect_ratio=decrease,"
            f"pad={tile_w}:{tile_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"tpad=stop_duration={max_duration}:stop_mode=clone,"
            f"setpts=PTS-STARTPTS[v{i}]"
        )

    # 3. xstack.
    input_labels = "".join(f"[v{i}]" for i in range(n))
    layout_str = "|".join(f"{x}_{y}" for x, y in positions)
    parts.append(
        f"{input_labels}xstack=inputs={n}:layout={layout_str}:fill=black[tiled]"
    )

    # 4. Highlight borders.
    current_label = "tiled"
    label_idx = 0

    # Build a name→index map for highlights.
    name_to_idx = {spec.recordings[i]: i for i in range(n)}

    for hi, h in enumerate(spec.highlights):
        idx = name_to_idx.get(h.recording)
        if idx is None:
            continue
        x, y = positions[idx]
        t_start = h.time
        t_end = h.time + h.duration
        enable = f"between(t\\,{t_start:.3f}\\,{t_end:.3f})"
        bw = spec.highlight_width
        color = spec.highlight_color

        # Outer glow (semi-transparent, slightly larger).
        next_label = f"hl{label_idx}"
        parts.append(
            f"[{current_label}]"
            f"drawbox=x={x}:y={y}:w={tile_w}:h={tile_h}"
            f":color=0x{color}@0.3:t={bw + 4}"
            f":enable='{enable}'"
            f"[{next_label}]"
        )
        current_label = next_label
        label_idx += 1

        # Inner solid border.
        next_label = f"hl{label_idx}"
        parts.append(
            f"[{current_label}]"
            f"drawbox=x={x + 2}:y={y + 2}:w={tile_w - 4}:h={tile_h - 4}"
            f":color=0x{color}@0.9:t={bw}"
            f":enable='{enable}'"
            f"[{next_label}]"
        )
        current_label = next_label
        label_idx += 1

    # 5. Labels.
    if spec.labels and font_bold:
        for i in range(n):
            x, y = positions[i]
            label = spec.recordings[i].replace(":", "\\:").replace("'", "\\'")
            next_label = f"lb{i}"
            parts.append(
                f"[{current_label}]"
                f"drawtext=text='{label}'"
                f":fontfile={font_bold}:fontsize=16:fontcolor=white"
                f":x={x + 10}:y={y + 8}"
                f":box=1:boxcolor=0x000000@0.5:boxborderw=4"
                f"[{next_label}]"
            )
            current_label = next_label

    # Rename final label to [out].
    if current_label != "tiled":
        # Replace the last label with [out].
        last_part = parts[-1]
        last_part = last_part[:last_part.rfind("[")] + "[out]"
        parts[-1] = last_part
    else:
        # No highlights or labels — just rename tiled.
        parts[-1] = parts[-1].replace("[tiled]", "[out]")

    return ";\n".join(parts)


# ── Composition rendering ────────────────────────────────────────────────

def _find_system_fonts():
    """Find system monospace fonts (same search as recorder.py)."""
    from .recorder import _find_system_fonts as _find
    return _find()


def resolve_recording_path(output_dir: str, name: str) -> str | None:
    """Find the MP4 path for a recording name, or None."""
    safe = re.sub(r"[^\w\-.]", "_", name)[:120]
    path = os.path.join(output_dir, f"{safe}.mp4")
    return path if os.path.isfile(path) else None


def render_composition(
    spec: CompositionSpec,
    output_dir: str,
    tile_width: int = 640,
    tile_height: int = 360,
    crf: int = 20,
    font: str | None = None,
    font_bold: str | None = None,
) -> str:
    """Render a composed video synchronously.

    Args:
        spec: What to compose (recordings, layout, highlights, etc.).
        output_dir: Directory containing the source MP4s and where
            the composed MP4 will be written.
        tile_width: Width of each tile in pixels.
        tile_height: Height of each tile in pixels.
        crf: H.264 quality (lower = better, 18–23 is typical).
        font: Path to regular TTF font (auto-detected if None).
        font_bold: Path to bold TTF font (auto-detected if None).

    Returns:
        Absolute path to the composed MP4 file.

    Raises:
        FileNotFoundError: If a source recording doesn't exist.
        RuntimeError: If ffmpeg fails.
    """
    # Resolve fonts.
    if font is None or font_bold is None:
        sys_font, sys_bold = _find_system_fonts()
        font = font or sys_font
        font_bold = font_bold or sys_bold

    # Resolve input paths and probe durations.
    paths: list[str] = []
    max_duration = 0.0
    for name in spec.recordings:
        path = resolve_recording_path(output_dir, name)
        if path is None:
            raise FileNotFoundError(f"recording '{name}' not found in {output_dir}")
        paths.append(path)
        dur = probe_duration(path)
        max_duration = max(max_duration, dur)

    # Build the filter.
    filter_complex = _build_filter_complex(
        spec, paths, tile_width, tile_height, font, font_bold, max_duration,
    )

    # Output path.
    safe_name = re.sub(r"[^\w\-.]", "_", spec.name)[:120]
    output_path = os.path.join(output_dir, f"{safe_name}.mp4")

    # Build the ffmpeg command.
    cmd: list[str] = ["ffmpeg", "-y"]
    for p in paths:
        cmd.extend(["-i", p])
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ])

    logger.info("Composing %d recordings -> %s", len(paths), output_path)
    logger.debug("ffmpeg command: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg composition failed:\n{result.stderr[-2000:]}")

    logger.info("Composition complete: %s", output_path)
    return output_path


# ── Async composition manager ────────────────────────────────────────────

class CompositionManager:
    """Manages composition jobs with background rendering.

    This is used by the server to run compositions in background threads
    while exposing status via the REST API.
    """

    def __init__(self, output_dir: str):
        self._output_dir = output_dir
        self._compositions: dict[str, CompositionSpec] = {}
        self._results: dict[str, CompositionResult] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def create(self, spec: CompositionSpec) -> CompositionResult:
        """Register a composition and start rendering in the background."""
        with self._lock:
            if spec.name in self._compositions:
                raise ValueError(f"composition '{spec.name}' already exists")
            self._compositions[spec.name] = spec
            result = CompositionResult(name=spec.name, status="rendering")
            self._results[spec.name] = result

        thread = threading.Thread(
            target=self._render_worker,
            args=(spec.name,),
            daemon=True,
        )
        with self._lock:
            self._threads[spec.name] = thread
        thread.start()
        return result

    def add_highlight(self, name: str, highlight: Highlight):
        """Add a highlight event to an existing composition.

        Must be called before rendering starts (status == "pending")
        or to a composition that hasn't been created yet via
        ``create()``.  In practice the server creates the composition
        after all highlights are added, so this is the normal flow.
        """
        with self._lock:
            spec = self._compositions.get(name)
            if spec is None:
                raise KeyError(f"composition '{name}' not found")
            spec.highlights.append(highlight)

    def get(self, name: str) -> tuple[CompositionSpec, CompositionResult] | None:
        """Return (spec, result) or None if not found."""
        with self._lock:
            spec = self._compositions.get(name)
            result = self._results.get(name)
        if spec is None or result is None:
            return None
        return spec, result

    def list_all(self) -> list[dict]:
        """Return summary of all compositions."""
        with self._lock:
            return [
                {**self._results[name].to_dict(), **{"recordings": spec.recordings}}
                for name, spec in self._compositions.items()
                if name in self._results
            ]

    def delete(self, name: str) -> bool:
        """Remove a composition.  Returns True if it existed."""
        with self._lock:
            spec = self._compositions.pop(name, None)
            result = self._results.pop(name, None)
            self._threads.pop(name, None)
        return spec is not None

    def _render_worker(self, name: str):
        """Background thread that runs the ffmpeg composition."""
        with self._lock:
            spec = self._compositions.get(name)
            result = self._results.get(name)
        if spec is None or result is None:
            return

        try:
            output_path = render_composition(spec, self._output_dir)
            with self._lock:
                result.status = "complete"
                result.output_path = output_path
        except Exception as exc:
            logger.exception("Composition '%s' failed", name)
            with self._lock:
                result.status = "failed"
                result.error = str(exc)
