"""Entry point for the packaged executable. With no arguments it opens the desktop
application; with arguments it behaves like the `fsoc-tracker` command line tool, so the
same executable can run headless benchmarks."""
from __future__ import annotations

import os
import shutil
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
                except (OSError, NotImplementedError):
                    # Windows needs a privilege for symlinks; a copy is small and works everywhere.
                    try:
                        shutil.copytree(internal / name, base / name)
                    except OSError:
                        pass


def _absolutise(args: list[str]) -> list[str]:
    """Relative file paths on the command line mean 'relative to where I launched from',
    so resolve them before the working directory moves into the bundle."""
    out = []
    for a in args:
        p = Path(a)
        if not a.startswith("-") and not p.is_absolute() and (p.exists() or p.parent.exists() and p.suffix):
            out.append(str(p.resolve()))
        else:
            out.append(a)
    return out


def main():
    args = _absolutise(sys.argv[1:])
    _chdir_to_bundle()
    if args:
        from fsoc_tracker.cli import main as cli_main
        return cli_main(args)
    from fsoc_tracker.gui.app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
