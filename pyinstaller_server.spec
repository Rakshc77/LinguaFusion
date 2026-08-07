# PyInstaller spec for the backend server -> LinguaFusionServer.exe
#
# Build with:
#   pyinstaller pyinstaller_server.spec
#
# HONEST WARNING, given today's history: this bundles torch, ctranslate2,
# faster-whisper, transformers, onnxruntime, and rapidocr -- several of
# these (especially torch and ctranslate2) are known-tricky to freeze
# correctly with PyInstaller because they load compiled extensions and
# CUDA DLLs dynamically at runtime rather than through normal Python
# imports PyInstaller can trace. This is the *same class* of problem as
# the cuBLAS/cuDNN DLL discovery issue solved earlier this project (see
# CLAUDE.md) -- do not be surprised if the frozen server.exe fails to find
# a CUDA DLL that works fine when run from source, and needs a similar
# os.add_dll_directory-style fix, or needs the relevant DLLs added to
# `binaries=` below explicitly. Test this build early and expect at least
# one iteration.

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_dynamic_libs

datas = []
binaries = []
hiddenimports = []

for pkg in ['torch', 'ctranslate2', 'faster_whisper', 'transformers', 'onnxruntime', 'rapidocr_onnxruntime', 'spacy']:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

binaries += collect_dynamic_libs('nvidia.cublas')
binaries += collect_dynamic_libs('nvidia.cuda_runtime')
binaries += collect_dynamic_libs('nvidia.nvjitlink')
binaries += collect_dynamic_libs('nvidia.cudnn')

# The codebase has several imports that happen inside function bodies
# rather than at module top-level (rapidocr_service, nllb_translation_service,
# and the Ollama-based ocr_correct_text are all imported this way, since
# they're optional/lazy-loaded features). PyInstaller's static analyzer
# only traces imports it can see without running the code, so these get
# silently missed unless explicitly swept in here.
hiddenimports += collect_submodules('backend')

hiddenimports += [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'argostranslate',
    'pytesseract',
    'fitz',
    'docx',
    'bs4',
    'striprtf',
]

a = Analysis(
    ['backend/run_server.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LinguaFusionServer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon='desktop/assets/linguafusion.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        'cublas64_12.dll',
        'cublasLt64_12.dll',
        'cudnn64_9.dll',
        'cudnn_adv64_9.dll',
        'cudnn_cnn64_9.dll',
        'cudnn_engines_precompiled64_9.dll',
        'cudnn_engines_runtime_compiled64_9.dll',
        'cudnn_graph64_9.dll',
        'cudnn_heuristic64_9.dll',
        'cudnn_ops64_9.dll',
        'cudart64_12.dll',
        'nvJitLink_120_0.dll',
    ],
    name='LinguaFusionServer',
)
