"""Explicit codec selection. Never silently fall back to a different video codec."""
import re

CODECS = ('자동 선택', 'H.264 · 호환성 우선', 'AV1 · 고효율', 'VP9 · WebM')
PATTERNS = {'h264': '^(avc1|h264)', 'av1': '^(av01|av1)', 'vp9': '^(vp09|vp9)'}

def codec_key(label):
    for prefix, key in (('H.264', 'h264'), ('AV1', 'av1'), ('VP9', 'vp9')):
        if label.startswith(prefix):
            return key
    return 'auto'

def codec_family(value):
    return next((key for key, pattern in PATTERNS.items() if re.match(pattern, value or '')), 'auto')

def selection(quality, codec):
    """Return yt-dlp selector and the expected output container."""
    if quality.startswith('오디오만'):
        return 'bestaudio/best', 'mp3'
    match = re.search(r'(\d+)p', quality)
    height = f'[height<={match.group(1)}]' if match else ''
    key = codec_key(codec)
    if key == 'auto':
        return (f'bestvideo{height}[ext=mp4]+bestaudio[ext=m4a]/best{height}[ext=mp4]/'
                f'bestvideo{height}+bestaudio/best{height}', 'mp4')
    video = height + "[vcodec~='" + PATTERNS[key] + "']"
    if key == 'vp9':
        return (f'bestvideo{video}[ext=webm]+bestaudio[ext=webm]/best{video}[ext=webm]', 'webm')
    # Restrict every fallback branch to the requested codec and an MP4-compatible audio stream.
    return (f'bestvideo{video}[ext=mp4]+bestaudio[ext=m4a]/best{video}[ext=mp4]', 'mp4')
