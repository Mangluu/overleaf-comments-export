from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from pathlib import Path

from . import __version__
from .client import OverleafClient, UserFacingError
from .export import ExportResult, run_export


def _no_tkinter_message() -> str:
    """Platform-specific instructions for installing Python's GUI toolkit."""
    if sys.platform == "darwin":
        fix = (
            "Install Python from python.org (it includes the GUI toolkit), or\n"
            "with Homebrew run:\n\n"
            "  brew install python-tk"
        )
    elif sys.platform.startswith("win"):
        fix = (
            "Re-run the Python installer from python.org, choose \"Modify\", and\n"
            "tick \"tcl/tk and IDLE\"."
        )
    else:
        fix = (
            "Install it with your package manager, for example:\n\n"
            "  Debian/Ubuntu : sudo apt install python3-tk\n"
            "  Fedora        : sudo dnf install python3-tkinter\n"
            "  Arch          : sudo pacman -S tk"
        )
    return (
        "The window cannot open because this Python has no GUI toolkit "
        "installed.\n\n"
        f"{fix}\n\n"
        "Or skip the window entirely and use the command line:\n\n"
        "  overleaf-comments-export --project-url <your project link> --out ./comments"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="overleaf-comments-export",
        description="Export Overleaf comment threads and tracked changes to Markdown.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the graphical interface (default if no other args).",
    )
    parser.add_argument(
        "--project-url",
        help="Full Overleaf project URL, e.g. https://www.overleaf.com/project/<24-hex-id>.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Directory to write comments-<date>.md, comments.json, and comments.log into.",
    )
    parser.add_argument(
        "--project-title",
        default=None,
        help="Optional human-readable title for the report header. Defaults to the project id.",
    )
    parser.add_argument(
        "--browser",
        default="auto",
        choices=list(OverleafClient.SUPPORTED_BROWSERS),
        help="Which browser to read cookies from. Default: auto-detect.",
    )
    parser.add_argument(
        "--cookie",
        default=None,
        metavar="VALUE",
        help="Overleaf session cookie, pasted from your browser (DevTools → "
        "Application → Cookies → overleaf_session2). Use this when reading "
        "cookies from the browser fails. Also read from the OVERLEAF_SESSION "
        "environment variable.",
    )
    parser.add_argument(
        "--base-url",
        default="https://www.overleaf.com",
        help="Override the Overleaf base URL (for self-hosted instances).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="More logging."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--render-mode",
        choices=["compact", "detailed"],
        default="compact",
        help="Markdown layout: 'compact' (one line per comment, default) or "
        "'detailed' (multi-line code-fence with anchor highlighted).",
    )
    parser.add_argument(
        "--no-open",
        dest="include_open",
        action="store_false",
        help="Skip open (unresolved) comments.",
    )
    parser.add_argument(
        "--no-resolved",
        dest="include_resolved",
        action="store_false",
        help="Skip resolved comments.",
    )
    parser.add_argument(
        "--no-changes",
        dest="include_changes",
        action="store_false",
        help="Skip tracked changes.",
    )
    parser.add_argument(
        "--reviewer",
        action="append",
        default=[],
        metavar="NAME",
        help="Only include threads/changes touching this reviewer "
        "(case-insensitive substring match against name and email). "
        "Pass multiple times for OR-of-reviewers.",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Embed the unprocessed Overleaf API payloads inside comments.json.",
    )
    parser.add_argument(
        "--no-jsonl",
        dest="write_jsonl",
        action="store_false",
        help="Skip writing comments.jsonl (the streaming-friendly companion).",
    )
    parser.add_argument(
        "--response-letter",
        action="store_true",
        help="Also write response-letter.md: a point-by-point reply document "
        "pre-filled with every open comment, grouped by who raised it, with "
        "blanks for your response.",
    )
    parser.add_argument(
        "--per-reviewer",
        action="store_true",
        help="Also write one Markdown per reviewer into by-reviewer/.",
    )
    parser.set_defaults(
        include_open=True,
        include_resolved=True,
        include_changes=True,
        write_jsonl=True,
    )
    args = parser.parse_args(argv)

    if args.gui or (not args.project_url and not args.out):
        try:
            from .gui import launch_gui
        except ImportError:
            # tkinter is NOT bundled with Python everywhere — most Linux
            # distributions ship it as a separate system package, and it is
            # missing from some minimal/conda builds.
            print(_no_tkinter_message(), file=sys.stderr)
            return 1
        try:
            return launch_gui()
        except Exception as e:
            # Typically TclError on a headless machine (SSH, server, container).
            if "display" in str(e).lower() or type(e).__name__ == "TclError":
                print(
                    "There is no screen to open a window on.\n\n"
                    "This looks like a computer without a desktop (a server, or "
                    "a remote session). Use the command line instead, for "
                    "example:\n\n"
                    "  overleaf-comments-export --project-url <your project link> "
                    "--out ./comments\n\n"
                    "Run with --help to see every option.",
                    file=sys.stderr,
                )
                return 1
            raise

    if not args.project_url or not args.out:
        parser.error("--project-url and --out are required in CLI mode (or pass --gui).")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    cookie_value = args.cookie or os.environ.get("OVERLEAF_SESSION") or None

    try:
        result: ExportResult = run_export(
            project_url=args.project_url,
            out_dir=args.out,
            project_title=args.project_title,
            base_url=args.base_url,
            browser=args.browser,
            cookie_value=cookie_value,
            verbose=args.verbose,
            include_raw=args.include_raw,
            include_open=args.include_open,
            include_resolved=args.include_resolved,
            include_changes=args.include_changes,
            reviewer_filter=args.reviewer,
            render_mode=args.render_mode,
            write_jsonl=args.write_jsonl,
            per_reviewer_reports=args.per_reviewer,
            response_letter=args.response_letter,
            progress=lambda msg: print(msg, file=sys.stderr),
        )
    except UserFacingError as e:
        # Expected, explainable failures: no traceback, just what to do next.
        print(f"\n{e}", file=sys.stderr)
        return 1
    except Exception:
        # Unexpected: show the traceback, but also tell people where to send it.
        # The moment something breaks is the only moment we have their attention.
        traceback.print_exc()
        print(
            f"\nThat looks like a bug in overleaf-comments-export {__version__}.\n"
            "Please report it (copy the lines above) at\n"
            "  https://github.com/Mangluu/overleaf-comments-export/issues/new/choose\n"
            "It probably affects other people too, and it cannot be fixed if "
            "nobody says anything.",
            file=sys.stderr,
        )
        return 2
    print(f"\nDone. Open: {result.markdown_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
