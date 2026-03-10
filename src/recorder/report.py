"""HTML report generator for test recordings.

Produces a dark-themed report with embedded MP4 videos, clickable step
timelines synced to video timestamps, and pass/fail summary statistics.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _step_table_html(table) -> str:
    if not table:
        return ""
    headings = list(table[0].keys())
    rows = "".join(
        "<tr>" + "".join(f"<td>{_escape(str(row.get(h, '')))}</td>" for h in headings) + "</tr>"
        for row in table
    )
    header = "".join(f"<th>{_escape(h)}</th>" for h in headings)
    return f'<table class="step-table"><tr>{header}</tr>{rows}</table>'


def generate_report(
    videos: list[dict],
    output_dir: str = "/tmp/recordings",
    title: str = "Test Report",
    subtitle: str = "Automated test recordings",
    logo_text: str = "R",
):
    """Write an HTML report with embedded video players and step timelines.

    Args:
        videos: List of dicts, each with keys: feature, scenario, status,
            video, and optionally steps (list of dicts with keyword, name,
            status, offset, and optionally table).
        output_dir: Directory where the report and videos live.
        title: Report heading.
        subtitle: Text below the heading.
        logo_text: Single character shown in the logo badge.

    Returns:
        Path to the generated report HTML file.
    """
    report_path = os.path.join(output_dir, "report.html")
    os.makedirs(output_dir, exist_ok=True)

    passed = sum(1 for v in videos if v["status"] == "passed")
    failed = len(videos) - passed
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Group by feature
    features: dict[str, list] = {}
    for v in videos:
        features.setdefault(v["feature"], []).append(v)

    feature_sections = []
    vid_idx = 0
    for feature_name, scenarios in features.items():
        f_passed = sum(1 for s in scenarios if s["status"] == "passed")
        f_failed = len(scenarios) - f_passed
        f_class = "fail" if f_failed else "pass"

        scenario_cards = []
        for v in scenarios:
            video_file = os.path.basename(v["video"])
            status_class = "pass" if v["status"] == "passed" else "fail"
            vid_id = f"vid{vid_idx}"
            vid_idx += 1

            steps = v.get("steps", [])
            step_items = []
            for step in steps:
                offset = step["offset"]
                s_class = "step-" + step.get("status", "running")
                mm = int(offset) // 60
                ss = int(offset) % 60
                timestamp = f"{mm}:{ss:02d}"
                table_html = _step_table_html(step.get("table"))
                step_items.append(
                    f'<li class="{s_class}" data-offset="{offset:.2f}" '
                    f'onclick="seekTo(\'{vid_id}\',{offset:.2f})">'
                    f'<span class="ts">{timestamp}</span>'
                    f'<span class="step-text">'
                    f'<span class="kw">{step["keyword"]}</span> {_escape(step["name"])}'
                    f"</span>"
                    f"{table_html}"
                    f"</li>"
                )

            steps_html = f'<ol class="steps" id="steps-{vid_id}">{"".join(step_items)}</ol>'
            offsets_js = ",".join(f"{s['offset']:.2f}" for s in steps) if steps else ""

            scenario_cards.append(
                f'<details class="scenario {status_class}" open>'
                f"<summary>"
                f'<span class="scenario-name">{_escape(v["scenario"])}</span>'
                f'<span class="badge {status_class}">{v["status"].upper()}</span>'
                f"</summary>"
                f'<div class="scenario-body">'
                f'<div class="video-col">'
                f'<video id="{vid_id}" controls preload="metadata" '
                f'data-offsets="[{offsets_js}]" data-steps-id="steps-{vid_id}">'
                f'<source src="{video_file}" type="video/mp4">'
                f"</video>"
                f"</div>"
                f'<div class="steps-col">{steps_html}</div>'
                f"</div></details>"
            )

        feature_sections.append(
            f'<details class="feature" open>'
            f'<summary class="feature-summary">'
            f'<span class="feature-name">{_escape(feature_name)}</span>'
            f'<span class="feature-count">'
            f'<span class="pass">{f_passed}</span> / '
            f'<span class="fail">{f_failed}</span>'
            f"</span>"
            f'<span class="badge {f_class}">{"PASS" if not f_failed else "FAIL"}</span>'
            f"</summary>"
            + "\n".join(scenario_cards)
            + "</details>"
        )

    html = f"""\
