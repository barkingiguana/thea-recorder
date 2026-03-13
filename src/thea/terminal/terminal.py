"""Terminal recording convenience layer.

Wraps xterm launch, window management, and command execution into
a simple API for recording CLI demos and test runs.
"""

from __future__ import annotations

import os
import re
import tempfile
import time


# ANSI escape code stripping
_ANSI_RE = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]'    # CSI sequences (colors, cursor)
    r'|\x1b\][^\x07]*\x07'       # OSC sequences
    r'|\x1b[()][A-Z0-9]'         # Character set selection
    r'|\x1b\[\?[0-9;]*[hl]'      # Private mode set/reset
    r'|\r'                         # Carriage returns
)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub('', text)


class Terminal:
    """High-level terminal recording interface.

    Launches an xterm on the recorder's display, optionally sets up
    output capture, and provides convenience methods for typing
    commands and interacting with the terminal.

    Args:
        recorder: A :class:`thea.Recorder` instance.
        font: Font family name (default ``"DejaVu Sans Mono"``).
        font_size: Font size in points (default ``14``).
        bg: Background colour as hex (default ``"#000000"``).
        fg: Foreground colour as hex (default ``"#c0c0c0"``).
        scrollbar: Show scrollbar (default ``False``).
        border: Internal border in pixels (default ``8``).
        shell: Shell to run (default ``"bash"``).
        capture_output: Set up tee-based output capture for
            :meth:`latest_output` (default ``True``).
        prompt_pattern: Regex pattern matching the shell prompt,
            used by ``wait_for_prompt`` in :meth:`run_command`.
            If *None*, prompt detection is not available.
        wpm: Words-per-minute for typing (default ``None`` — uses
            the Director's default).
        fill_viewport: Resize xterm to fill the display (default ``True``).
        env: Extra environment variables for the xterm process.

    Example::

        from thea import Recorder
        from thea.terminal import Terminal

        rec = Recorder(output_dir="./recordings", display=99)
        rec.start_display()
        rec.start_recording("demo")

        term = Terminal(rec, font="JetBrains Mono", font_size=18)
        term.run_command("echo hello")
        term.clear()
        term.close()

        rec.stop_recording()
    """

    def __init__(
        self,
        recorder,
        *,
        font: str = "DejaVu Sans Mono",
        font_size: int = 14,
        bg: str = "#000000",
        fg: str = "#c0c0c0",
        scrollbar: bool = False,
        border: int = 8,
        shell: str = "bash",
        capture_output: bool = True,
        prompt_pattern: str | None = None,
        wpm: float | None = None,
        fill_viewport: bool = True,
        env: dict | None = None,
    ):
        self._rec = recorder
        self._wpm = wpm
        self._prompt_pattern = re.compile(prompt_pattern) if prompt_pattern else None
        self._capture_output = capture_output

        # Output capture state
        self._stdout_log = None
        self._stderr_log = None
        self._stdout_offset = 0
        self._stderr_offset = 0

        if capture_output:
            self._stdout_log = tempfile.mktemp(suffix="-stdout.log")
            self._stderr_log = tempfile.mktemp(suffix="-stderr.log")
            # Create empty log files
            for path in (self._stdout_log, self._stderr_log):
                with open(path, "w") as f:
                    pass

        # Build xterm command
        cmd = ["xterm"]
        cmd.extend(["-fa", font])
        cmd.extend(["-fs", str(font_size)])
        cmd.extend(["-bg", bg])
        cmd.extend(["-fg", fg])
        cmd.extend(["-b", str(border)])
        if not scrollbar:
            cmd.append("+sb")
        cmd.extend(["-e", shell, "--login"])

        # Launch xterm
        self._proc = recorder.launch_app(
            cmd,
            env=env,
            window_class="XTerm",
            fill_viewport=fill_viewport,
        )

        # Set up output capture if enabled
        if capture_output and self._stdout_log and self._stderr_log:
            self._setup_capture()

    def _setup_capture(self):
        """Set up tee-based output capture in the shell."""
        # Type the tee setup command quickly (not meant to be seen)
        tee_cmd = (
            f"exec > >(tee -a {self._stdout_log}) "
            f"2> >(tee -a {self._stderr_log} >&2)"
        )
        self._rec.director.keyboard.type(tee_cmd, wpm=9999)
        self._rec.director.keyboard.press("Return")
        time.sleep(0.3)
        # Clear screen so the plumbing isn't visible
        self._rec.director.keyboard.press("ctrl+l")
        time.sleep(0.3)
        # Mark initial offset
        self._mark_offset()

    def _mark_offset(self):
        """Record current log file sizes for latest_output tracking."""
        if self._stdout_log and os.path.exists(self._stdout_log):
            self._stdout_offset = os.path.getsize(self._stdout_log)
        if self._stderr_log and os.path.exists(self._stderr_log):
            self._stderr_offset = os.path.getsize(self._stderr_log)

    def _read_from(self, path: str, offset: int) -> str:
        """Read new content from a log file starting at offset."""
        if not path or not os.path.exists(path):
            return ""
        with open(path, "r", errors="replace") as f:
            f.seek(offset)
            return f.read()

    def run_command(
        self,
        command: str,
        *,
        pause_after: float = 1.5,
        wait_for_prompt: bool = False,
        timeout: float = 30.0,
    ):
        """Type a command, press Enter, and wait.

        Args:
            command: The command text to type.
            pause_after: Seconds to wait after pressing Enter
                (used when ``wait_for_prompt`` is *False*).
            wait_for_prompt: If *True*, wait for the shell prompt
                to reappear instead of using a fixed delay.
                Requires ``prompt_pattern`` to have been set.
            timeout: Maximum seconds to wait when using prompt
                detection (default ``30``).
        """
        self._mark_offset()
        kwargs = {}
        if self._wpm is not None:
            kwargs["wpm"] = self._wpm
        self._rec.keyboard_type(command, **kwargs)
        self._rec.keyboard_press("Return")

        if wait_for_prompt and self._prompt_pattern:
            self._wait_for_prompt(timeout)
        else:
            time.sleep(pause_after)

    def _wait_for_prompt(self, timeout: float):
        """Poll log output for the prompt pattern."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            output = self._read_from(self._stdout_log, self._stdout_offset)
            clean = _strip_ansi(output)
            # Check if prompt appears in the output (after the command itself)
            lines = clean.split("\n")
            if len(lines) >= 2 and self._prompt_pattern.search(lines[-1]):
                return
            time.sleep(0.1)
        # Timeout — continue anyway

    def latest_output(self) -> str:
        """Return ANSI-stripped output since the last :meth:`run_command`.

        Returns:
            Combined stdout and stderr text with ANSI codes removed.
        """
        if not self._capture_output:
            return ""
        stdout = self._read_from(self._stdout_log, self._stdout_offset)
        stderr = self._read_from(self._stderr_log, self._stderr_offset)
        return _strip_ansi(stdout + stderr)

    def latest_stdout(self) -> str:
        """Return ANSI-stripped stdout since the last :meth:`run_command`."""
        if not self._capture_output:
            return ""
        return _strip_ansi(self._read_from(self._stdout_log, self._stdout_offset))

    def latest_stderr(self) -> str:
        """Return ANSI-stripped stderr since the last :meth:`run_command`."""
        if not self._capture_output:
            return ""
        return _strip_ansi(self._read_from(self._stderr_log, self._stderr_offset))

    def clear(self):
        """Clear the terminal screen (Ctrl+L)."""
        self._rec.keyboard_press("ctrl+l")
        time.sleep(0.3)

    def close(self):
        """Exit the terminal session cleanly."""
        self._rec.keyboard_type("exit")
        self._rec.keyboard_press("Return")
        time.sleep(0.5)

    def cleanup(self):
        """Remove temporary log files."""
        for path in (self._stdout_log, self._stderr_log):
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
