"""Entry point for the PyInstaller-bundled MoldGen backend."""

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    base = Path(sys.executable).parent
    sys.path.insert(0, str(base))

from moldgen.main import main  # noqa: E402

if __name__ == "__main__":
    main()
