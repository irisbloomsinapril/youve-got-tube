#!/bin/bash
# ============================================
#  YGT (You've Got Tube) - macOS 빌드 스크립트
#  빌드하는 사람만 1회 실행하면 됩니다 (macOS + Python 필요).
#  배포 후 받는 사람은 Python 설치가 필요 없습니다.
#
#  실행 방법:
#   1) 터미널에서 이 폴더로 이동
#      cd /path/to/이폴더
#   2) (선택) 로고를 앱 아이콘으로 쓰려면 ygt.icns 파일을 이 폴더에 준비
#      (ygt_logo.png를 무료 온라인 변환기(예: cloudconvert.com)로 .icns로 바꿔서 준비)
#   3) 실행 권한 부여 (최초 1회)
#      chmod +x build_mac.sh
#   4) 실행
#      ./build_mac.sh
#   5) dist/YGT.app 생성 완료 -> 이 파일(.app)을 배포
# ============================================

set -e

echo "[1/5] 필요한 패키지 설치 중..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install pyinstaller

if [ ! -f "ffmpeg" ]; then
    echo ""
    echo "[경고] ffmpeg 바이너리가 이 폴더에 없습니다."
    echo "다음 중 하나로 준비하세요:"
    echo "  A) Homebrew가 있다면:"
    echo "       brew install ffmpeg"
    echo "       cp \$(which ffmpeg) ./ffmpeg"
    echo "  B) 정적 빌드 받기: https://evermeet.cx/ffmpeg/ 에서 다운로드 후"
    echo "     압축 풀어 이 폴더에 'ffmpeg' 라는 이름으로 넣기"
    echo ""
    read -p "ffmpeg 없이 계속 진행할까요? (mp4 병합/mp3 변환 불가) [y/N] " yn
    if [ "$yn" != "y" ] && [ "$yn" != "Y" ]; then
        echo "빌드를 중단합니다. ffmpeg를 준비한 뒤 다시 실행하세요."
        exit 1
    fi
fi

if [ ! -f "ygt.icns" ]; then
    echo "[안내] ygt.icns가 없어 기본 아이콘으로 빌드됩니다. 로고를 앱 아이콘으로 쓰려면"
    echo "ygt_logo.png를 .icns로 변환해 ygt.icns로 이 폴더에 넣고 다시 실행하세요."
fi

echo "[2/5] 이전 빌드 정리 중..."
rm -rf build dist "YGT.spec"

echo "[3/5] app 빌드 중... (몇 분 걸릴 수 있습니다)"
ICON_OPT=()
if [ -f "ygt.icns" ]; then
    ICON_OPT=(--icon "ygt.icns")
fi
DATA_OPT=()
if [ -f "ygt_logo.png" ]; then
    DATA_OPT=(--add-data "ygt_logo.png:.")
fi

if [ -f "ffmpeg" ]; then
    chmod +x ffmpeg
    pyinstaller --noconfirm --onefile --windowed --name "YGT" "${ICON_OPT[@]}" "${DATA_OPT[@]}" --add-binary "ffmpeg:." app.py
else
    pyinstaller --noconfirm --onefile --windowed --name "YGT" "${ICON_OPT[@]}" "${DATA_OPT[@]}" app.py
fi

echo "[4/5] 실행 권한 및 격리 속성 정리 중..."
chmod +x "dist/YGT.app/Contents/MacOS/YGT" 2>/dev/null || true
xattr -cr "dist/YGT.app" 2>/dev/null || true

echo "[5/5] 완료!"
echo ""
echo "dist/YGT.app 이 생성되었습니다."
echo "이 .app 파일을 다른 사람에게 전달하면 됩니다 (Python 설치 불필요)."
echo "단, Apple 개발자 서명이 없는 앱이라 받는 사람이 처음 실행할 때"
echo "'확인되지 않은 개발자' 경고가 뜰 수 있습니다. README.md의 안내를 참고하세요."
