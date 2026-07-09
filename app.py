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
import threading
import queue
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


def resource_path(relative_path: str) -> str:
    """PyInstaller로 패키징된 exe 안에 포함된 리소스(ffmpeg 등) 경로를 찾는다."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


APP_TITLE = "YGT"
APP_SUBTITLE = "You've Got Tube — 간편 유튜브 다운로더"

# 브랜드 컬러
COLOR_PRIMARY = "#2F6FED"
COLOR_PRIMARY_DARK = "#1F4FBF"
COLOR_BG = "#F5F7FB"
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

# 일괄 다운로드(URL 여러 개) 시 사용하는 화질 프리셋 (고화질이 위)
QUALITY_PRESETS = {
    "최고 화질 (mp4)": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080p 이하 (mp4)": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
    "720p 이하 (mp4)": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
    "480p 이하 (mp4)": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
    "오디오만 (mp3)": "bestaudio/best",
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


class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} — You've Got Tube")
        self.geometry("1000x900")
        self.minsize(920, 780)
        self.configure(background=COLOR_BG)

        self._logo_image = None  # 참조 유지 (가비지 컬렉션 방지)
        self._apply_theme()
        self._set_window_icon()

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

        if yt_dlp is None:
            messagebox.showerror(
                APP_TITLE,
                "yt-dlp 모듈을 찾을 수 없습니다.\n"
                "개발 환경에서 실행 중이라면 'pip install yt-dlp'를 먼저 실행하세요.",
            )

    # ---------- 테마 / 아이콘 ----------
    def _apply_theme(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=COLOR_BG, font=(FONT_FAMILY, 10))
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG)
        style.configure("TLabelframe", background=COLOR_BG, bordercolor="#D6DCE8")
        style.configure(
            "TLabelframe.Label", background=COLOR_BG, foreground="#333333", font=(FONT_FAMILY, 10, "bold")
        )
        style.configure("TCheckbutton", background=COLOR_BG)

        style.configure(
            "Accent.TButton",
            background=COLOR_PRIMARY,
            foreground="white",
            font=(FONT_FAMILY, 11, "bold"),
            padding=(14, 8),
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLOR_PRIMARY_DARK), ("disabled", "#A9B6D6")],
        )

        style.configure("Secondary.TButton", padding=(10, 5))

        style.configure("Treeview", rowheight=24, fieldbackground="white")
        style.configure("Treeview.Heading", font=(FONT_FAMILY, 9, "bold"))

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
    def _build_ui(self):
        pad = {"padx": 12, "pady": 8}

        # ===== 헤더 (로고 + 이름) =====
        header = tk.Frame(self, background=COLOR_PRIMARY, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        logo_img = self._load_header_logo(max_size=40)
        if logo_img is not None:
            self._header_logo_ref = logo_img  # 참조 유지
            logo_label = tk.Label(header, image=logo_img, background=COLOR_PRIMARY)
            logo_label.pack(side="left", padx=(16, 8), pady=10)

        title_col = tk.Frame(header, background=COLOR_PRIMARY)
        title_col.pack(side="left", pady=8)
        tk.Label(
            title_col,
            text=APP_TITLE,
            background=COLOR_PRIMARY,
            foreground="white",
            font=(FONT_FAMILY, 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_col,
            text=APP_SUBTITLE,
            background=COLOR_PRIMARY,
            foreground="#DCE6FF",
            font=(FONT_FAMILY, 9),
        ).pack(anchor="w")

        # ===== 스크롤 가능한 본문 =====
        body_canvas = tk.Canvas(self, background=COLOR_BG, highlightthickness=0)
        body_scroll = ttk.Scrollbar(self, orient="vertical", command=body_canvas.yview)
        body = ttk.Frame(body_canvas)
        body.bind("<Configure>", lambda e: body_canvas.configure(scrollregion=body_canvas.bbox("all")))
        body_canvas.create_window((0, 0), window=body, anchor="nw")
        body_canvas.configure(yscrollcommand=body_scroll.set)
        body_canvas.pack(side="left", fill="both", expand=True)
        body_scroll.pack(side="right", fill="y")

        def _on_mousewheel(event):
            body_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        body_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ---- 1. URL 입력 ----
        url_box = ttk.Labelframe(body, text="1. 영상 URL 입력", padding=10)
        url_box.pack(fill="x", **pad)
        ttk.Label(
            url_box,
            text="한 줄에 하나씩 붙여넣으세요. 입력한 개수에 따라 아래 2번 또는 3번 섹션이 자동으로 켜집니다.",
            foreground=COLOR_TEXT_MUTED,
        ).pack(anchor="w")
        entry_row = ttk.Frame(url_box)
        entry_row.pack(fill="x", pady=(6, 0))
        self.url_text = tk.Text(entry_row, height=4, wrap="none")
        self.url_text.pack(side="left", fill="x", expand=True)
        url_scroll = ttk.Scrollbar(entry_row, orient="vertical", command=self.url_text.yview)
        self.url_text.configure(yscrollcommand=url_scroll.set)
        url_scroll.pack(side="left", fill="y")

        self.mode_banner = ttk.Label(url_box, text="", font=(FONT_FAMILY, 9, "bold"))
        self.mode_banner.pack(anchor="w", pady=(8, 0))
        self.url_text.bind("<KeyRelease>", self._update_mode_banner)
        self.url_text.bind("<<Paste>>", lambda e: self.after(10, self._update_mode_banner))

        # ---- 2. 단일 링크 모드 (URL 정확히 1개) ----
        single_box = ttk.Labelframe(body, text="2. 단일 링크 모드 — 화질/코덱을 직접 골라 다운로드 (URL 1개 전용)", padding=10)
        single_box.pack(fill="both", expand=True, **pad)

        self.fetch_btn = ttk.Button(
            single_box, text="🔍 정보 가져오기", style="Secondary.TButton", command=self._start_fetch_info
        )
        self.fetch_btn.pack(anchor="w")

        self.title_label = ttk.Label(single_box, text="", font=(FONT_FAMILY, 10, "bold"), wraplength=900)
        self.title_label.pack(fill="x", pady=(8, 0))

        ttk.Label(
            single_box,
            text="추천 조합 (고화질 순 정렬 · 원하는 줄을 더블클릭하면 바로 다운로드됩니다)",
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(anchor="w", pady=(10, 0))
        combo_container = ttk.Frame(single_box)
        combo_container.pack(fill="both", expand=True, pady=(4, 0))
        self.combo_tree = ttk.Treeview(
            combo_container, columns=COMBO_COLUMNS, show="headings", selectmode="browse", height=6
        )
        for col in COMBO_COLUMNS:
            self.combo_tree.heading(col, text=COMBO_COLUMN_LABELS[col])
            self.combo_tree.column(col, width=COMBO_COLUMN_WIDTHS[col], anchor="center")
        self.combo_tree.column("note", anchor="w")
        combo_vsb = ttk.Scrollbar(combo_container, orient="vertical", command=self.combo_tree.yview)
        self.combo_tree.configure(yscrollcommand=combo_vsb.set)
        self.combo_tree.pack(side="left", fill="both", expand=True)
        combo_vsb.pack(side="left", fill="y")
        self.combo_tree.bind("<Double-1>", self._on_combo_double_click)

        ttk.Label(
            single_box,
            text="💡 프리미어 프로 등 편집 프로그램에 쓰려면 avc1(H.264) 코덱의 mp4를 추천합니다. "
            "VP9/AV1 코덱은 편집 시 버벅임이 있을 수 있어요.",
            foreground=COLOR_TEXT_MUTED,
            font=(FONT_FAMILY, 8),
        ).pack(anchor="w", pady=(6, 0))

        self.mp3_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            single_box,
            text="선택한 항목을 mp3로 변환",
            variable=self.mp3_var,
        ).pack(anchor="w", pady=(6, 0))

        self.adv_toggle_btn = ttk.Button(
            single_box,
            text="🔧 고급: 전체 포맷 직접 조합 보기 ▸",
            style="Secondary.TButton",
            command=self._toggle_advanced,
        )
        self.adv_toggle_btn.pack(anchor="w", pady=(10, 0))

        self.adv_container = ttk.Frame(single_box)
        ttk.Label(
            self.adv_container,
            text="Ctrl+클릭으로 '영상만' 1개 + '음성만' 1개를 직접 골라 조합할 수 있습니다.",
            foreground=COLOR_TEXT_MUTED,
        ).pack(anchor="w")
        raw_container = ttk.Frame(self.adv_container)
        raw_container.pack(fill="both", expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(
            raw_container, columns=RAW_COLUMNS, show="headings", selectmode="extended", height=6
        )
        for col in RAW_COLUMNS:
            self.tree.heading(col, text=RAW_COLUMN_LABELS[col])
            self.tree.column(col, width=RAW_COLUMN_WIDTHS[col], anchor="center")
        self.tree.column("note", anchor="w")
        vsb = ttk.Scrollbar(raw_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        # adv_container는 기본적으로 접혀 있음 (버튼으로 펼침)

        # ---- 3. 여러 링크 일괄 다운로드 (URL 2개 이상) ----
        batch_box = ttk.Labelframe(body, text="3. 여러 링크 일괄 다운로드 — URL 2개 이상일 때 사용", padding=10)
        batch_box.pack(fill="both", expand=True, **pad)

        self.preview_btn = ttk.Button(
            batch_box,
            text="👀 제목 미리보기 (링크 확인)",
            style="Secondary.TButton",
            command=self._start_preview_titles,
        )
        self.preview_btn.pack(anchor="w")

        preview_frame = ttk.Frame(batch_box)
        preview_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(
            preview_frame,
            text="링크별 제목 확인 결과 — 더블클릭: 그 영상 1개 바로 다운로드 · Ctrl+클릭/Shift+클릭: 여러 개 선택",
        ).pack(anchor="w")
        preview_container = ttk.Frame(preview_frame)
        preview_container.pack(fill="x", pady=(4, 0))
        self.preview_tree = ttk.Treeview(
            preview_container,
            columns=("num", "status", "title", "url"),
            show="headings",
            selectmode="extended",
            height=5,
        )
        self.preview_tree.heading("num", text="#")
        self.preview_tree.heading("status", text="상태")
        self.preview_tree.heading("title", text="제목")
        self.preview_tree.heading("url", text="URL")
        self.preview_tree.column("num", width=30, anchor="center")
        self.preview_tree.column("status", width=60, anchor="center")
        self.preview_tree.column("title", width=380, anchor="w")
        self.preview_tree.column("url", width=380, anchor="w")
        preview_vsb = ttk.Scrollbar(preview_container, orient="vertical", command=self.preview_tree.yview)
        self.preview_tree.configure(yscrollcommand=preview_vsb.set)
        self.preview_tree.pack(side="left", fill="x", expand=True)
        preview_vsb.pack(side="left", fill="y")
        self.preview_tree.bind("<Double-1>", self._on_preview_double_click)

        preview_action_row = ttk.Frame(batch_box)
        preview_action_row.pack(fill="x", pady=(6, 0))
        self.download_selected_btn = ttk.Button(
            preview_action_row,
            text="⬇ 선택한 항목만 다운로드",
            style="Secondary.TButton",
            command=self._download_selected_previews,
        )
        self.download_selected_btn.pack(side="left")
        ttk.Label(
            preview_action_row,
            text="(위 표에서 Ctrl+클릭으로 여러 제목을 고른 뒤 눌러도 됩니다)",
            foreground=COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(8, 0))

        preset_row = ttk.Frame(batch_box)
        preset_row.pack(fill="x", pady=(10, 0))
        ttk.Label(preset_row, text="일괄 다운로드 화질:").pack(side="left")
        self.preset_var = tk.StringVar(value=list(QUALITY_PRESETS.keys())[0])
        preset_combo = ttk.Combobox(
            preset_row,
            textvariable=self.preset_var,
            values=list(QUALITY_PRESETS.keys()),
            state="readonly",
            width=22,
        )
        preset_combo.pack(side="left", padx=(6, 0))
        ttk.Label(
            preset_row, text="(아래 '다운로드 시작'을 누르면 이 화질로 전체 순차 다운로드)", foreground=COLOR_TEXT_MUTED
        ).pack(side="left", padx=(8, 0))

        # ---- 4. 공통 옵션 ----
        options_box = ttk.Labelframe(body, text="4. 공통 옵션 (단일/일괄 모두 적용)", padding=10)
        options_box.pack(fill="x", **pad)

        self.playlist_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_box, text="재생목록 전체 다운로드", variable=self.playlist_var
        ).pack(side="left")

        self.subtitle_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_box, text="자막 함께 다운로드 (있는 경우)", variable=self.subtitle_var
        ).pack(side="left", padx=(20, 0))

        self._update_mode_banner()

        # ---- 5. 저장 위치 & 다운로드 ----
        action_box = ttk.Labelframe(body, text="5. 저장 위치 및 다운로드", padding=10)
        action_box.pack(fill="x", **pad)

        folder_row = ttk.Frame(action_box)
        folder_row.pack(fill="x")
        ttk.Label(folder_row, text="저장 위치:").pack(side="left")
        self.folder_label = ttk.Label(folder_row, text=self.download_dir, relief="sunken", anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True, ipady=3, padx=(6, 6))
        ttk.Button(folder_row, text="변경", style="Secondary.TButton", command=self._choose_folder).pack(side="left")

        button_frame = ttk.Frame(action_box)
        button_frame.pack(fill="x", pady=(10, 0))
        self.download_btn = ttk.Button(
            button_frame, text="⬇  다운로드 시작", style="Accent.TButton", command=self._start_download
        )
        self.download_btn.pack(side="left")

        progress_col = ttk.Frame(button_frame)
        progress_col.pack(side="left", padx=(14, 0), fill="x", expand=True)
        self.progress = ttk.Progressbar(progress_col, mode="determinate", maximum=100, length=400)
        self.progress.pack(fill="x")
        self.progress_label = ttk.Label(progress_col, text="대기 중", foreground=COLOR_TEXT_MUTED)
        self.progress_label.pack(anchor="w")

        # ---- 6. 로그 ----
        log_box = ttk.Labelframe(body, text="6. 진행 상황 로그", padding=10)
        log_box.pack(fill="both", expand=True, **pad)
        log_container = ttk.Frame(log_box)
        log_container.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_container, height=12, state="disabled", wrap="word")
        log_vsb = ttk.Scrollbar(log_container, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_vsb.pack(side="left", fill="y")

    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_dir)
        if folder:
            self.download_dir = folder
            self.folder_label.config(text=folder)

    # ---------- 단일/일괄 모드 전환 ----------
    def _update_mode_banner(self, _event=None):
        urls = self._get_urls()
        n = len(urls)
        if n == 0:
            text = "URL을 입력하면 아래 섹션이 활성화됩니다."
            color = COLOR_TEXT_MUTED
            single_enabled = False
        elif n == 1:
            text = "✅ 링크 1개 입력됨 — 아래 '2. 단일 링크 모드'에서 화질/코덱을 골라 다운로드하세요."
            color = "#1F8A44"
            single_enabled = True
        else:
            text = f"📦 링크 {n}개 입력됨 — '2. 단일 링크 모드'는 비활성화되고, 아래 '3. 여러 링크 일괄 다운로드'를 사용하세요."
            color = "#B8860B"
            single_enabled = False

        self.mode_banner.config(text=text, foreground=color)
        if not self.is_busy:
            self.fetch_btn.config(state="normal" if single_enabled else "disabled")

    def _toggle_advanced(self):
        self.adv_visible = not self.adv_visible
        if self.adv_visible:
            self.adv_container.pack(fill="both", expand=True, pady=(8, 0))
            self.adv_toggle_btn.config(text="🔧 고급: 전체 포맷 직접 조합 숨기기 ▾")
        else:
            self.adv_container.pack_forget()
            self.adv_toggle_btn.config(text="🔧 고급: 전체 포맷 직접 조합 보기 ▸")

    def _on_preview_double_click(self, event):
        if self.is_busy:
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
        if self.is_busy:
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
                self.log_text.config(state="normal")
                self.log_text.insert("end", message + "\n")
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
        if self.is_busy:
            return
        if yt_dlp is None:
            messagebox.showerror(APP_TITLE, "yt-dlp 모듈이 설치되어 있지 않습니다.")
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
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,  # 정보 조회는 대표 영상 1개 기준
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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

    def _fetch_finished(self):
        self.is_busy = False
        self._update_mode_banner()
        self._set_progress(percent=0, text="대기 중")

    # ---------- 제목 미리보기 (URL 여러 개 확인용) ----------
    def _start_preview_titles(self):
        if self.is_busy:
            return
        if yt_dlp is None:
            messagebox.showerror(APP_TITLE, "yt-dlp 모듈이 설치되어 있지 않습니다.")
            return

        urls = self._get_urls()
        if not urls:
            messagebox.showwarning(APP_TITLE, "URL을 입력해주세요.")
            return

        self.is_busy = True
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
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
        }
        for idx, url in enumerate(urls, start=1):
            self._set_progress(percent=int((idx - 1) / total * 100), text=f"[{idx}/{total}] 제목 확인 중...")
            self.after(0, lambda i=idx, u=url: self._update_preview_row(i, "확인중", "확인 중...", u))
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
        self._set_progress(percent=100, text="제목 확인 완료")
        self.after(0, self._preview_finished)

    def _preview_finished(self):
        self.is_busy = False
        self.preview_btn.config(state="normal")
        self.download_btn.config(state="normal")
        self.download_selected_btn.config(state="normal")
        self._update_mode_banner()

    def _on_combo_double_click(self, _event):
        if self.is_busy:
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
        if self.is_busy:
            return
        if yt_dlp is None:
            messagebox.showerror(APP_TITLE, "yt-dlp 모듈이 설치되어 있지 않습니다.")
            return

        urls = self._get_urls()
        if not urls:
            messagebox.showwarning(APP_TITLE, "URL을 입력해주세요.")
            return

        combo_selection = self.combo_tree.selection()
        raw_selection = self.tree.selection()

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
        self.download_btn.config(state="disabled")
        self.download_selected_btn.config(state="disabled")
        self.fetch_btn.config(state="disabled")
        self._set_progress(percent=0, text="다운로드 준비 중...")

        if is_combo:
            format_ids = self.combo_map.get(selection, selection).split("+")
            thread = threading.Thread(
                target=self._run_precise_download, args=(url, format_ids), daemon=True
            )
        else:
            thread = threading.Thread(
                target=self._run_precise_download, args=(url, list(selection)), daemon=True
            )
        thread.start()

    def _begin_batch_download(self, urls):
        self.is_busy = True
        self.download_btn.config(state="disabled")
        self.download_selected_btn.config(state="disabled")
        self.fetch_btn.config(state="disabled")
        self._set_progress(percent=0, text="다운로드 준비 중...")
        thread = threading.Thread(target=self._run_batch_download, args=(urls,), daemon=True)
        thread.start()

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
                return f"{fmt_id}+bestaudio/best", has_video, True
            return fmt_id, has_video, has_audio
        else:
            # 2개 선택(또는 미리 만든 조합): '+'로 합쳐서 영상+음성 병합
            return "+".join(format_ids), True, True

    def _run_precise_download(self, url: str, format_ids):
        format_selector, has_video, has_audio = self._build_format_selector(format_ids)
        want_mp3 = self.mp3_var.get()

        self._log(f"다운로드 시작 ({format_ids}): {url}")

        if want_mp3:
            expected_ext = "mp3"
        elif has_video:
            expected_ext = "mp4"
        else:
            fmt_info = self.current_formats.get(format_ids[0], {}) if format_ids else {}
            expected_ext = fmt_info.get("ext") or "m4a"

        is_playlist = self.playlist_var.get()
        if not is_playlist and self.video_title:
            # 같은 이름의 파일이 이미 있으면 '(1)' 식으로 번호를 붙여 겹치지 않게 저장
            outtmpl = self._unique_output_path(self.video_title, expected_ext)
        else:
            outtmpl = os.path.join(self.download_dir, "%(title)s.%(ext)s")

        ydl_opts = {
            "format": format_selector,
            "outtmpl": outtmpl,
            "noplaylist": not self.playlist_var.get(),
            "progress_hooks": [self._progress_hook],
            "ffmpeg_location": self._ffmpeg_location(),
            "quiet": True,
            "no_warnings": True,
        }

        if want_mp3:
            ydl_opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        elif has_video:
            ydl_opts["merge_output_format"] = "mp4"

        if self.subtitle_var.get():
            ydl_opts.update(
                {"writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": ["ko", "en"]}
            )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self._log("완료! 저장 위치: " + self.download_dir)
            self._set_progress(percent=100, text="완료")
        except Exception as exc:
            self._log("오류 발생: " + str(exc))
            self._log(traceback.format_exc())
            self._set_progress(percent=0, text="오류 발생")
        finally:
            self.after(0, self._download_finished)

    def _run_batch_download(self, urls):
        preset_label = self.preset_var.get()
        format_selector = QUALITY_PRESETS[preset_label]
        is_audio_only = preset_label.startswith("오디오만")
        expected_ext = "mp3" if is_audio_only else "mp4"
        is_playlist = self.playlist_var.get()

        total = len(urls)
        for idx, url in enumerate(urls, start=1):
            self._log(f"[{idx}/{total}] 다운로드 시작: {url}")
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
                "noplaylist": not self.playlist_var.get(),
                "progress_hooks": [lambda d, i=idx, t=total: self._progress_hook(d, prefix=f"[{i}/{t}] ")],
                "ffmpeg_location": self._ffmpeg_location(),
                "quiet": True,
                "no_warnings": True,
            }

            if is_audio_only:
                ydl_opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ]
            else:
                ydl_opts["merge_output_format"] = "mp4"

            if self.subtitle_var.get():
                ydl_opts.update(
                    {"writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": ["ko", "en"]}
                )

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                self._log(f"[{idx}/{total}] 완료: {url}")
            except Exception as exc:
                self._log(f"[{idx}/{total}] 오류 발생 ({url}): {exc}")

        self._log(f"일괄 다운로드 종료. 저장 위치: {self.download_dir}")
        self._set_progress(percent=100, text="전체 완료")
        self.after(0, self._download_finished)

    def _ffmpeg_location(self):
        ffmpeg_name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
        bundled = resource_path(ffmpeg_name)
        if os.path.exists(bundled):
            return bundled
        return None  # 시스템 PATH에 있는 ffmpeg 사용 시도

    def _sanitize_title(self, title: str) -> str:
        try:
            from yt_dlp.utils import sanitize_filename
            return sanitize_filename(title, restricted=False)
        except Exception:
            # 최소한의 안전장치: 파일명에 못 쓰는 문자만 제거
            return "".join(c for c in title if c not in '\\/:*?"<>|').strip() or "video"

    def _unique_output_path(self, title: str, ext: str) -> str:
        """저장 위치에 같은 이름의 파일이 이미 있으면 '제목 (1).ext' 식으로 번호를 붙여
        겹치지 않는 경로를 만들어 반환한다. (브라우저 다운로드와 동일한 방식)"""
        safe_title = self._sanitize_title(title or "video")
        candidate = os.path.join(self.download_dir, f"{safe_title}.{ext}")
        if not os.path.exists(candidate):
            return candidate
        n = 1
        while True:
            candidate = os.path.join(self.download_dir, f"{safe_title} ({n}).{ext}")
            if not os.path.exists(candidate):
                return candidate
            n += 1

    def _peek_title(self, url: str):
        """다운로드 전에 제목만 빠르게 가져온다 (실패하면 None)."""
        try:
            probe_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(probe_opts) as ydl:
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

    def _download_finished(self):
        self.is_busy = False
        self.download_btn.config(state="normal")
        self.download_selected_btn.config(state="normal")
        self._update_mode_banner()


def main():
    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
