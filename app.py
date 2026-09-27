"""
YGT (You've Got Tube) - yt-dlp 기반 간단 GUI 다운로더
Python이나 명령줄 없이, 창을 열어 URL만 붙여넣으면 다운로드됩니다.

흐름:
  - 정밀 선택: URL 1개 입력 -> "정보 가져오기" -> 추천 조합(영상+음성 자동 매칭, 고화질 순)에서
    한 항목 선택 후 다운로드. 필요하면 "전체 포맷" 표에서 직접 2개(영상+음성) 조합도 가능.
  - 일괄 다운로드: URL 여러 줄(줄바꿈으로 구분) 입력 -> 화질 프리셋으로 순차 다운로드
"""

import os
import sys
import shutil
import threading
import queue
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import ygt_engine as yt_dlp
from ygt_ui import DesktopUI
from ygt_formats import selection as codec_selection


def resource_path(relative_path: str) -> str:
    """PyInstaller로 패키징된 exe 안에 포함된 리소스(ffmpeg 등) 경로를 찾는다."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


APP_TITLE = "YGT"
APP_SUBTITLE = "You've Got Tube — 간편 유튜브 다운로더"

# 브랜드 컬러
COLOR_PRIMARY = "#2F6FED"
COLOR_PRIMARY_DARK = "#1F4FBF"
COLOR_BG = "#141820"
COLOR_TEXT_MUTED = "#6B7280"


def _default_font_family():
    """OS별로 적절한 폰트를 고른다.
    앱 텍스트 대부분이 한글이라 Arial 하나만 쓰면 한글이 깨져 보이므로,
    Windows에서는 '맑은 고딕'(Apple 고딕과 비슷한 느낌의 산세리프),
    macOS에서는 실제 'Apple SD Gothic Neo'를 쓰고, 그 외에는 Arial로 대체한다."""
    if sys.platform.startswith("win"):
        return "Malgun Gothic"
    elif sys.platform == "darwin":
        return "Apple SD Gothic Neo"
    return "Arial"


FONT_FAMILY = _default_font_family()

RAW_COLUMNS = ("format_id", "type", "resolution", "fps", "vcodec", "acodec", "ext", "size", "note")
RAW_COLUMN_LABELS = {
    "format_id": "ID",
    "type": "종류",
    "resolution": "해상도",
    "fps": "FPS",
    "vcodec": "영상 코덱",
    "acodec": "오디오 코덱",
    "ext": "확장자",
    "size": "용량",
    "note": "비고",
}
RAW_COLUMN_WIDTHS = {
    "format_id": 55,
    "type": 65,
    "resolution": 85,
    "fps": 45,
    "vcodec": 100,
    "acodec": 100,
    "ext": 50,
    "size": 75,
    "note": 110,
}

COMBO_COLUMNS = ("resolution", "fps", "vcodec", "acodec", "ext", "size", "note")
COMBO_COLUMN_LABELS = {
    "resolution": "해상도",
    "fps": "FPS",
    "vcodec": "영상 코덱",
    "acodec": "오디오 코덱",
    "ext": "확장자",
    "size": "예상 용량",
    "note": "비고",
}
COMBO_COLUMN_WIDTHS = {
    "resolution": 100,
    "fps": 50,
    "vcodec": 110,
    "acodec": 110,
    "ext": 60,
    "size": 90,
    "note": 160,
}

EDITOR_FRIENDLY_VCODEC_PREFIXES = ("avc1", "h264")


def human_size(num_bytes):
    if not num_bytes:
        return "-"
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


def is_editor_friendly(vcodec: str) -> bool:
    if not vcodec:
        return False
    return vcodec.lower().startswith(EDITOR_FRIENDLY_VCODEC_PREFIXES)


def format_row(f):
    vcodec = f.get("vcodec") or "-"
    acodec = f.get("acodec") or "-"
    has_video = vcodec not in (None, "none")
    has_audio = acodec not in (None, "none")

    if has_video and has_audio:
        ftype = "영상+음성"
    elif has_video:
        ftype = "영상만"
    elif has_audio:
        ftype = "음성만"
    else:
        ftype = "기타"

    resolution = f.get("resolution")
    if not resolution:
        if f.get("height"):
            resolution = f"{f.get('width', '?')}x{f.get('height')}"
        elif has_audio and not has_video:
            resolution = "오디오"
        else:
            resolution = "-"

    fps = f.get("fps")
    fps_str = str(int(fps)) if fps else "-"

    size = f.get("filesize") or f.get("filesize_approx")
    size_str = human_size(size)

    note = f.get("format_note") or ""

    return {
        "format_id": f.get("format_id", "-"),
        "type": ftype,
        "resolution": resolution,
        "fps": fps_str,
        "vcodec": vcodec,
        "acodec": acodec,
        "ext": f.get("ext", "-"),
        "size": size_str,
        "note": note,
        "_height": f.get("height") or 0,
    }


def build_combo_rows(formats):
    """video-only + 최고음질 audio-only 를 자동으로 짝지어 '추천 조합' 목록을 만든다.
    이미 영상+음성이 합쳐진 muxed 포맷도 단일 옵션으로 포함한다.
    고화질(해상도 높은 순)이 위로 오도록 정렬한다."""
    video_onlys = []
    audio_onlys = []
    muxed = []

    for f in formats:
        if f.get("format_id") is None:
            continue
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        has_video = vcodec != "none"
        has_audio = acodec != "none"
        if has_video and has_audio:
            muxed.append(f)
        elif has_video:
            video_onlys.append(f)
        elif has_audio:
            audio_onlys.append(f)

    if not audio_onlys:
        best_audio = None
    else:
        def audio_score(f):
            return f.get("abr") or f.get("tbr") or 0
        best_audio = max(audio_onlys, key=audio_score)

    combos = []

    # video-only + best audio 자동 조합 (해상도별 가장 좋은 것 하나씩)
    best_by_height = {}
    for f in video_onlys:
        h = f.get("height") or 0
        score = f.get("tbr") or 0
        if h not in best_by_height or score > (best_by_height[h].get("tbr") or 0):
            best_by_height[h] = f

    for h, vf in best_by_height.items():
        if best_audio is None:
            continue
        v_row = format_row(vf)
        a_row = format_row(best_audio)
        v_size = vf.get("filesize") or vf.get("filesize_approx") or 0
        a_size = best_audio.get("filesize") or best_audio.get("filesize_approx") or 0
        total_size = (v_size or 0) + (a_size or 0)
        note = "영상+음성 자동 조합"
        if is_editor_friendly(vf.get("vcodec")):
            note += " · 편집 프로그램 호환 좋음"
        combos.append(
            {
                "format_ids": f"{vf.get('format_id')}+{best_audio.get('format_id')}",
                "resolution": v_row["resolution"],
                "fps": v_row["fps"],
                "vcodec": v_row["vcodec"],
                "acodec": a_row["acodec"],
                "ext": "mp4",
                "size": human_size(total_size) if total_size else "-",
                "note": note,
                "_height": h,
                "_is_muxed": False,
            }
        )

    # 이미 영상+음성이 합쳐진 단일 파일 옵션
    for mf in muxed:
        row = format_row(mf)
        note = "단일 파일"
        if is_editor_friendly(mf.get("vcodec")):
            note += " · 편집 프로그램 호환 좋음"
        combos.append(
            {
                "format_ids": mf.get("format_id"),
                "resolution": row["resolution"],
                "fps": row["fps"],
                "vcodec": row["vcodec"],
                "acodec": row["acodec"],
                "ext": row["ext"],
                "size": row["size"],
                "note": note,
                "_height": row["_height"],
                "_is_muxed": True,
            }
        )

    combos.sort(key=lambda r: r["_height"], reverse=True)
    return combos


class DownloaderApp(DesktopUI, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} — You've Got Tube")
        self.geometry(f"960x{min(820, self.winfo_screenheight() - 100)}")
        self.minsize(800, 560)
        self.configure(background=COLOR_BG)

        self._logo_image = None  # 참조 유지 (가비지 컬렉션 방지)
        self._last_editable_widget = None
        self._apply_theme()
        self._set_window_icon()
        self._build_menu()

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.progress_queue: "queue.Queue[dict]" = queue.Queue()
        self.download_dir = str(Path.home() / "Downloads")
        self.is_busy = False
        self.current_formats = {}  # format_id -> raw format dict
        self.combo_map = {}  # combo iid -> format_ids string
        self.video_title = None
        self.fetched_url = None  # 표가 어떤 URL 기준인지 기억
        self._preview_urls = []  # 제목 미리보기 표의 각 줄이 어떤 URL인지 기억
        self._title_cache = {}  # url -> title (같은 이름 파일 중복 방지에 사용)
        self.adv_visible = False

        self._build_ui()
        self._poll_log_queue()
        self._poll_progress_queue()

    # ---------- 메뉴바 (macOS에서 Cmd 단축키가 실제로 동작하려면 필요) ----------
    def _build_menu(self):
        menubar = tk.Menu(self)

        # PyInstaller로 패키징한 macOS 앱에서는 Cmd+키를 누르는 순간 OS가 이 메뉴의
        # accelerator와 먼저 매칭시키는데, 그 처리 과정에서 self.focus_get()이 None을
        # 반환해 버리는 경우가 있다(터미널에서 바로 실행할 때는 재현되지 않음).
        # 그래서 <FocusIn>으로 마지막으로 포커스를 받았던 입력 위젯을 직접 기억해뒀다가
        # focus_get()이 실패할 때 그걸 대신 사용한다.
        def _track_focus(event):
            widget = event.widget
            if isinstance(widget, (tk.Text, tk.Entry, ttk.Entry)) and str(widget.cget("state")) != "disabled":
                self._last_editable_widget = widget

        self.bind_all("<FocusIn>", _track_focus, add="+")

        def _do(virtual_event):
            widget = self.focus_get() or self._last_editable_widget
            if widget is not None:
                widget.event_generate(virtual_event)
            return "break"

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="잘라내기", accelerator="Cmd+X", command=lambda: _do("<<Cut>>"))
        edit_menu.add_command(label="복사", accelerator="Cmd+C", command=lambda: _do("<<Copy>>"))
        edit_menu.add_command(label="붙여넣기", accelerator="Cmd+V", command=lambda: _do("<<Paste>>"))
        edit_menu.add_separator()
        edit_menu.add_command(label="전체 선택", accelerator="Cmd+A", command=lambda: _do("<<SelectAll>>"))
        menubar.add_cascade(label="편집", menu=edit_menu)

        self.config(menu=menubar)

        # Tk에는 <<SelectAll>> 가상 이벤트에 대한 기본 동작이 없으므로 직접 구현
        def select_all(event=None):
            widget = self.focus_get() or self._last_editable_widget
            if isinstance(widget, tk.Text):
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "end-1c")
                widget.see("insert")
            elif isinstance(widget, (tk.Entry, ttk.Entry)):
                widget.selection_range(0, "end")
            return "break"

        self.bind_all("<<SelectAll>>", select_all)
        # 메뉴 accelerator 등록만으로 실제 키 입력이 전달 안 되는 Tk 빌드를 위한 보조 바인딩
        self.bind_all("<Command-a>", lambda e: self.event_generate("<<SelectAll>>"))
        self.bind_all("<Control-a>", lambda e: self.event_generate("<<SelectAll>>"))

    # ---------- IME 상태와 무관하게 항상 동작하는 붙여넣기/전체선택/지우기 ----------
    def _paste_into(self, widget):
        try:
            clip = widget.clipboard_get()
        except tk.TclError:
            messagebox.showinfo(APP_TITLE, "클립보드에 붙여넣을 내용이 없습니다.")
            return
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        widget.insert("insert", clip)
        widget.focus_set()
        self._update_mode_banner()

    def _select_all_in(self, widget):
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set("insert", "end-1c")
        widget.focus_set()

    def _clear_text(self, widget):
        widget.delete("1.0", "end")
        widget.focus_set()
        self._update_mode_banner()

    # ---------- 텍스트 위젯 편집 단축키 / 우클릭 메뉴 ----------
    def _enable_text_editing_shortcuts(self, widget):
        """복사/붙여넣기/잘라내기/전체선택 단축키와 우클릭 컨텍스트 메뉴를 붙여준다.
        macOS에서 PyInstaller로 패키징한 tkinter 앱은 기본 Aqua 바인딩이
        먹지 않는 경우가 있어, Cmd/Ctrl 단축키를 직접 처리한다."""

        def copy(event=None):
            try:
                text = widget.get("sel.first", "sel.last")
            except tk.TclError:
                text = widget.get("1.0", "end-1c")
            widget.clipboard_clear()
            widget.clipboard_append(text)
            return "break"

        def cut(event=None):
            copy()
            try:
                widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            return "break"

        def paste(event=None):
            if str(widget.cget("state")) != "disabled":
                self._paste_into(widget)
            return "break"

        def select_all(event=None):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "end-1c")
            widget.see("insert")
            return "break"

        # macOS(Command)와 Windows/Linux(Control) 둘 다 지원
        for mod in ("Command", "Control"):
            widget.bind(f"<{mod}-c>", copy)
            widget.bind(f"<{mod}-x>", cut)
            widget.bind(f"<{mod}-v>", paste)
            widget.bind(f"<{mod}-V>", paste)
            widget.bind(f"<{mod}-a>", select_all)

        widget.bind("<<Paste>>", paste)

        # 한글(2벌식) 등 비영문 입력 소스가 활성화된 상태에서는 macOS가 Command+글자
        # 키의 keysym을 영문 그대로 넘겨주지 않아서 위의 <Command-v> 류 바인딩이
        # 매칭되지 않는다(그래서 영문 입력일 땐 되다가 한글 입력일 땐 안 됨).
        # keycode(물리적 키 위치, 입력 소스와 무관)로 한 번 더 잡아서 그 경우를 보완한다.
        _MAC_KEYCODES = {9: "v", 8: "c", 7: "x", 0: "a"}

        def on_command_key(event):
            letter = _MAC_KEYCODES.get(event.keycode)
            if letter == "v":
                return paste(event)
            if letter == "c":
                return copy(event)
            if letter == "x":
                return cut(event)
            if letter == "a":
                return select_all(event)
            return None

        widget.bind("<Command-Key>", on_command_key, add="+")

        # 우클릭 컨텍스트 메뉴 (macOS는 우클릭이 Button-2로 오는 경우도 있어 둘 다 등록)
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="잘라내기", command=cut)
        menu.add_command(label="복사", command=copy)
        menu.add_command(label="붙여넣기", command=paste)
        menu.add_separator()
        menu.add_command(label="전체 선택", command=select_all)

        def show_context_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        widget.bind("<Button-3>", show_context_menu)
        widget.bind("<Button-2>", show_context_menu)
        widget.bind("<Control-Button-1>", show_context_menu)  # macOS 트랙패드 관습적 우클릭

    # ---------- 테마 / 아이콘 ----------
    def _set_window_icon(self):
        """ygt_logo.png (없으면 ygt_icon.png)를 창/작업표시줄 아이콘으로 사용. 없으면 조용히 건너뜀."""
        for name in ("ygt_icon.png", "ygt_logo.png"):
            path = resource_path(name)
            if os.path.exists(path):
                try:
                    self._logo_image = tk.PhotoImage(file=path)
                    self.iconphoto(True, self._logo_image)
                    return
                except tk.TclError:
                    continue

    def _load_header_logo(self, max_size=56):
        """헤더에 표시할 축소된 로고 PhotoImage를 반환 (없으면 None)."""
        for name in ("ygt_logo.png", "ygt_icon.png"):
            path = resource_path(name)
            if os.path.exists(path):
                try:
                    img = tk.PhotoImage(file=path)
                    factor = max(1, img.width() // max_size)
                    if factor > 1:
                        img = img.subsample(factor, factor)
                    return img
                except tk.TclError:
                    continue
        return None

    # ---------- UI ----------
    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_dir)
        if folder:
            self.download_dir = folder
            self.folder_label.config(text=self._display_folder(folder))
            self._save_preferences()

    # ---------- 단일/일괄 모드 전환 ----------
    def _on_preview_double_click(self, event):
        if self.is_busy or self.engine_busy:
            return
        row_id = self.preview_tree.identify_row(event.y)
        if not row_id:
            return
        try:
            idx = int(row_id.split("_")[1])
        except (IndexError, ValueError):
            return
        if idx - 1 >= len(self._preview_urls):
            return
        url = self._preview_urls[idx - 1]
        self._log(f"제목 더블클릭 → 이 영상만 바로 다운로드 시작: {url}")
        self._begin_batch_download([url])

    def _download_selected_previews(self):
        if self.is_busy or self.engine_busy:
            return
        selection = self.preview_tree.selection()
        if not selection:
            messagebox.showwarning(
                APP_TITLE, "표에서 다운로드할 항목을 먼저 선택해주세요 (Ctrl+클릭 또는 Shift+클릭으로 여러 개 선택 가능)."
            )
            return

        urls = []
        for iid in selection:
            try:
                idx = int(iid.split("_")[1])
            except (IndexError, ValueError):
                continue
            if idx - 1 < len(self._preview_urls):
                urls.append(self._preview_urls[idx - 1])

        if not urls:
            return

        self._log(f"선택한 {len(urls)}개 항목 다운로드 시작")
        self._begin_batch_download(urls)

    def _get_urls(self):
        raw = self.url_text.get("1.0", "end")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    # ---------- 로그 / 진행률 ----------
    def _log(self, message: str):
        self.log_queue.put(message)

    def _poll_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                at_end = self.log_text.yview()[1] >= 0.999
                self.log_text.config(state="normal")
                self.log_text.insert("end", message + "\n")
                if at_end:
                    self.log_text.see("end")
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self._poll_log_queue)

    def _set_progress(self, percent=None, text=None):
        self.progress_queue.put({"percent": percent, "text": text})

    def _poll_progress_queue(self):
        try:
            latest = None
            while True:
                latest = self.progress_queue.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            if latest.get("percent") is not None:
                self.progress["value"] = latest["percent"]
            if latest.get("text") is not None:
                self.progress_label.config(text=latest["text"])
        self.after(150, self._poll_progress_queue)

    # ---------- 정보 가져오기 (정밀 선택용, URL 1개만) ----------
    def _start_fetch_info(self):
        if self.is_busy or self.engine_busy:
            return

        urls = self._get_urls()
        if not urls:
            messagebox.showwarning(APP_TITLE, "URL을 입력해주세요.")
            return
        if len(urls) > 1:
            messagebox.showinfo(
                APP_TITLE,
                "URL이 여러 개 입력되어 있어 첫 번째 URL의 정보만 가져옵니다.\n"
                "여러 개를 그대로 다운로드하려면 정보 가져오기 없이 '다운로드 시작'만 누르면 됩니다.",
            )
        url = urls[0]

        self.is_busy = True
        self._refresh_controls()
        self.fetch_btn.config(state="disabled")
        self._set_progress(percent=0, text="정보 가져오는 중...")
        self.combo_tree.delete(*self.combo_tree.get_children())
        self.tree.delete(*self.tree.get_children())
        self.combo_map = {}
        self.title_label.config(text="")
        self._log(f"정보 가져오는 중: {url}")

        thread = threading.Thread(target=self._run_fetch_info, args=(url,), daemon=True)
        thread.start()

    def _run_fetch_info(self, url: str):
        ydl_opts = {
            "noplaylist": True,  # 정보 조회는 대표 영상 1개 기준
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts, log=self._log) as ydl:
                info = ydl.extract_info(url, download=False)

            formats = info.get("formats") or []

            raw_rows = []
            self.current_formats = {}
            for f in formats:
                if f.get("format_id") is None:
                    continue
                self.current_formats[f["format_id"]] = f
                raw_rows.append(format_row(f))
            raw_rows.sort(key=lambda r: r["_height"], reverse=True)

            combo_rows = build_combo_rows(formats)

            self.video_title = info.get("title")
            if self.video_title:
                self._title_cache[url] = self.video_title
            self.after(0, lambda: self._populate_trees(raw_rows, combo_rows, url))
            self._log(f"정보 가져오기 완료: {self.video_title} (추천 조합 {len(combo_rows)}개, 전체 포맷 {len(raw_rows)}개)")
        except Exception as exc:
            self._set_progress(percent=0, text="정보 조회 실패 · 작업 기록에서 원인을 확인하세요")
            self._log("정보 가져오기 실패: " + str(exc))
            self._log(traceback.format_exc())
        finally:
            self.after(0, self._fetch_finished)

    def _populate_trees(self, raw_rows, combo_rows, url):
        for row in raw_rows:
            values = tuple(row[c] for c in RAW_COLUMNS)
            self.tree.insert("", "end", iid=row["format_id"], values=values)

        self.combo_map = {}
        for idx, row in enumerate(combo_rows):
            iid = f"combo_{idx}"
            self.combo_map[iid] = row["format_ids"]
            values = tuple(row[c] for c in COMBO_COLUMNS)
            self.combo_tree.insert("", "end", iid=iid, values=values)

        title_text = f"제목: {self.video_title}" if self.video_title else ""
        self.title_label.config(text=title_text)
        self.fetched_url = url
        self._set_progress(percent=0, text="영상 정보를 불러왔어요 · 포맷을 선택하세요")

    def _fetch_finished(self):
        self.is_busy = False
        self._update_mode_banner()


    # ---------- 제목 미리보기 (URL 여러 개 확인용) ----------
    def _start_preview_titles(self):
        if self.is_busy or self.engine_busy:
            return

        urls = self._get_urls()
        if not urls:
            messagebox.showwarning(APP_TITLE, "URL을 입력해주세요.")
            return

        self.is_busy = True
        self._refresh_controls()
        self.fetch_btn.config(state="disabled")
        self.preview_btn.config(state="disabled")
        self.download_btn.config(state="disabled")
        self.download_selected_btn.config(state="disabled")
        self._set_progress(percent=0, text="제목 확인 중...")
        self._log(f"===== 제목 미리보기 시작 (총 {len(urls)}개) =====")

        self._preview_urls = list(urls)
        self.preview_tree.delete(*self.preview_tree.get_children())
        for idx, url in enumerate(urls, start=1):
            self.preview_tree.insert(
                "", "end", iid=f"prev_{idx}", values=(idx, "대기", "-", self._short_url(url))
            )

        thread = threading.Thread(target=self._run_preview_titles, args=(urls,), daemon=True)
        thread.start()

    @staticmethod
    def _short_url(url, max_len=60):
        return url if len(url) <= max_len else url[: max_len - 3] + "..."

    def _update_preview_row(self, idx, status, title, url):
        iid = f"prev_{idx}"
        if self.preview_tree.exists(iid):
            self.preview_tree.item(iid, values=(idx, status, title, self._short_url(url)))

    def _run_preview_titles(self, urls):
        total = len(urls)
        ok_count = 0
        ydl_opts = {
            "noplaylist": True,
            "skip_download": True,
        }
        for idx, url in enumerate(urls, start=1):
            self._set_progress(percent=int((idx - 1) / total * 100), text=f"[{idx}/{total}] 제목 확인 중...")
            self.after(0, lambda i=idx, u=url: self._update_preview_row(i, "확인중", "확인 중...", u))
            try:
                with yt_dlp.YoutubeDL(ydl_opts, log=self._log) as ydl:
                    info = ydl.extract_info(url, download=False)
                title = info.get("title", "(제목 없음)")
                if title:
                    self._title_cache[url] = title
                duration = info.get("duration")
                duration_str = ""
                if duration:
                    m, s = divmod(int(duration), 60)
                    h, m = divmod(m, 60)
                    duration_str = f" ({h:02d}:{m:02d}:{s:02d})" if h else f" ({m:02d}:{s:02d})"
                full_title = f"{title}{duration_str}"
                self.after(0, lambda i=idx, u=url, t=full_title: self._update_preview_row(i, "✅ 확인됨", t, u))
                self._log(f"[{idx}/{total}] ✅ {full_title}")
                ok_count += 1
            except Exception as exc:
                self.after(
                    0, lambda i=idx, u=url: self._update_preview_row(i, "❌ 실패", "확인 실패 (링크 확인 필요)", u)
                )
                self._log(f"[{idx}/{total}] ❌ 정보 확인 실패: {url}\n        사유: {exc}")

        self._log(f"===== 미리보기 완료: {ok_count}/{total}개 확인됨 =====")
        self._set_progress(percent=100, text=f"제목 확인 {ok_count}개 / 실패 {total - ok_count}개")
        self.after(0, self._preview_finished)

    def _preview_finished(self):
        self.is_busy = False
        self.preview_btn.config(state="normal")
        self.download_btn.config(state="normal")
        self.download_selected_btn.config(state="normal")
        self._update_mode_banner()

    def _on_combo_double_click(self, _event):
        if self.is_busy or self.engine_busy:
            return
        selection = self.combo_tree.selection()
        if not selection:
            return
        urls = self._get_urls()
        if len(urls) != 1 or self.fetched_url != urls[0]:
            messagebox.showwarning(
                APP_TITLE, "추천 조합은 방금 정보를 가져온 URL 1개에 대해서만 바로 다운로드할 수 있습니다."
            )
            return
        self._begin_precise_download(urls[0], selection[0], is_combo=True)

    # ---------- 다운로드 ----------
    def _start_download(self):
        if self.is_busy or self.engine_busy:
            return

        urls = self._get_urls()
        if not urls:
            messagebox.showwarning(APP_TITLE, "URL을 입력해주세요.")
            return

        in_details = self.notebook.select() == str(self.detail_page)
        combo_selection = self.combo_tree.selection() if in_details else ()
        raw_selection = self.tree.selection() if in_details and self.adv_visible else ()
        if in_details and (self.fetched_url != urls[0] or not (combo_selection or raw_selection)):
            messagebox.showinfo(APP_TITLE, "영상 정보를 불러온 뒤 포맷을 선택하세요.\n간편하게 받으려면 다운로드 탭을 사용하세요.")
            return

        use_combo = len(urls) == 1 and bool(combo_selection) and self.fetched_url == urls[0]
        use_raw = (
            not use_combo and len(urls) == 1 and bool(raw_selection) and self.fetched_url == urls[0]
        )

        if use_raw and len(raw_selection) > 2:
            messagebox.showwarning(
                APP_TITLE, "전체 포맷 목록에서는 최대 2개(영상 1개 + 음성 1개)까지만 함께 선택할 수 있습니다."
            )
            return

        if use_combo:
            self._begin_precise_download(urls[0], combo_selection[0], is_combo=True)
        elif use_raw:
            self._begin_precise_download(urls[0], list(raw_selection), is_combo=False)
        else:
            self._begin_batch_download(urls)

    def _begin_precise_download(self, url, selection, is_combo):
        self.is_busy = True
        self._refresh_controls()
        self.download_btn.config(state="disabled")
        self.thumb_only_btn.config(state="disabled")
        self.download_selected_btn.config(state="disabled")
        self.fetch_btn.config(state="disabled")
        self._set_progress(percent=0, text="다운로드 준비 중...")

        self._capture_job_options()
        if is_combo:
            format_ids = self.combo_map.get(selection, selection).split("+")
            thread = threading.Thread(
                target=self._run_precise_download, args=(url, format_ids, False), daemon=True
            )
        else:
            thread = threading.Thread(
                target=self._run_precise_download, args=(url, list(selection)), daemon=True
            )
        thread.start()

    def _begin_batch_download(self, urls):
        self.is_busy = True
        self._refresh_controls()
        self.download_btn.config(state="disabled")
        self.thumb_only_btn.config(state="disabled")
        self.download_selected_btn.config(state="disabled")
        self.fetch_btn.config(state="disabled")
        self._set_progress(percent=0, text="다운로드 준비 중...")
        self._capture_job_options()
        thread = threading.Thread(target=self._run_batch_download, args=(urls,), daemon=True)
        thread.start()

    def _capture_job_options(self):
        self._job_options = {
            name: getattr(self, name + "_var").get()
            for name in ("embed_thumb", "save_thumb", "mp3", "playlist", "subtitle", "preset", "codec")
        }

    def _build_format_selector(self, format_ids):
        """선택된 format_id 1~2개로 -f 문자열을 구성한다."""
        if len(format_ids) == 1:
            fmt_id = format_ids[0]
            info = self.current_formats.get(fmt_id, {})
            vcodec = info.get("vcodec") or "none"
            acodec = info.get("acodec") or "none"
            has_video = vcodec != "none"
            has_audio = acodec != "none"
            if has_video and not has_audio:
                return f"{fmt_id}+bestaudio", has_video, True
            return fmt_id, has_video, has_audio
        else:
            # 2개 선택(또는 미리 만든 조합): '+'로 합쳐서 영상+음성 병합
            return "+".join(format_ids), True, True

    def _apply_thumbnail_opts(self, ydl_opts):
        """썸네일 저장/삽입 옵션을 ydl_opts에 반영한다."""
        embed = self._job_options["embed_thumb"]
        save = self._job_options["save_thumb"]
        if not (embed or save):
            return
        ydl_opts["writethumbnail"] = True
        if embed:
            postprocessors = ydl_opts.setdefault("postprocessors", [])
            postprocessors.append({"key": "EmbedThumbnail"})

    def _run_precise_download(self, url: str, format_ids, adaptive=False):
        format_selector, has_video, has_audio = self._build_format_selector(format_ids)
        want_mp3 = self._job_options["mp3"]

        self._log(f"다운로드 시작 ({format_ids}): {url}")

        if want_mp3:
            expected_ext = "mp3"
        elif has_video:
            expected_ext = "mkv"
        else:
            fmt_info = self.current_formats.get(format_ids[0], {}) if format_ids else {}
            expected_ext = fmt_info.get("ext") or "m4a"

        is_playlist = self._job_options["playlist"]
        if not is_playlist and self.video_title:
            # 같은 이름의 파일이 이미 있으면 '(1)' 식으로 번호를 붙여 겹치지 않게 저장
            outtmpl = self._unique_output_path(self.video_title, expected_ext)
        else:
            outtmpl = os.path.join(self.download_dir, "%(title)s.%(ext)s")

        ydl_opts = {
            "format": format_selector,
            "outtmpl": outtmpl,
            "noplaylist": not self._job_options["playlist"],
            "progress_hooks": [self._progress_hook],
            "ffmpeg_location": self._ffmpeg_location(),
        }

        if want_mp3:
            ydl_opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        elif has_video:
            ydl_opts["merge_output_format"] = "mkv"
            ydl_opts["remux_video"] = "mkv"

        if self._job_options["subtitle"]:
            ydl_opts.update(
                {"writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": ["ko", "en"]}
            )

        self._apply_thumbnail_opts(ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts, log=self._log) as ydl:
                ydl.download([url])
            self._log("완료! 저장 위치: " + self.download_dir)
            self._set_progress(percent=100, text="완료")
        except Exception as exc:
            self._log("오류 발생: " + str(exc))
            self._log(traceback.format_exc())
            self._set_progress(percent=0, text="다운로드 실패 · 작업 기록에서 원인을 확인하세요")
        finally:
            self.after(0, self._download_finished)

    def _run_batch_download(self, urls):
        preset_label = self._job_options["preset"]
        format_selector, output_container = codec_selection(preset_label, self._job_options["codec"])
        is_audio_only = preset_label.startswith("오디오만")
        expected_ext = output_container
        is_playlist = self._job_options["playlist"]

        total = len(urls)
        failed = 0
        for idx, url in enumerate(urls, start=1):
            self._log(f"[{idx}/{total}] 다운로드 시작 · {preset_label} · {self._job_options['codec']}: {url}")
            self._set_progress(percent=0, text=f"[{idx}/{total}] 준비 중...")

            if not is_playlist:
                title = self._known_title_for(url)
                outtmpl = (
                    self._unique_output_path(title, expected_ext)
                    if title
                    else os.path.join(self.download_dir, "%(title)s.%(ext)s")
                )
            else:
                outtmpl = os.path.join(self.download_dir, "%(title)s.%(ext)s")

            ydl_opts = {
                "format": format_selector,
                "outtmpl": outtmpl,
                "noplaylist": not self._job_options["playlist"],
                "progress_hooks": [lambda d, i=idx, t=total: self._progress_hook(d, prefix=f"[{i}/{t}] ")],
                "ffmpeg_location": self._ffmpeg_location(),
            }

            if is_audio_only:
                ydl_opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ]
            else:
                ydl_opts["merge_output_format"] = output_container
                ydl_opts["remux_video"] = output_container

            if self._job_options["subtitle"]:
                ydl_opts.update(
                    {"writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": ["ko", "en"]}
                )

            self._apply_thumbnail_opts(ydl_opts)

            try:
                with yt_dlp.YoutubeDL(ydl_opts, log=self._log) as ydl:
                    ydl.download([url])
                self._log(f"[{idx}/{total}] 완료: {url}")
            except Exception as exc:
                failed += 1
                if "Requested format is not available" in str(exc):
                    self._log("선택한 화질·코덱 조합을 제공하지 않는 영상입니다. 다른 코덱을 선택하거나 포맷 직접 선택 탭에서 확인하세요.")
                self._log(f"[{idx}/{total}] 오류 발생 ({url}): {exc}")

        self._log(f"일괄 다운로드 종료. 저장 위치: {self.download_dir}")
        self._set_progress(percent=100 if not failed else 0, text=f"완료 {total - failed}개 / 실패 {failed}개")
        self.after(0, self._download_finished)

    def _ffmpeg_location(self):
        ffmpeg_name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
        bundled = resource_path(ffmpeg_name)
        if os.path.exists(bundled):
            return bundled
        for path in (shutil.which(ffmpeg_name), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None

    def _sanitize_title(self, title: str) -> str:
        # Literal titles must escape '%' before passing through yt-dlp templates.
        return "".join(c for c in title if c not in '\\/:*?"<>|' and ord(c) >= 32).strip().strip('.') or "video"

    def _unique_output_path(self, title: str, ext: str) -> str:
        """저장 위치에 같은 이름의 파일이 이미 있으면 '제목 (1).ext' 식으로 번호를 붙여
        겹치지 않는 경로를 만들어 반환한다. (브라우저 다운로드와 동일한 방식)"""
        safe_title = self._sanitize_title(title or "video")
        candidate = os.path.join(self.download_dir, f"{safe_title}.{ext}")
        if not os.path.exists(candidate):
            return candidate.replace("%", "%%")
        n = 1
        while True:
            candidate = os.path.join(self.download_dir, f"{safe_title} ({n}).{ext}")
            if not os.path.exists(candidate):
                return candidate.replace("%", "%%")
            n += 1

    def _peek_title(self, url: str):
        """다운로드 전에 제목만 빠르게 가져온다 (실패하면 None)."""
        try:
            probe_opts = {
                "noplaylist": True,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(probe_opts, log=self._log) as ydl:
                info = ydl.extract_info(url, download=False)
            return info.get("title")
        except Exception:
            return None

    def _known_title_for(self, url: str):
        """캐시에 제목이 있으면 그걸 쓰고, 없으면 새로 조회해서 캐시에 저장한다."""
        if url in self._title_cache:
            return self._title_cache[url]
        title = self._peek_title(url)
        if title:
            self._title_cache[url] = title
        return title

    def _progress_hook(self, d, prefix=""):
        if d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            percent = (downloaded / total * 100) if total else None

            percent_str = d.get("_percent_str", "").strip()
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            filename = os.path.basename(d.get("filename", ""))

            self._set_progress(
                percent=percent,
                text=f"{prefix}{filename} - {percent_str} (속도 {speed}, 남은시간 {eta})",
            )
        elif d["status"] == "finished":
            self._set_progress(percent=100, text=f"{prefix}변환 중... (ffmpeg 처리 중일 수 있습니다)")
            self._log(f"{prefix}변환 중... (ffmpeg 처리 중일 수 있습니다)")

    def _start_thumbnail_only_download(self):
        if self.is_busy or self.engine_busy:
            return

        urls = self._get_urls()
        if not urls:
            messagebox.showwarning(APP_TITLE, "URL을 입력해주세요.")
            return

        self.is_busy = True
        self._refresh_controls()
        self.download_btn.config(state="disabled")
        self.thumb_only_btn.config(state="disabled")
        self.download_selected_btn.config(state="disabled")
        self.fetch_btn.config(state="disabled")
        self._set_progress(percent=0, text="썸네일 다운로드 준비 중...")

        self._capture_job_options()
        thread = threading.Thread(target=self._run_thumbnail_only_download, args=(urls,), daemon=True)
        thread.start()

    def _run_thumbnail_only_download(self, urls):
        total = len(urls)
        failed = 0
        for idx, url in enumerate(urls, start=1):
            self._log(f"[{idx}/{total}] 썸네일 다운로드 시작: {url}")
            self._set_progress(percent=0, text=f"[{idx}/{total}] 썸네일 받는 중...")

            outtmpl = os.path.join(self.download_dir, "%(title)s.%(ext)s")
            ydl_opts = {
                "outtmpl": outtmpl,
                "skip_download": True,   # 영상/음성은 받지 않고 썸네일만
                "writethumbnail": True,
                "noplaylist": not self._job_options["playlist"],
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts, log=self._log) as ydl:
                    ydl.download([url])
                self._log(f"[{idx}/{total}] 썸네일 저장 완료: {url}")
            except Exception as exc:
                failed += 1
                self._log(f"[{idx}/{total}] 썸네일 다운로드 오류 ({url}): {exc}")
                self._log(traceback.format_exc())

        self._log(f"썸네일 다운로드 종료. 저장 위치: {self.download_dir}")
        self._set_progress(percent=100 if not failed else 0, text=f"썸네일 완료 {total - failed}개 / 실패 {failed}개")
        self.after(0, self._download_finished)

    def _download_finished(self):
        self.is_busy = False
        self.download_btn.config(state="normal")
        self.thumb_only_btn.config(state="normal")
        self.download_selected_btn.config(state="normal")
        self.fetch_btn.config(state="normal")
        self._update_mode_banner()


def main():
    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
