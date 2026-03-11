"""Generate a combined HTML report from all E2E recordings.

This test runs last (via naming convention) and generates a single
HTML report showing all the application recordings side by side.
"""

import glob
import os

from thea import generate_report

from conftest import OUTPUT_DIR


def test_z_generate_combined_report():
    """Generate a combined report from all recordings in the output dir."""
    recordings = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.mp4")))

    if not recordings:
        print("No recordings found — skipping report generation")
        return

    videos = []
    for rec_path in recordings:
        name = os.path.basename(rec_path).replace(".mp4", "").replace("_", " ").title()
        # Categorise by filename
        if "selenium" in rec_path.lower():
            feature = "Browser Recording"
        elif "xterm" in rec_path.lower():
            feature = "Terminal Recording"
        elif "gnumeric" in rec_path.lower():
            feature = "GUI App Recording"
        elif "dogfood" in rec_path.lower():
            feature = "Dogfooding"
        else:
            feature = "Recording"

        videos.append({
            "feature": feature,
            "scenario": name,
            "status": "passed",
            "video": rec_path,
        })

    report_path = generate_report(
        videos,
        output_dir=OUTPUT_DIR,
        title="Thea E2E Application Recordings",
    )

    assert os.path.exists(report_path)
    print(f"\nCombined report: {report_path}")
    print(f"Includes {len(recordings)} recordings:")
    for r in recordings:
        size = os.path.getsize(r)
        print(f"  - {os.path.basename(r)} ({size:,} bytes)")
