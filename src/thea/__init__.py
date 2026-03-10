# Client (stdlib-only, always available)
from .client import CompositionHelper, RecorderClient, RecorderError, RecordingResult

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
    # Server (available when [server] extra is installed)
    "Recorder", "PANEL_HEIGHT", "LINE_HEIGHT",
    "generate_report",
    "CompositionSpec", "Highlight", "render_composition",
]
