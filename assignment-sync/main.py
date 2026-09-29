import argparse
from pathlib import Path

from calendar_sync import sync_assignments
from html_assignment_parser import extract_assignments_from_pages, load_html_inputs


def find_default_html_files():
    input_dir = Path("html_inputs")
    if not input_dir.exists():
        return []
    return sorted(input_dir.glob("*.html"))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract assignments from raw HTML and sync them to Google Calendar."
    )
    parser.add_argument(
        "html_files",
        nargs="*",
        help="One or more HTML files copied from assignment webpages.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print extracted assignments without creating Google Calendar events.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    html_files = args.html_files or find_default_html_files()

    if not html_files:
        print("\nNo HTML files provided.")
        print("Pass files directly, or place .html files in an html_inputs folder.")
        return

    print("Reading assignment pages...")
    pages = load_html_inputs(html_files)

    print("\nExtracting assignments from HTML...")
    assignments = extract_assignments_from_pages(pages)

    if not assignments:
        print("\nNo assignments found.")
        return

    print(f"\nFound {len(assignments)} total assignments.")

    if args.dry_run:
        for assignment in assignments:
            print(
                f"  {assignment['name']} ({assignment['course']}) "
                f"due {assignment['due'].strftime('%b %d %I:%M %p')}"
            )
        return

    sync_assignments(assignments)


if __name__ == "__main__":
    main()