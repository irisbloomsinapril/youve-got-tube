# YGT (You've Got Tube)

yt-dlp를 감싼 간단한 GUI 다운로더입니다. 창에서 URL만 붙여넣으면 다운로드됩니다.

## 파일 구성

- `app.py` — 앱 소스코드 (tkinter GUI, Windows/Mac 공용)
- `requirements.txt` — 필요한 패키지 목록
- `build.bat` — Windows용 exe 패키징 스크립트
- `build_mac.sh` — macOS용 .app 패키징 스크립트
- `ygt_logo.png` — (선택) 로고 이미지. 있으면 앱 헤더/창 아이콘에 자동으로 쓰입니다.

## 로고 적용 방법 (선택)

생성해드린 로고 이미지를 `ygt_logo.png`라는 이름으로 `app.py`가 있는 이 폴더에 저장하세요.
- 넣으면: 앱 실행 시 상단 헤더와 창(작업표시줄) 아이콘에 자동으로 표시됩니다.
- exe/앱 파일 자체의 아이콘(탐색기에서 보이는 아이콘)까지 바꾸고 싶다면 추가 변환이 필요합니다.
  - Windows: `ygt_logo.png`를 무료 온라인 변환기(예: icoconvert.com, convertio.co)로 `.ico`로 변환 → `ygt.ico`로 이 폴더에 저장 → `build.bat`이 자동으로 인식해 적용합니다.
  - Mac: 같은 방식으로 `.icns`로 변환 → `ygt.icns`로 저장 → `build_mac.sh`가 자동 인식합니다.
  - 두 파일 다 없어도 빌드는 정상 진행되며, 그 경우 기본 아이콘으로 빌드됩니다.

## 중요: Windows용과 Mac용은 따로 빌드해야 합니다

PyInstaller는 "지금 실행 중인 OS용"으로만 빌드합니다. 즉:
- Windows PC에서 `build.bat`을 실행하면 **Windows용 .exe**만 나옵니다.
- macOS에서 `build_mac.sh`를 실행하면 **Mac용 .app**만 나옵니다.
- Windows에서 Mac용을 만들거나 그 반대는 불가능합니다.

맥북 사용자에게도 배포하려면, Mac 컴퓨터(본인 것이든 지인 것이든)에서 `build_mac.sh`를 한 번 실행해서 `.app` 파일을 따로 만들어야 합니다. Mac이 없다면 지인에게 이 폴더를 통째로 보내 macOS에서 빌드를 부탁하면 됩니다.

## Windows용 exe 만들기 (Windows PC에서 1회 실행)

exe를 만드는 사람 컴퓨터에만 Python이 필요합니다. exe를 받는 사람은 Python이 전혀 필요 없습니다.

