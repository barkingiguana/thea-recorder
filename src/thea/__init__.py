# Client (stdlib-only, always available)
from .client import CompositionHelper, RecorderClient, RecorderError, RecordingResult

# Layout (stdlib-only, always available)
from .layout import Region, validate_regions, generate_testcard

# Director (always available — uses xdotool at runtime)
from .director import Director, MotionConfig, RhythmConfig

# Server components (require flask/click — installed via `pip install thea-recorder[server]`)
try:
    from .recorder import Recorder, PANEL_HEIGHT, LINE_HEIGHT
    from .report import generate_report
    from .composer import CompositionSpec, Highlight, render_composition
except ImportError:
    pass

__all__ = [
    # Client
    "RecorderClient", "RecorderError", "RecordingResult", "CompositionHelper",
    # Layout
    "Region", "validate_regions", "generate_testcard",
    # Director (always available)
    "Director", "MotionConfig", "RhythmConfig",
    # Server (available when [server] extra is installed)
    "Recorder", "PANEL_HEIGHT", "LINE_HEIGHT",
    "generate_report",
    "CompositionSpec", "Highlight", "render_composition",
]
