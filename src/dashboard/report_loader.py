
"""
INNEVA.E - AI REPORT LOADER
Module 16 - Checkpoint 16.4A

Responsibilities:
- Discover locally generated AI reports
- Read Markdown and JSON report pairs
- Validate report file structure
- Provide report metadata
- Avoid modifying existing reports

Read-only operations.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REPORT_DIRECTORY = (
    PROJECT_ROOT
    / "reports"
    / "energy_intelligence"
)


def discover_reports():
    """
    Discover Markdown reports with matching JSON files.

    Returns newest files first, based on the
    report filename.
    """

    if not REPORT_DIRECTORY.is_dir():
        return []

    reports = []

    for markdown_path in REPORT_DIRECTORY.glob(
        "energy_report_*.md"
    ):

        json_path = markdown_path.with_suffix(
            ".json"
        )

        if not json_path.is_file():
            continue

        reports.append(
            {
                "report_id": markdown_path.stem,
                "markdown_path": markdown_path,
                "json_path": json_path,
                "modified_at_utc": datetime.fromtimestamp(
                    markdown_path.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat(),
            }
        )

    return sorted(
        reports,
        key=lambda item: item["report_id"],
        reverse=True,
    )


def load_report(report):
    """
    Load the Markdown and JSON contents
    of a selected report.
    """

    markdown_path = Path(
        report["markdown_path"]
    )

    json_path = Path(
        report["json_path"]
    )

    if not markdown_path.is_file():
        raise FileNotFoundError(
            markdown_path
        )

    if not json_path.is_file():
        raise FileNotFoundError(
            json_path
        )

    markdown_content = markdown_path.read_text(
        encoding="utf-8"
    )

    with json_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        json_content = json.load(file)

    if not markdown_content.strip():
        raise ValueError(
            "Markdown report is empty."
        )

    if not isinstance(json_content, dict):
        raise ValueError(
            "JSON report must contain an object."
        )

    return {
        "report_id": report["report_id"],
        "markdown": markdown_content,
        "json": json_content,
        "markdown_path": markdown_path,
        "json_path": json_path,
        "modified_at_utc": report["modified_at_utc"],
    }


def inspect_reports():
    """
    Display discovered report files
    and validate the newest report.
    """

    print("=" * 65)
    print("INNEVA.E - AI REPORT INSPECTION")
    print("=" * 65)

    print("\nReport directory:")
    print(REPORT_DIRECTORY)

    reports = discover_reports()

    print("\nReport pairs discovered:", len(reports))

    for report in reports:
        print(
            f"  - {report['report_id']}"
        )

    if not reports:
        print(
            "\nNo complete Markdown/JSON report pairs found."
        )
        return

    latest = load_report(reports[0])

    print("\nLatest report:")
    print(latest["report_id"])

    print("\nMarkdown characters:")
    print(len(latest["markdown"]))

    print("\nJSON top-level keys:")
    for key in latest["json"]:
        print(f"  - {key}")

    print("\nReport validation: PASSED")


if __name__ == "__main__":
    inspect_reports()
