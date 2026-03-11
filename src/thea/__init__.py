# Client
from .client import CompositionHelper, RecorderClient, RecorderError, RecordingResult

# Layout
from .layout import Region, validate_regions, generate_testcard

# Director
from .director import Director, MotionConfig, RhythmConfig

# Recorder & server components
from .recorder import Recorder, PANEL_HEIGHT, LINE_HEIGHT
from .report import generate_report
from .composer import CompositionSpec, Highlight, render_composition

__all__ = [
    # Client
    "RecorderClient", "RecorderError", "RecordingResult", "CompositionHelper",
    # Layout
    "Region", "validate_regions", "generate_testcard",
    # Director
    "Director", "MotionConfig", "RhythmConfig",
    # Recorder & server
    "Recorder", "PANEL_HEIGHT", "LINE_HEIGHT",
    "generate_report",
    "CompositionSpec", "Highlight", "render_composition",
]
