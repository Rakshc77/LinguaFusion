"""Entry point for the frozen LinguaFusionServer.exe.

PyInstaller needs a plain Python script to target -- it can't freeze the
`python -m uvicorn backend.server:app` command line directly. This does the
same thing programmatically, with --reload disabled (that flag is a dev
convenience that doesn't make sense in a frozen, installed app: there's no
source file to watch for changes since everything is bundled).

IMPORTANT: the app is imported directly (`from backend.server import app`)
rather than passed as the string "backend.server:app". uvicorn accepts
both forms, but the string form is a dynamic/runtime lookup that
PyInstaller's static analyzer can't follow -- it would never discover that
the `backend` package needs to be bundled at all, and the frozen exe fails
at startup with "ModuleNotFoundError: No module named 'backend'". Importing
the object directly makes it a normal, traceable import.
"""

import multiprocessing

if __name__ == "__main__":
    # Required on Windows when a frozen app spawns subprocesses/threads
    # that themselves might try to re-run the entry point.
    multiprocessing.freeze_support()

    import os
    import sys
    from pathlib import Path

    def _register_cuda_dll_dirs() -> None:
        seen_dirs = set()
        search_roots = []
        if getattr(sys, "frozen", False):
            search_roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)))
        else:
            proj_dir = Path(__file__).resolve().parents[1]
            venv_site = proj_dir / ".venv" / "Lib" / "site-packages"
            search_roots.extend([venv_site, proj_dir])

        for base_dir in search_roots:
            if not base_dir.exists():
                continue
            for dll_name in ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll", "cudart64_12.dll", "nvJitLink_120_0.dll"):
                for dll_path in base_dir.rglob(dll_name):
                    parent = dll_path.parent
                    if parent not in seen_dirs:
                        seen_dirs.add(parent)
                        try:
                            os.add_dll_directory(str(parent))
                            os.environ["PATH"] = str(parent) + os.pathsep + os.environ.get("PATH", "")
                        except (AttributeError, OSError):
                            pass

    _register_cuda_dll_dirs()

    import uvicorn
    from backend.server import app as fastapi_app

    uvicorn.run(
        fastapi_app,
        # Desktop-only installs stay loopback-bound by default. The dedicated
        # mobile launcher opts into LAN access and API-key pairing explicitly.
        host=os.environ.get("LINGUAFUSION_HOST", "127.0.0.1"),
        port=8000,
    )
