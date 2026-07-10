# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['av', 'mutagen', 'mutagen.mp4', 'piexif', 'PIL', 'PIL.Image', 'timezonefinder', 'pytz', 'tzlocal', 'video_utils', 'snap_utils', 'zip_utils', 'downloader', 'exif_utils']
datas += collect_data_files('timezonefinder')
tmp_ret = collect_all('av')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['download_snapchat_memories_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SnapchatMemoriesDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# On macOS, wrap the executable in a double-clickable .app bundle.
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='SnapchatMemoriesDownloader.app',
        icon=None,
        bundle_identifier='com.ethanwheatthin.snapchatmemoriesdownloader',
        info_plist={
            'NSHighResolutionCapable': True,
        },
    )
