"""External, independently updated yt-dlp backend for the existing YGT UI."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections import deque

_LOCK = threading.Lock()
_CHECKED = False
API = 'https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest'

def engine_dir():
    if os.environ.get('YGT_ENGINE_DIR'):
        return Path(os.environ['YGT_ENGINE_DIR'])
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/YGT/engine'
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'YGT/engine'
    return Path.home() / '.local/share/YGT/engine'

def _asset_name():
    if sys.platform == 'darwin':
        return 'yt-dlp_macos'
    if os.name == 'nt':
        return 'yt-dlp.exe'
    return 'yt-dlp_linux_aarch64' if platform.machine() in ('arm64', 'aarch64') else 'yt-dlp_linux'

def _read(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'YGT-Updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()

def _run(args, **kwargs):
    return subprocess.run(args, text=True, encoding='utf-8', errors='replace',
                          capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, **kwargs)

def ensure_engine(log=lambda text: None, force=False):
    """Check once per app session, or on explicit refresh; replace only after verification."""
    global _CHECKED
    with _LOCK:
        folder = engine_dir()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ('yt-dlp.exe' if os.name == 'nt' else 'yt-dlp')
        stamp = folder / 'last-check'
        if _CHECKED and target.exists() and not force:
            return str(target)
        log('yt-dlp 최신 버전 확인 중...')
        staged = None
        try:
            release = json.loads(_read(API))
            version = release['tag_name']
            current = _run([str(target), '--version'], timeout=20).stdout.strip() if target.exists() else ''
            if current != version:
                name = _asset_name()
                assets = {a['name']: a for a in release['assets']}
                url = assets[name]['browser_download_url']
                checks_url = assets['SHA2-256SUMS']['browser_download_url']
                for address in (url, checks_url):
                    if not address.startswith('https://github.com/yt-dlp/yt-dlp/releases/download/'):
                        raise RuntimeError('공식 배포 주소가 아닙니다.')
                sums = _read(checks_url).decode()
                expected = next(line.split()[0] for line in sums.splitlines()
                                if len(line.split()) == 2 and line.split()[1].lstrip('*') == name)
                log(f'yt-dlp {version} 다운로드 중...')
                fd, staged = tempfile.mkstemp(prefix='yt-dlp-', suffix='.exe' if os.name == 'nt' else '', dir=folder)
                digest = hashlib.sha256()
                with os.fdopen(fd, 'wb') as output:
                    with urllib.request.urlopen(url, timeout=60) as response:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                            digest.update(chunk)
                if digest.hexdigest() != expected:
                    raise RuntimeError('다운로드 파일의 SHA256 검증에 실패했습니다.')
                os.chmod(staged, 0o755)
                check = _run([staged, '--version'], timeout=30)
                if check.returncode or check.stdout.strip() != version:
                    raise RuntimeError('새 yt-dlp 실행 검증에 실패했습니다.')
                os.replace(staged, target)
                staged = None
            stamp.touch()
            log(f'yt-dlp {version} 준비 완료')
        except Exception as exc:
            if not target.exists():
                raise RuntimeError(f'yt-dlp 최초 설치 실패. 인터넷 연결을 확인 후 다시 시도하세요: {exc}') from exc
            log(f'업데이트 확인 실패 — 기존 yt-dlp로 계속합니다: {exc}')
        finally:
            if staged and os.path.exists(staged):
                os.unlink(staged)
        _CHECKED = True
        return str(target)

def _runtime_args(log):
    # Finder-launched macOS applications do not inherit Homebrew's PATH.
    for name in ('deno', 'node'):
        candidates = [shutil.which(name), str(Path.home() / '.deno/bin' / name),
                      '/opt/homebrew/bin/' + name, '/usr/local/bin/' + name]
        for candidate in candidates:
            if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return ['--js-runtimes', f'{name}:{candidate}']
    log('경고: Deno/Node를 찾지 못했습니다. YouTube 다운로드에는 JavaScript 실행 환경이 필요할 수 있습니다.')
    return []

class YoutubeDL:
    """Small adapter for the options used by app.py; no bundled yt_dlp imports."""
    def __init__(self, options=None, log=None):
        self.options = options or {}
        self.log = log or (lambda text: None)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _args(self):
        o = self.options
        args = [ensure_engine(self.log), '--ignore-config', '--no-color',
                '--socket-timeout', '30', '--retries', '3', '--fragment-retries', '3']
        args += _runtime_args(self.log)
        args += ['--no-playlist' if o.get('noplaylist', True) else '--yes-playlist']
        for key, flag in [('format', '-f'), ('outtmpl', '-o'), ('ffmpeg_location', '--ffmpeg-location'),
                          ('merge_output_format', '--merge-output-format'), ('remux_video', '--remux-video')]:
            if o.get(key):
                args += [flag, str(o[key])]
        for key, flag in [('skip_download', '--skip-download'), ('writethumbnail', '--write-thumbnail'),
                          ('writesubtitles', '--write-subs'), ('writeautomaticsub', '--write-auto-subs')]:
            if o.get(key):
                args.append(flag)
        if o.get('subtitleslangs'):
            args += ['--sub-langs', ','.join(o['subtitleslangs'])]
        for pp in o.get('postprocessors', []):
            if pp['key'] == 'FFmpegExtractAudio':
                args += ['-x', '--audio-format', pp.get('preferredcodec', 'mp3'),
                         '--audio-quality', pp.get('preferredquality', '192') + 'K']
            elif pp['key'] == 'EmbedThumbnail':
                args.append('--embed-thumbnail')
            else:
                raise ValueError(f"지원하지 않는 후처리: {pp['key']}")
        return args

    def extract_info(self, url, download=False):
        if download:
            raise ValueError('다운로드는 download()를 사용하세요.')
        result = _run(self._args() + ['--dump-single-json', '--skip-download', '--', url], timeout=180)
        for line in result.stderr.splitlines():
            self.log(line)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or '영상 정보 조회 실패')
        return json.loads(result.stdout)

    def download(self, urls):
        args = self._args() + ['--newline', '--progress', '--progress-delta', '0.5',
                              '--progress-template', 'download:YGT_PROGRESS:%(progress)j', '--'] + list(urls)
        tail = deque(maxlen=25)
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding='utf-8', errors='replace', bufsize=1,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
            for line in process.stdout:
                line = line.rstrip()
                if line.startswith('YGT_PROGRESS:'):
                    try:
                        progress = json.loads(line.split(':', 1)[1])
                    except ValueError:
                        self.log(line)
                    else:
                        for hook in self.options.get('progress_hooks', []):
                            hook(progress)
                elif line:
                    tail.append(line)
                    self.log(line)
            code = process.wait()
        if code:
            detail = '\n'.join(tail)
            if '403' in detail:
                detail += '\n403: 최신 엔진에서도 서버가 다운로드를 거부했습니다. 경고 로그를 확인하세요. IP/인증/영상별 제한 등은 엔진 업데이트만으로 해결되지 않을 수 있습니다.'
            raise RuntimeError(detail or f'yt-dlp 종료 코드: {code}')
        return 0
