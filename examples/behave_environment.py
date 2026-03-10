"""Drop-in Behave environment.py for recording E2E tests.

Copy this file to your features/environment.py and customise the panels
and authenticator setup for your application. The recording hooks handle
the rest automatically.

Panel layout (bottom bar on recordings):
  [Status 120px] [Scenario auto-width]

Usage:
  1. pip install thea-recorder
  2. Copy this file to features/environment.py
  3. Run: behave --no-capture
"""

import os
import re
import time

from recorder import Recorder, generate_report


def _render_scenario_panel(recorder, header, step_events):
    """Format step events and push them to the scenario panel."""
    lines = []
    if header:
        lines.append(header)

    focus = -1
    for i, ev in enumerate(step_events):
        marker = "*" if ev["status"] == "running" else " "
        line = f" {marker} {ev['keyword']} {ev['name']}"
        if ev.get("table"):
            for row in ev["table"]:
                vals = " | ".join(str(v) for v in row.values())
                line += f"\n      | {vals} |"
        lines.append(line)
        if ev["status"] == "running":
            focus = len(lines) - 1

    recorder.update_panel("scenario", "\n".join(lines), focus_line=focus)


def _scenario_filename(scenario):
    feature = re.sub(r"[^\w\-.]", "_", scenario.feature.name[:40])
    name = re.sub(r"[^\w\-.]", "_", scenario.name[:60])
    return f"{feature}__{name}"


def before_all(context):
    recorder = Recorder(
        output_dir=os.environ.get("RECORDINGS_DIR", "/app/recordings"),
        display=int(os.environ.get("DISPLAY_NUM", "99")),
    )
    recorder.add_panel("status", title="Status", width=120)
    recorder.add_panel("scenario", title="Scenario")
    recorder.start_display()
    context.recorder = recorder
    context.recorded_videos = []


def before_scenario(context, scenario):
    recorder = context.recorder
    recorder.update_panel("status", "Initialising")

    context._step_events = [
        {
            "offset": 0.0,
            "keyword": s.keyword,
            "name": s.name,
            "status": "pending",
            **({"table": [{h: row[h] for h in s.table.headings} for row in s.table]} if s.table else {}),
        }
        for s in scenario.steps
    ]
    context._step_index = -1
    context._step_header = f"Feature:  {scenario.feature.name}\nScenario: {scenario.name}\n"
    _render_scenario_panel(recorder, context._step_header, context._step_events)

    recorder.start_recording(_scenario_filename(scenario))
    recorder.update_panel("status", "Running")


def before_step(context, step):
    recorder = context.recorder
    context._step_index += 1
    idx = context._step_index
    if idx < len(context._step_events):
        context._step_events[idx]["status"] = "running"
        context._step_events[idx]["offset"] = recorder.recording_elapsed
        if step.table:
            context._step_events[idx]["table"] = [
                {h: row[h] for h in step.table.headings} for row in step.table
            ]
    _render_scenario_panel(recorder, context._step_header, context._step_events)


def after_step(context, step):
    recorder = context.recorder
    idx = context._step_index
    if 0 <= idx < len(context._step_events):
        context._step_events[idx]["status"] = step.status.name
    _render_scenario_panel(recorder, context._step_header, context._step_events)
    if step.status.name == "failed":
        recorder.update_panel("status", "FAILED")


def after_scenario(context, scenario):
    recorder = context.recorder
    recorder.update_panel("status", scenario.status.name.upper())
    time.sleep(0.5)
    steps = list(context._step_events)
    video_path = recorder.stop_recording()
    if video_path:
        context.recorded_videos.append({
            "feature": scenario.feature.name,
            "scenario": scenario.name,
            "status": scenario.status.name,
            "video": video_path,
            "steps": steps,
        })


def after_all(context):
    context.recorder.cleanup()

    videos = context.recorded_videos
    if videos:
        output_dir = os.environ.get("RECORDINGS_DIR", "/app/recordings")
        generate_report(
            videos,
            output_dir=output_dir,
            title="E2E Test Report",
            subtitle="Automated test recordings with step timelines",
        )
