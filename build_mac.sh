#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${YGT_PYTHON:-python3}"
"$PYTHON" -m PyInstaller --noconfirm --clean YGT.spec
printf '\n완료: dist/YGT.app\n'
