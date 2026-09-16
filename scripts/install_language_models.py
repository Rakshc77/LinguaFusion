"""Compatibility entry point for the unified seven-language installer."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.install_arabic_odia_models import main


if __name__ == "__main__":
    raise SystemExit(main())
