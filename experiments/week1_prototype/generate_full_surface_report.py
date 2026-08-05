"""Generate the committed full API framework-comparison snapshot."""

from __future__ import annotations

from pathlib import Path

from framework_comparison.full_surface import write_full_surface_report


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = (
    ROOT
    / "experiments"
    / "week1_prototype"
    / "framework_comparison"
    / "full_surface_snapshot.json"
)


if __name__ == "__main__":
    report = write_full_surface_report(OUTPUT)
    scope = report["scope"]
    authenticated = report["fastapi"]["authenticated_probe"]
    print(
        f"wrote {OUTPUT}: {scope['path_count']} paths / "
        f"{scope['operation_count']} operations / "
        f"unhandled 5xx={authenticated['unhandled_server_error_count']}"
    )