<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
    --bg-primary: #0a0e17;
    --bg-secondary: #111827;
    --bg-card: #151d2e;
    --bg-hover: #1c2940;
    --border: #1e2d45;
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent: #00d4aa;
    --accent-dim: rgba(0, 212, 170, 0.15);
    --pass: #22c55e;
    --pass-bg: rgba(34, 197, 94, 0.1);
    --fail: #ef4444;
    --fail-bg: rgba(239, 68, 68, 0.1);
    --keyword: #a78bfa;
    --timestamp: #38bdf8;
    --radius: 10px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
}}
body::before {{
    content: '';
    position: fixed;
    inset: 0;
    z-index: -1;
    background-image:
        radial-gradient(circle at 25% 25%, rgba(0, 212, 170, 0.03) 0%, transparent 50%),
        radial-gradient(circle at 75% 75%, rgba(56, 189, 248, 0.03) 0%, transparent 50%);
}}
.container {{ max-width: 1400px; margin: 0 auto; padding: 3rem 2rem; }}
header {{ margin-bottom: 3rem; padding-bottom: 2rem; border-bottom: 1px solid var(--border); }}
.brand {{ display: flex; align-items: center; gap: 16px; margin-bottom: 1rem; }}
.logo {{
    width: 48px; height: 48px;
    background: linear-gradient(135deg, var(--accent), #38bdf8);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem; font-weight: 700; color: var(--bg-primary); flex-shrink: 0;
}}
h1 {{ font-size: 1.75rem; font-weight: 700; letter-spacing: -0.02em; }}
.subtitle {{ color: var(--text-secondary); font-size: 0.9rem; margin-top: 0.25rem; }}
.summary-bar {{ display: flex; gap: 2rem; margin-top: 1.5rem; align-items: center; }}
.stat {{ display: flex; align-items: center; gap: 8px; font-size: 0.95rem; color: var(--text-secondary); }}
.stat-value {{ font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; font-weight: 600; }}
.stat-value.pass {{ color: var(--pass); }}
.stat-value.fail {{ color: var(--fail); }}
.stat-value.total {{ color: var(--accent); }}
.stat-divider {{ width: 1px; height: 32px; background: var(--border); }}
.timestamp {{ color: var(--text-muted); font-size: 0.8rem; margin-left: auto; font-family: 'JetBrains Mono', monospace; }}
.feature {{
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: var(--radius); margin-bottom: 1.5rem; overflow: hidden;
}}
.feature-summary {{
    padding: 16px 20px; cursor: pointer; display: flex; align-items: center;
    gap: 12px; font-size: 1rem; list-style: none; transition: background 0.15s;
}}
.feature-summary:hover {{ background: var(--bg-hover); }}
.feature-summary::-webkit-details-marker {{ display: none; }}
.feature-summary::before {{
    content: "\\25B6"; font-size: 0.65rem; color: var(--text-muted); transition: transform 0.2s ease;
}}
.feature[open] > .feature-summary::before {{ transform: rotate(90deg); }}
.feature-name {{ flex: 1; color: var(--text-primary); font-weight: 600; }}
.feature-count {{ font-size: 0.8rem; font-family: 'JetBrains Mono', monospace; color: var(--text-muted); }}
.feature-count .pass {{ color: var(--pass); }}
.feature-count .fail {{ color: var(--fail); }}
.scenario {{
    margin: 0 12px 12px; border: 1px solid var(--border);
    border-radius: 8px; background: var(--bg-card); overflow: hidden;
}}
.scenario > summary {{
    padding: 12px 16px; cursor: pointer; display: flex; align-items: center;
    gap: 10px; list-style: none; font-size: 0.92rem; transition: background 0.15s;
}}
.scenario > summary:hover {{ background: var(--bg-hover); }}
.scenario > summary::-webkit-details-marker {{ display: none; }}
.scenario > summary::before {{
    content: "\\25B6"; font-size: 0.55rem; color: var(--text-muted); transition: transform 0.2s ease;
}}
.scenario[open] > summary::before {{ transform: rotate(90deg); }}
.scenario-name {{ flex: 1; color: var(--text-secondary); }}
.scenario.fail {{ border-color: rgba(239, 68, 68, 0.3); }}
.badge {{
    padding: 3px 12px; border-radius: 20px; font-size: 0.65rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.8px; font-family: 'JetBrains Mono', monospace;
}}
.badge.pass {{ background: var(--pass-bg); color: var(--pass); }}
.badge.fail {{ background: var(--fail-bg); color: var(--fail); }}
.scenario-body {{ display: flex; gap: 16px; padding: 16px; border-top: 1px solid var(--border); }}
.video-col {{ flex: 1; min-width: 0; }}
.steps-col {{ width: 360px; flex-shrink: 0; }}
video {{
    border-radius: 8px; width: 100%; background: #000;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
}}
.steps {{
    list-style: none; max-height: 460px; overflow-y: auto;
    font-size: 0.78rem; font-family: 'JetBrains Mono', monospace;
    scrollbar-width: thin; scrollbar-color: var(--border) transparent;
}}
.steps::-webkit-scrollbar {{ width: 6px; }}
.steps::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
.steps li {{
    padding: 8px 10px; border-radius: 6px; cursor: pointer;
    border-left: 3px solid transparent; transition: all 0.15s ease; line-height: 1.5;
}}
.steps li:hover {{ background: var(--bg-hover); }}
.steps li.active {{ background: var(--bg-hover); border-left-color: var(--accent) !important; }}
.steps .ts {{ color: var(--timestamp); font-size: 0.7rem; margin-right: 8px; opacity: 0.7; }}
.steps .kw {{ color: var(--keyword); font-weight: 600; }}
.steps .step-text {{ display: block; }}
.step-passed {{ border-left-color: var(--pass); }}
.step-failed {{ border-left-color: var(--fail); background: var(--fail-bg); }}
.step-running {{ border-left-color: var(--text-muted); }}
.step-pending {{ opacity: 0.5; }}
.step-table {{
    margin: 6px 0 2px 18px; border-collapse: collapse; font-size: 0.7rem;
}}
.step-table th {{
    background: var(--bg-secondary); padding: 3px 10px; text-align: left;
    color: var(--text-muted); font-weight: 600; border: 1px solid var(--border);
}}
.step-table td {{ padding: 3px 10px; border: 1px solid var(--border); color: var(--text-secondary); }}
@media (max-width: 900px) {{
    .scenario-body {{ flex-direction: column; }}
    .steps-col {{ width: 100%; }}
}}
</style></head><body>
<div class="container">
<header>
    <div class="brand">
        <div class="logo">{_escape(logo_text)}</div>
        <div>
            <h1>{_escape(title)}</h1>
            <div class="subtitle">{_escape(subtitle)}</div>
        </div>
    </div>
    <div class="summary-bar">
        <div class="stat">
            <span class="stat-value total">{len(videos)}</span>
            <span>Scenarios</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat">
            <span class="stat-value pass">{passed}</span>
            <span>Passed</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat">
            <span class="stat-value fail">{failed}</span>
            <span>Failed</span>
        </div>
        <span class="timestamp">{now}</span>
    </div>
</header>
{"".join(feature_sections)}
</div>
<script>
function seekTo(vidId, offset) {{
    var v = document.getElementById(vidId);
    v.currentTime = offset;
    v.play();
}}
document.querySelectorAll('video').forEach(function(v) {{
    var stepsId = v.getAttribute('data-steps-id');
    var offsets = JSON.parse(v.getAttribute('data-offsets') || '[]');
    if (!offsets.length) return;
    var stepsList = document.getElementById(stepsId);
    if (!stepsList) return;
    var items = stepsList.querySelectorAll('li');
    v.addEventListener('timeupdate', function() {{
        var t = v.currentTime;
        var activeIdx = -1;
        for (var i = 0; i < offsets.length; i++) {{
            if (t >= offsets[i]) activeIdx = i;
        }}
        items.forEach(function(li, i) {{
            li.classList.toggle('active', i === activeIdx);
        }});
        if (activeIdx >= 0 && items[activeIdx]) {{
            items[activeIdx].scrollIntoView({{block:'nearest'}});
        }}
    }});
}});
</script>
</body></html>"""

    with open(report_path, "w") as f:
        f.write(html)

    return report_path