1. [python.org](https://www.python.org/downloads/)에서 Python 설치 (설치 시 "Add to PATH" 체크)
2. [ffmpeg 다운로드](https://www.gyan.dev/ffmpeg/builds/)에서 "release essentials" zip을 받아 압축 해제 후, 안에 있는 `bin\ffmpeg.exe`를 이 폴더(`app.py`가 있는 폴더)로 복사
3. (선택) 로고를 넣으려면 위 "로고 적용 방법" 참고
4. 이 폴더에서 `build.bat` 더블클릭
5. 완료되면 `dist\YGT.exe` 파일 생성됨

## Mac용 .app 만들기 (Mac에서 1회 실행)

빌드하는 Mac에만 Python(3.9 이상)이 필요합니다. 앱을 받는 사람은 Python이 전혀 필요 없습니다.

1. macOS에 Python3가 없다면 설치: `python.org`에서 받거나, Homebrew가 있다면 `brew install python`
2. ffmpeg 바이너리 준비 (둘 중 하나):
   - Homebrew 사용: `brew install ffmpeg` 후 `cp $(which ffmpeg) ./ffmpeg`
   - 정적 빌드: [evermeet.cx/ffmpeg](https://evermeet.cx/ffmpeg/)에서 받아 압축 해제 후 `ffmpeg`라는 이름으로 이 폴더에 복사
3. (선택) 로고를 넣으려면 위 "로고 적용 방법" 참고
4. 터미널에서 이 폴더로 이동 후:
   ```
   chmod +x build_mac.sh
   ./build_mac.sh
   ```
5. 완료되면 `dist/YGT.app` 생성됨

### Mac에서 받는 사람이 실행할 때 "확인되지 않은 개발자" 경고가 뜨면

Apple 개발자 서명이 없는 앱이라 macOS Gatekeeper가 처음엔 막습니다. 받는 사람에게 다음 중 하나를 안내하세요:
- `YGT.app`을 **우클릭(또는 control+클릭) → 열기** → 뜨는 창에서 다시 "열기" 클릭 (최초 1회만 필요)
- 또는 터미널에서: `xattr -cr /path/to/YGT.app` 실행 후 실행

## 배포 방법

Windows 사용자에게는 `dist\YGT.exe`를, Mac 사용자에게는 `dist/YGT.app`을 전달하세요 (카카오톡, 구글 드라이브, USB 등 무엇이든 상관없음).
받는 사람은 그냥 더블클릭해서 실행하면 됩니다 (Mac은 위 Gatekeeper 안내 참고). 설치나 Python 필요 없음.

## 앱 사용법

### A. 영상 1개, 화질/코덱 정밀 선택

1. YGT 실행
2. URL 1개 붙여넣고 "🔍 정보 가져오기" 클릭
3. **추천 조합** 표에 영상+음성이 자동으로 합쳐진 조합이 고화질 순(위가 고화질)으로 뜸. 원하는 줄을 더블클릭하면 바로 다운로드 시작 (한 번 클릭으로 끝)
   - 코덱이 avc1(H.264)인 항목은 "편집 프로그램 호환 좋음"이라고 표시됨 — 프리미어 프로 등에서 바로 불러오기 좋은 코덱
   - 표 아래 작은 안내문에도 편집용 추천 코덱이 적혀 있음
4. 더 세밀하게 고르고 싶으면 "전체 포맷 목록(고급)"에서 Ctrl+클릭으로 영상 1개 + 음성 1개를 직접 조합해서 "다운로드 시작" 클릭 가능
5. 필요하면 재생목록 전체 다운로드, 자막 다운로드, mp3 변환 체크
6. 저장 위치 확인/변경
7. 다운로드가 시작되면 진행률 바에 실시간 퍼센트/속도/남은시간이 표시됨

### B. 여러 영상 한 번에 다운로드

1. URL 입력창에 한 줄에 하나씩 여러 개 붙여넣기 → 화면 상단 안내 문구가 "📦 링크 N개 입력됨"으로 바뀌고, "2. 단일 링크 모드" 섹션은 자동으로 비활성화되며 "3. 여러 링크 일괄 다운로드" 섹션이 활성 상태가 됩니다
2. "👀 제목 미리보기" 클릭 → URL 옆에 바로 제목/길이가 표로 뜨면서 링크를 제대로 넣었는지 확인 가능 (잘못된 링크는 ❌ 표시)
3. 표에서 **원하는 영상 제목을 더블클릭하면 그 영상 하나만 바로 다운로드**됩니다 (일괄 다운로드 화질 설정 적용)
4. 여러 개를 한 번에 받고 싶으면 "일괄 다운로드 화질" 드롭다운에서 화질/mp3 선택 후 "다운로드 시작" 클릭 → 순서대로 하나씩 다운로드되며, 하나가 실패해도 나머지는 계속 진행됨

※ 화면 상단 배너가 현재 몇 개의 링크가 입력되어 있는지, 어느 섹션을 써야 하는지 항상 알려줍니다.

## 참고

- Windows Defender/백신이 PyInstaller로 만든 exe를 처음 보는 프로그램이라 경고할 수 있습니다 (오탐). 필요하면 "추가 정보 → 실행"으로 진행하세요.
- 저작권이 있는 콘텐츠 다운로드는 유튜브 이용약관 및 저작권법 위반 소지가 있으니, 개인 소장 등 허용된 범위 내에서만 사용하세요.
- yt-dlp는 유튜브 쪽 변경사항에 따라 가끔 업데이트가 필요합니다. 다운로드가 안 되기 시작하면 `requirements.txt`의 yt-dlp 버전을 최신으로 올리고 다시 빌드하세요.
