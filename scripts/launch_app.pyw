import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

VENV_PYTHONW = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
PYTHON_EXE = str(VENV_PYTHONW) if VENV_PYTHONW.exists() else sys.executable
MAIN_PY = PROJECT_ROOT / "desktop" / "main.py"

creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
subprocess.Popen([PYTHON_EXE, str(MAIN_PY)], cwd=str(PROJECT_ROOT), creationflags=creation_flags)
