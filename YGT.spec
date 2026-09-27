# Build from this file on macOS, Windows or Linux. Engine updates independently.
import sys
import os
from pathlib import Path
root = Path(SPECPATH)
binaries = [(str(root / name), '.') for name in ('ffmpeg', 'ffprobe', 'ffmpeg.exe', 'ffprobe.exe') if (root / name).is_file()]
if os.environ.get('YGT_FFMPEG'):
    binaries.append((os.environ['YGT_FFMPEG'], '.'))
a = Analysis([str(root / 'app.py')], pathex=[str(root)], binaries=binaries,
             datas=[(str(root / 'ygt_logo.png'), '.')], hiddenimports=[],
             excludes=['yt_dlp'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='YGT', console=False,
          argv_emulation=False, upx=False)
collection = COLLECT(exe, a.binaries, a.datas, name='YGT', strip=False, upx=False)
if sys.platform == 'darwin':
    app = BUNDLE(collection, name='YGT.app', bundle_identifier='io.github.irisbloomsinapril.ygt',
                 info_plist={'CFBundleShortVersionString': '2.1.0', 'NSHighResolutionCapable': True})
