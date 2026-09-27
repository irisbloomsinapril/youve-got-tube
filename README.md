# YGT — You've Got Tube

링크를 붙여넣고 화질을 선택하면 내 폴더에 저장하는 Python/Tkinter 데스크톱 앱입니다.

차분한 어두운 테마에서 화질과 영상 코덱을 나란히 선택합니다.

## 사용 방법

1. 앱을 열면 다운로드 엔진 업데이트를 자동으로 확인합니다.
2. **다운로드** 탭에 영상 링크를 붙여넣습니다. 여러 개는 한 줄에 하나씩 입력합니다.
3. 화질과 코덱을 선택하고 **다운로드 시작**을 누릅니다. 기본값은 1080p 이하·자동 코덱입니다.
4. **폴더 열기**로 결과를 확인합니다. 저장 폴더와 화질은 다음 실행에도 유지됩니다.

MP3가 필요하면 화질 목록에서 **오디오만 (mp3)**를 선택하세요. 자막, 재생목록, 썸네일은 선택 사항입니다. 개별 포맷이 필요할 때만 **포맷 직접 선택** 탭을 사용하세요. 조합 표와 개별 포맷 목록 모두 선택한 ID와 코덱을 그대로 사용합니다. 직접 선택한 영상은 재인코딩 없이 MKV로 병합/저장합니다. 오디오만 선택하면 원본 오디오 형식을 유지합니다.

다운로드 버튼과 진행률은 창 아래에 항상 표시됩니다. 일반 마우스 휠 및 Tk 9 고해상도 휠·트랙패드 입력을 모두 지원합니다. 상단 헤더나 탐색 버튼 위에서도 현재 본문을 스크롤할 수 있고, 표와 입력창 안에서는 해당 영역을 먼저 스크롤합니다. 넓은 표는 아래 가로 스크롤바 또는 Shift+휠을 사용하세요.

## 코덱 선택

| 선택 | 결과 | 동작 |
| --- | --- | --- |
| 자동 선택 | MP4 | 제공되는 포맷을 자동 선택 |
| H.264 | MP4 | H.264 영상 + M4A 오디오 |
| AV1 | MP4 | AV1 영상 + M4A 오디오 |
| VP9 | WebM | VP9 영상 + WebM 오디오 |
| 오디오만 | MP3 | 영상 코덱 설정을 사용하지 않고 MP3로 변환 |

특정 코덱을 고르면 다른 코덱으로 자동 변경하지 않습니다. 해당 화질·코덱·컨테이너 조합이 없으면 실패 원인을 기록에 표시합니다. 재인코딩으로 코덱을 만드는 기능은 아닙니다. 실제 제공 포맷은 영상마다 다릅니다.

## 자동 업데이트

- 앱을 **실행할 때마다** 공식 yt-dlp stable 최신 버전을 확인합니다. 오른쪽 위 **업데이트 확인**으로 다시 확인할 수도 있습니다.
- 별도의 공식 실행파일을 다운로드하고 SHA256과 실행 버전을 검증한 뒤 교체합니다.
- 기존 엔진이 있으면 업데이트 서버에 연결하지 못해도 기존 버전으로 계속 사용할 수 있습니다. 최초 설치에는 인터넷이 필요합니다.
- 작업 중에는 엔진 교체와 다운로드 설정 변경을 막습니다. 업데이트·다운로드는 GUI와 별도 스레드에서 실행됩니다.
- **자동 업데이트 대상은 yt-dlp입니다.** YGT UI 자체를 새 버전으로 바꾸려면 새 앱을 받아 교체하세요.

엔진은 macOS의 `~/Library/Application Support/YGT/engine`, Windows의 `%LOCALAPPDATA%/YGT/engine`, Linux의 `~/.local/share/YGT/engine`에 저장됩니다. 개발/테스트에서는 `YGT_ENGINE_DIR`로 변경할 수 있습니다.

## 실행에 필요한 것

배포된 앱은 Python 설치가 필요 없습니다. 다음 외부 도구는 별도로 준비해야 합니다.

