# PyInstaller spec for the desktop app.
#
# Build with:
#   pyinstaller pyinstaller_desktop.spec
#
# Output goes to dist/LinguaFusion/ as a folder (onedir, not onefile) --
# onedir starts faster and is much easier to debug if something's missing,
# at the cost of being a folder instead of a single .exe. The Inno Setup
# script installs the whole folder either way, so this doesn't change the
# end-user experience.

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_dynamic_libs

diagnostic_console = os.environ.get('LF_PYINSTALLER_CONSOLE', '').strip() == '1'

datas = [
    ('desktop/assets', 'assets'),
    ('desktop/design', 'design'),
    ('desktop', 'desktop'),
    ('backend/mobile_web', 'backend/mobile_web'),
    ('backend/owner_web', 'backend/owner_web'),
]
binaries = []
hiddenimports = [
    'desktop',
    'desktop.iconography',
    'desktop.main',
    'pydub',
    'sounddevice',
    'soundfile',
    'pygame',
    'uvicorn',
    'fastapi',
]

for pkg in ['torch', 'ctranslate2', 'faster_whisper', 'transformers', 'onnxruntime', 'rapidocr_onnxruntime', 'piper']:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

hiddenimports += collect_submodules('backend')

a = Analysis(
    ['desktop/main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Qt 6.11 uses Windows' ICU API (unversioned symbols). Build-time PATH can
# contain Poppler's unrelated ICU DLL, whose suffixed symbols break QtCore
# before the app opens. Let Windows resolve its own system component.
if os.name == 'nt' and os.path.isfile(os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'icuuc.dll')):
    a.binaries = [entry for entry in a.binaries if entry[0].replace('\\', '/').lower() != 'icuuc.dll']

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LinguaFusion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=diagnostic_console,
    icon='desktop/assets/linguafusion.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LinguaFusion',
)
