"""Entry point for the packaged executable. With no arguments it opens the desktop
application; with arguments it behaves like the `fsoc-tracker` command line tool, so the
same executable can run headless benchmarks."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _chdir_to_bundle():
    """Packaged runs resolve configs/, models/ and results/ next to the executable."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        os.chdir(base)
        internal = base / "_internal"
        for name in ("configs", "models", "docs"):
            if not (base / name).exists() and (internal / name).exists():
                try:
                    os.symlink(internal / name, base / name, target_is_directory=True)
                except OSError:
                    pass


def main():
    _chdir_to_bundle()
    if len(sys.argv) > 1:
        from fsoc_tracker.cli import main as cli_main
        return cli_main(sys.argv[1:])
    from fsoc_tracker.gui.app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
