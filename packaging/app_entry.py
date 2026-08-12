"""Entry point for the packaged, double-clickable application."""
import sys

from overleaf_comments_export.gui import launch_gui

if __name__ == "__main__":
    sys.exit(launch_gui())