- **Deno**: YouTube JavaScript 처리에 사용합니다. 설치된 Deno를 자동으로 찾고, 없으면 Node를 찾습니다. 호환 버전은 [yt-dlp EJS 공식 안내](https://github.com/yt-dlp/yt-dlp/wiki/EJS)를 따르세요.
- **FFmpeg**: 영상·오디오 병합과 MP3 변환에 사용합니다. 앱에 포함하거나 시스템에 설치하세요.

macOS Homebrew를 사용한다면:

```sh
brew install deno ffmpeg
```

Finder에서 실행해도 `/opt/homebrew/bin`, `/usr/local/bin`, `~/.deno/bin`의 Deno를 찾습니다. FFmpeg도 Homebrew 경로를 확인합니다. Windows에서는 Deno/FFmpeg를 PATH에 등록하세요.

현재 수정본은 Apple Silicon Mac에서 검증했습니다. Windows 빌드 설정과 CI는 포함하지만 실제 Windows GUI 실행은 별도 확인이 필요합니다. GitHub Actions의 기본 빌드에는 Deno/FFmpeg를 포함하지 않습니다. Apple 서명·공증도 별도입니다.

## 소스 실행

Python 3.10 이상과 Tkinter가 필요합니다. macOS에서는 Tkinter가 포함된 Python 배포판을 사용하세요.

```sh
python3 app.py
```

GUI와 엔진 연결은 표준 라이브러리만 사용합니다. `pip install yt-dlp`는 필요 없습니다.

## 앱 빌드

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./build_mac.sh
```

macOS 결과는 `dist/YGT.app`입니다. Windows에서는 가상환경 활성화 후 `build.bat`을 실행하고 **`dist/YGT` 폴더 전체**를 배포하세요.

`ffmpeg` / `ffmpeg.exe` 및 선택적으로 `ffprobe` / `ffprobe.exe`를 소스 폴더에 두면 빌드에 포함합니다. macOS에서는 `YGT_FFMPEG=/path/to/ffmpeg`로 지정할 수도 있습니다. 타인에게 배포하기 전 다른 컴퓨터에서 라이브러리 의존성과 해당 바이너리의 라이선스를 확인하세요.

GitHub의 **Actions → Build desktop apps → Run workflow**로 macOS/Windows 빌드 파일을 만들 수도 있습니다. 이 작업은 다운로드 가능한 artifact를 만들며 Release를 자동 게시하지 않습니다. macOS 빌드 아키텍처는 선택된 runner를 따릅니다.

## 테스트

```sh
python3 -m unittest discover -s tests -p "test_*.py" -v
# 실제 데스크톱 세션에서 스크롤 및 UI 동작 검증:
YGT_UI_TESTS=1 python3 -m unittest discover -s tests -p test_ui.py -v
```

업데이트 실패/검증 실패 시 기존 엔진 보존, 앱 재실행 시 확인, 수동 재확인, 옵션 전달 및 오류 전달을 검사합니다. UI 검증은 작은 창, 중첩 스크롤, 탭에 따른 다운로드 선택, 설정 저장을 확인합니다.

## GitHub에 올릴 파일

소스, `tests/`, `.github/`, 빌드 설정과 README를 올리세요. `.gitignore`는 가상환경, 빌드 결과, FFmpeg 바이너리, 백업을 제외합니다. 앱 배포 ZIP은 저장소 소스 대신 GitHub Releases에 첨부하면 됩니다.

이미 이전 버전에서 생성물을 Git으로 추적 중인 저장소라면 `.gitignore`만 추가해도 기존 추적은 사라지지 않습니다. 로컬 파일을 보존하면서 추적만 해제하려면:

```sh
git rm -r --cached --ignore-unmatch build dist __pycache__ venv .DS_Store ffmpeg ffmpeg.exe
```

그 다음 변경 내역을 확인하고 커밋하세요. 이 명령은 과거 커밋 기록을 삭제하지 않습니다.

## 오류 확인

**작업 기록**에서 메시지를 확인하거나 **기록 복사**로 공유할 수 있습니다. HTTP 403은 YouTube 서버가 데이터 요청을 거부한 것으로, 엔진 업데이트 외에도 로그인·IP·영상별 제한에 영향을 받습니다. 최신 엔진이 모든 403을 해결한다고 보장하지 않습니다.

공식 프로젝트: [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Deno](https://deno.com/) · [FFmpeg](https://ffmpeg.org/)
