"""YGT desktop layout and nested scrolling. Network work stays outside Tk's thread."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import ygt_engine
from ygt_formats import CODECS, codec_key, codec_family

BG = '#141820'
WHITE = '#1D2330'  # Raised surface, retained name for existing layout helpers.
INK = '#E5EAF3'
MUTED = '#A0ACC0'
BLUE = '#7C9BFF'
LINE = '#323D50'
INPUT = '#171D28'
FONT = 'Apple SD Gothic Neo' if sys.platform == 'darwin' else '맑은 고딕' if os.name == 'nt' else 'DejaVu Sans'

class ScrollPage(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, yscrollincrement=1)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas, padding=(24, 20, 24, 24))
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.body)
        self.canvas.bind('<Configure>', self._resize)
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        scrollbar._wheel_target = self.canvas

    def _resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

class DesktopUI:
    def _apply_theme(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=(FONT, 12), foreground=INK, background=BG,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG)
        style.configure('Card.TFrame', background=WHITE)
        style.configure('Card.TLabel', background=WHITE)
        style.configure('Muted.TLabel', foreground=MUTED, background=WHITE, font=(FONT, 11))
        style.configure('Title.TLabel', font=(FONT, 15, 'bold'), background=WHITE)
        style.configure('TButton', padding=(14, 9), background='#283244', borderwidth=0, relief='flat',
                        bordercolor='#283244', lightcolor='#283244', darkcolor='#283244')
        style.map('TButton', background=[('disabled', '#212938'), ('active', '#35435B')],
                  foreground=[('disabled', '#738096')], bordercolor=[('focus', BLUE)])
        style.configure('Accent.TButton', background=BLUE, foreground='#111B35', padding=(24, 12), font=(FONT, 13, 'bold'))
        style.map('Accent.TButton', background=[('disabled', '#2D3A58'), ('active', '#9AB1FF')],
                  foreground=[('disabled', '#8291AF'), ('!disabled', '#111B35')])
        style.configure('Nav.TButton', background=BG, foreground=MUTED, padding=(18, 10))
        style.configure('Selected.Nav.TButton', background='#293651', foreground='#B4C6FF')
        style.configure('TCheckbutton', background=WHITE, padding=(0, 6), indicatorbackground=INPUT,
                        indicatorforeground=BLUE, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.map('TCheckbutton', background=[('active', WHITE)], foreground=[('disabled', '#738096')],
                  indicatorbackground=[('selected', '#506ECD'), ('!selected', INPUT)])
        style.configure('TCombobox', padding=9, fieldbackground=INPUT, background='#283244',
                        foreground=INK, arrowcolor=MUTED, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.map('TCombobox', fieldbackground=[('readonly', INPUT), ('disabled', INPUT)],
                  foreground=[('disabled', '#738096')], selectbackground=[('readonly', INPUT)],
                  selectforeground=[('readonly', INK)])
        self.option_add('*TCombobox*Listbox.background', INPUT)
        self.option_add('*TCombobox*Listbox.foreground', INK)
        self.option_add('*TCombobox*Listbox.selectBackground', '#344C79')
        self.option_add('*TCombobox*Listbox.selectForeground', INK)
        style.configure('TNotebook', borderwidth=0, background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG)
        style.layout('TNotebook.Tab', [])
        for orient in ('Vertical', 'Horizontal'):
            style.layout(orient + '.TScrollbar', [(orient + '.Scrollbar.trough', {'sticky': 'nswe',
                         'children': [(orient + '.Scrollbar.thumb', {'sticky': 'nswe'})]})])
            style.configure(orient + '.TScrollbar', background='#46536B', troughcolor=BG,
                            bordercolor=BG, lightcolor='#46536B', darkcolor='#46536B',
                            borderwidth=0, arrowsize=9, width=9, relief='flat')
            style.map(orient + '.TScrollbar', background=[('active', '#62728E')])
        style.configure('Treeview', rowheight=34, background=INPUT, fieldbackground=INPUT, foreground=INK,
                        borderwidth=0, font=(FONT, 11), bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.configure('Treeview.Heading', background='#283244', foreground=MUTED, padding=9, font=(FONT, 10, 'bold'), relief='flat')
        style.map('Treeview', background=[('selected', '#344C79')], foreground=[('selected', '#F0F4FF')])
        style.map('Treeview.Heading', background=[('active', '#34415A')])
        style.configure('Horizontal.TProgressbar', troughcolor='#283244', background=BLUE,
                        bordercolor='#283244', lightcolor=BLUE, darkcolor=BLUE, borderwidth=0, thickness=4)

    def _card(self, parent, title, description=None):
        frame = ttk.Frame(parent, style='Card.TFrame', padding=18)
        frame.pack(fill='x', pady=(0, 12))
        ttk.Label(frame, text=title, style='Title.TLabel').pack(anchor='w')
        if description:
            ttk.Label(frame, text=description, style='Muted.TLabel', wraplength=620).pack(anchor='w', pady=(4, 12))
        return frame

    def _text(self, parent, height=4, readonly=False):
        box = ttk.Frame(parent, style='Card.TFrame')
        box.pack(fill='both', expand=True, pady=(8, 0))
        text = tk.Text(box, height=height, wrap='word', font=(FONT, 12), bg=INPUT, fg=INK,
                       insertbackground=BLUE, selectbackground='#344C79', padx=12, pady=10,
                       highlightthickness=1, highlightbackground=LINE, highlightcolor=BLUE, relief='flat',
                       state='disabled' if readonly else 'normal', undo=not readonly)
        bar = ttk.Scrollbar(box, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        text.pack(side='left', fill='both', expand=True)
        bar._wheel_target = text
        return text

    def _table(self, parent, columns, height=5, multi=False):
        box = ttk.Frame(parent, style='Card.TFrame')
        box.pack(fill='both', expand=True, pady=(10, 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        tree = ttk.Treeview(box, columns=[c[0] for c in columns], show='headings',
                           selectmode='extended' if multi else 'browse', height=height)
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=width, stretch=True, anchor='w')
        vertical = ttk.Scrollbar(box, command=tree.yview)
        horizontal = ttk.Scrollbar(box, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        vertical._wheel_target = tree
        horizontal._wheel_target = tree
        return tree

    def _build_ui(self):
        self.engine_events = queue.Queue()
        self.engine_busy = False
        self._closing = False
        self._last_controls = None
        self._last_urls = None
        self._load_preferences()
        header = ttk.Frame(self, padding=(24, 14))
        header.pack(fill='x')
        mark = tk.Label(header, text='YGT', font=(FONT, 22, 'bold'), fg=BLUE, bg=BG)
        mark.pack(side='left')
        ttk.Label(header, text='VIDEO DOWNLOADER', foreground=MUTED).pack(side='left', padx=16)
        self.update_btn = ttk.Button(header, text='업데이트 확인', command=self._check_updates)
        self.update_btn.pack(side='right')
        self.engine_label = ttk.Label(header, text='다운로드 엔진 준비 중', foreground=MUTED, font=(FONT, 10))
        self.engine_label.pack(side='right', padx=12)

        # Pack the persistent action area before the expanding notebook.
        footer = ttk.Frame(self, style='Card.TFrame', padding=(24, 16))
        footer.pack(side='bottom', fill='x')
        self.progress = ttk.Progressbar(footer, maximum=100)
        self.progress.pack(fill='x', pady=(0, 12))
        row = ttk.Frame(footer, style='Card.TFrame')
        row.pack(fill='x')
        self.download_btn = ttk.Button(row, text='다운로드 시작', style='Accent.TButton', command=self._start_download)
        self.download_btn.pack(side='right')
        self.progress_label = ttk.Label(row, text='링크를 붙여넣어 시작하세요', style='Muted.TLabel', wraplength=450)
        self.progress_label.pack(side='left', fill='x', expand=True, padx=(0, 14))
        row.bind('<Configure>', lambda e: self.progress_label.configure(wraplength=max(180, e.width-220)))

        self.nav = ttk.Frame(self, padding=(24, 0, 24, 8))
        self.nav.pack(fill='x')
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)
        self.download_page = ScrollPage(self.notebook)
        self.detail_page = ScrollPage(self.notebook)
        self.log_page = ttk.Frame(self.notebook, padding=24)
        self.notebook.add(self.download_page, text='다운로드')
        self.notebook.add(self.detail_page, text='포맷 직접 선택')
        self.notebook.add(self.log_page, text='작업 기록')
        self.notebook.bind('<<NotebookTabChanged>>', lambda e: self._update_mode_banner())
        self.nav_buttons = []
        for title, page in [('다운로드', self.download_page), ('포맷 직접 선택', self.detail_page), ('작업 기록', self.log_page)]:
            button = ttk.Button(self.nav, text=title, style='Nav.TButton', command=lambda p=page: self.notebook.select(p))
            button.pack(side='left', padx=(0, 6))
            self.nav_buttons.append((button, page))
        body = self.download_page.body

        link = self._card(body, '영상 링크', '한 줄에 하나씩 붙여넣으세요. 여러 영상도 한 번에 받을 수 있어요.')
        self.url_text = self._text(link, height=2)
        actions = ttk.Frame(link, style='Card.TFrame')
        actions.pack(fill='x', pady=(12, 0))
        ttk.Button(actions, text='클립보드에서 붙여넣기', command=lambda: self._paste_into(self.url_text)).pack(side='left')
        ttk.Button(actions, text='비우기', command=lambda: self._clear_text(self.url_text)).pack(side='left', padx=8)
        self.mode_banner = ttk.Label(actions, text='링크 없음', style='Muted.TLabel')
        self.mode_banner.pack(side='right')
        self._enable_text_editing_shortcuts(self.url_text)
        self.url_text.bind('<<Modified>>', self._links_modified)

        options = self._card(body, '화질 · 코덱', '원하는 화질과 코덱을 선택하세요. 영상과 소리를 함께 저장합니다.')
        self.preset_var = tk.StringVar(value=self._preferences.get('quality', '1080p 이하').replace(' (mp4)', ''))
        qualities = ['최고 화질', '1080p 이하', '720p 이하', '480p 이하', '오디오만 (mp3)']
        if self.preset_var.get() not in qualities:
            self.preset_var.set(qualities[1])
        selection_row = ttk.Frame(options, style='Card.TFrame')
        selection_row.pack(fill='x', pady=(0, 10))
        selection_row.columnconfigure(0, weight=1)
        selection_row.columnconfigure(1, weight=1)
        ttk.Label(selection_row, text='화질 / 오디오', style='Muted.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 6))
        ttk.Label(selection_row, text='영상 코덱', style='Muted.TLabel').grid(row=0, column=1, sticky='w', padx=(14, 0), pady=(0, 6))
        self.preset_combo = ttk.Combobox(selection_row, textvariable=self.preset_var, values=qualities, state='readonly', width=23)
        self.preset_combo.grid(row=1, column=0, sticky='ew')
        self.codec_var = tk.StringVar(value=self._preferences.get('codec', CODECS[0]))
        if self.codec_var.get() not in CODECS:
            self.codec_var.set(CODECS[0])
        self.codec_combo = ttk.Combobox(selection_row, textvariable=self.codec_var, values=CODECS, state='readonly', width=23)
        self.codec_combo.grid(row=1, column=1, sticky='ew', padx=(14, 0))
        self.codec_hint = ttk.Label(options, text='', style='Muted.TLabel', wraplength=620)
        self.codec_hint.pack(anchor='w', pady=(0, 8))
        self.codec_combo.bind('<<ComboboxSelected>>', self._codec_changed)
        self._codec_changed(save=False)
        self.preset_combo.bind('<<ComboboxSelected>>', self._codec_changed)
        self.playlist_var = tk.BooleanVar(value=False)
        self.subtitle_var = tk.BooleanVar(value=False)
        self.embed_thumb_var = tk.BooleanVar(value=False)
        self.save_thumb_var = tk.BooleanVar(value=False)
        self.option_controls = []
        checks = ttk.Frame(options, style='Card.TFrame')
        checks.pack(fill='x')
        for i, (text, var) in enumerate([
            ('재생목록 전체 받기', self.playlist_var), ('한국어·영어 자막 함께 받기', self.subtitle_var),
            ('파일에 썸네일 넣기', self.embed_thumb_var), ('썸네일 이미지도 저장', self.save_thumb_var)]):
            check = ttk.Checkbutton(checks, text=text, variable=var)
            check.grid(row=i//2, column=i%2, sticky='w', padx=(0, 24))
            self.option_controls.append(check)
        self.thumb_only_btn = ttk.Button(options, text='영상 없이 썸네일만 받기', command=self._start_thumbnail_only_download)
        self.thumb_only_btn.pack(anchor='w', pady=(12, 0))

        folder = self._card(body, '저장 위치')
        self.folder_label = ttk.Label(folder, text=self._display_folder(self.download_dir), style='Muted.TLabel', wraplength=620)
        self.folder_label.pack(fill='x', pady=(6, 10))
        folder_actions = ttk.Frame(folder, style='Card.TFrame')
        folder_actions.pack(fill='x')
        self.folder_change_btn = ttk.Button(folder_actions, text='폴더 변경', command=self._choose_folder)
        self.folder_change_btn.pack(side='left')
        ttk.Button(folder_actions, text='폴더 열기', command=self._open_folder).pack(side='left', padx=8)

        preview = self._card(body, '링크 확인', '선택 사항이에요. 제목을 확인한 뒤 원하는 영상만 골라 받을 수 있어요.')
        self.preview_btn = ttk.Button(preview, text='영상 제목 확인', command=self._start_preview_titles)
        self.preview_btn.pack(anchor='w')
        self.preview_tree = self._table(preview, [('num', '#', 35), ('status', '상태', 85), ('title', '영상 제목', 300), ('url', '링크', 250)], multi=True)
        self.download_selected_btn = ttk.Button(preview, text='선택한 영상만 받기', command=self._download_selected_previews)
        self.download_selected_btn.pack(anchor='w', pady=(12, 0))

        detail = self._card(self.detail_page.body, '실제 포맷에서 선택', '영상 정보를 불러오면 제공되는 코덱·해상도·FPS·용량을 비교할 수 있어요.')
        self.fetch_btn = ttk.Button(detail, text='사용 가능한 포맷 불러오기', command=self._start_fetch_info)
        self.fetch_btn.pack(anchor='w')
        self.title_label = ttk.Label(detail, text='아직 불러온 영상이 없어요', style='Muted.TLabel', wraplength=620)
        self.title_label.pack(anchor='w', pady=(12, 0))
        self.combo_tree = self._table(detail, [('resolution','해상도',90), ('fps','FPS',45), ('vcodec','영상 코덱',90), ('acodec','오디오',80), ('ext','원본 형식',70), ('size','예상 용량',90), ('note','정보',190)])
        ttk.Label(detail, text='선택한 ID·코덱 그대로 다운로드 · 영상은 코덱 변환 없이 MKV로 저장', style='Muted.TLabel', wraplength=620).pack(anchor='w', pady=10)
        self.mp3_var = tk.BooleanVar(value=False)
        mp3_check = ttk.Checkbutton(detail, text='선택한 포맷을 MP3로 변환', variable=self.mp3_var)
        mp3_check.pack(anchor='w')
        self.option_controls.append(mp3_check)
        self.adv_toggle_btn = ttk.Button(detail, text='영상·오디오 따로 선택', command=self._toggle_advanced)
        self.adv_toggle_btn.pack(anchor='w', pady=(12, 0))
        self.adv_container = ttk.Frame(detail, style='Card.TFrame')
        ttk.Label(self.adv_container, text='영상 1개와 오디오 1개까지 선택할 수 있어요. 이 목록은 포맷 ID를 그대로 사용합니다.', style='Muted.TLabel', wraplength=600).pack(anchor='w', pady=(12,0))
        self.tree = self._table(self.adv_container, [('format_id','ID',65), ('type','유형',80), ('resolution','해상도',95), ('fps','FPS',45), ('vcodec','영상 코덱',100), ('acodec','오디오',90), ('ext','원본 형식',70), ('size','용량',90), ('note','정보',180)], multi=True)
        self.combo_tree.bind('<<TreeviewSelect>>', lambda e: self._exclusive_selection(self.combo_tree, self.tree))
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._exclusive_selection(self.tree, self.combo_tree))

        ttk.Label(self.log_page, text='작업 기록', font=(FONT, 19, 'bold')).pack(anchor='w')
        ttk.Label(self.log_page, text='업데이트와 다운로드 결과를 여기에서 확인하세요.', foreground=MUTED).pack(anchor='w', pady=(4, 12))
        ttk.Button(self.log_page, text='기록 복사', command=self._copy_log).pack(anchor='w')
        self.log_text = self._text(self.log_page, height=12, readonly=True)
        self.log_text.configure(font=('Menlo' if sys.platform=='darwin' else 'Consolas', 10))
        self._install_wheel_bindings()
        self._update_mode_banner()
        self.after_idle(self.url_text.focus_set)
        self.after(120, self._check_updates)
        self.after(150, self._poll_ui_state)
        self.protocol('WM_DELETE_WINDOW', self._close_window)

    def _links_modified(self, event=None):
        if self.url_text.edit_modified():
            self.url_text.edit_modified(False)
            self._update_mode_banner()

    def _update_mode_banner(self, _event=None):
        if not hasattr(self, 'download_btn') or not hasattr(self, 'url_text'):
            return
        urls = tuple(self._get_urls())
        self.mode_banner.configure(text=f'링크 {len(urls)}개' if urls else '링크 없음')
        if urls != self._last_urls:
            self._last_urls = urls
            # Results belong to the input they were fetched for.
            if hasattr(self, 'preview_tree') and not self.is_busy:
                self.preview_tree.selection_remove(self.preview_tree.selection())
                self._preview_urls = []
                self.preview_tree.delete(*self.preview_tree.get_children())
        self._refresh_controls()

    def _refresh_controls(self):
        if not hasattr(self, 'fetch_btn'):
            return
        count = len(self._get_urls())
        blocked = self.is_busy or self.engine_busy
        enabled = bool(count) and not blocked
        for widget in (self.download_btn, self.thumb_only_btn, self.preview_btn):
            widget.configure(state='normal' if enabled else 'disabled')
        self.download_selected_btn.configure(state='normal' if enabled and self._preview_urls else 'disabled')
        self.fetch_btn.configure(state='normal' if count == 1 and not blocked else 'disabled')
        self.update_btn.configure(state='disabled' if blocked else 'normal')
        self.url_text.configure(state='disabled' if self.is_busy else 'normal')
        self.preset_combo.configure(state='disabled' if blocked else 'readonly')
        self.codec_combo.configure(state='disabled' if blocked or self.preset_var.get().startswith('오디오만') else 'readonly')
        for button, page in self.nav_buttons:
            button.configure(style='Selected.Nav.TButton' if self.notebook.select() == str(page) else 'Nav.TButton')
        for widget in self.option_controls + [self.folder_change_btn]:
            widget.configure(state='disabled' if blocked else 'normal')
        detail = self.notebook.select() == str(self.detail_page)
        self.download_btn.configure(text='선택한 포맷 받기' if detail else (f'{count}개 영상 다운로드' if count > 1 else '다운로드 시작'))

    def _toggle_advanced(self):
        self.adv_visible = not self.adv_visible
        if self.adv_visible:
            self.adv_container.pack(fill='both', expand=True)
        else:
            self.adv_container.pack_forget()
            self.tree.selection_remove(self.tree.selection())
        self.adv_toggle_btn.configure(text='개별 포맷 접기' if self.adv_visible else '영상·오디오 따로 선택')

    def _exclusive_selection(self, selected, other):
        if selected.selection() and other.selection():
            other.selection_remove(other.selection())

    def _install_wheel_bindings(self):
        tag = 'YGTScroll'
        self.bind_class(tag, '<MouseWheel>', self._route_wheel)
        self.bind_class(tag, '<Button-4>', self._route_wheel)
        self.bind_class(tag, '<Button-5>', self._route_wheel)
        try:
            self.bind_class(tag, '<TouchpadScroll>', self._route_touchpad)
        except tk.TclError:
            pass  # Tk 8.6 sends MouseWheel instead.
        def visit(widget):
            widget.bindtags((tag,) + tuple(t for t in widget.bindtags() if t != tag))
            for child in widget.winfo_children():
                visit(child)
        visit(self)

    def _route_wheel(self, event):
        delta = getattr(event, 'delta', 0)
        number = getattr(event, 'num', None)
        if number in (4, 5):
            steps = -3 if number == 4 else 3
        elif delta:
            units = -delta if sys.platform == 'darwin' else -delta / 120
            steps = int(units) or (-1 if delta > 0 else 1)
            steps = max(-8, min(8, steps))
        else:
            return 'break'
        horizontal = bool(getattr(event, 'state', 0) & 1)
        return self._route_scroll(event, steps, horizontal, precise=False)

    def _route_touchpad(self, event):
        dx, dy = self.tk.call('tk::PreciseScrollDeltas', event.delta)
        for delta, horizontal in ((dx, True), (dy, False)):
            if delta:
                pixels = -int(self.tk.call('tk::ScaleNum', delta))
                self._route_scroll(event, pixels, horizontal, precise=True)
        return 'break'

    def _route_scroll(self, event, steps, horizontal, precise=False):
        widget = event.widget
        if widget is self and hasattr(event, 'x_root') and hasattr(event, 'y_root'):
            hovered = self.winfo_containing(event.x_root, event.y_root)
            if hovered is not None and hovered.winfo_toplevel() is self:
                widget = hovered
        visited = set()
        while widget is not None:
            target = getattr(widget, '_wheel_target', widget)
            if isinstance(target, (tk.Text, ttk.Treeview, tk.Canvas)) and target not in visited:
                visited.add(target)
                view = target.xview if horizontal else target.yview
                scroll = target.xview_scroll if horizontal else target.yview_scroll
                start, end = view()
                if (steps < 0 and start > 0) or (steps > 0 and end < 0.999999):
                    self._scroll_target(target, steps, horizontal, precise)
                    return 'break'
            widget = getattr(widget, 'master', None)
        if not horizontal:
            page = self.notebook.select()
            target = self.download_page.canvas if page == str(self.download_page) else self.detail_page.canvas if page == str(self.detail_page) else self.log_text
            if target not in visited:
                self._scroll_target(target, steps, False, precise)
        return 'break'

    def _scroll_target(self, target, amount, horizontal, precise):
        axis = 'x' if horizontal else 'y'
        if isinstance(target, tk.Canvas):
            getattr(target, axis + 'view_scroll')(amount if precise else amount * 24, 'units')
        elif precise and isinstance(target, tk.Text):
            target.tk.call(target._w, axis + 'view', 'scroll', amount, 'pixels')
        elif precise and isinstance(target, ttk.Treeview) and not horizontal:
            # Treeview scrolls rows, so accumulate small trackpad deltas.
            pixels = getattr(target, '_pending_scroll_pixels', 0) + amount
            rowheight = int(ttk.Style(self).lookup('Treeview', 'rowheight') or 34)
            rows = int(pixels / rowheight)
            target._pending_scroll_pixels = pixels - rows * rowheight
            if rows:
                target.yview_scroll(rows, 'units')
        elif precise:
            start, end = getattr(target, axis + 'view')()
            size = target.winfo_width() if horizontal else target.winfo_height()
            getattr(target, axis + 'view_moveto')(start + amount * (end - start) / max(1, size))
        else:
            getattr(target, axis + 'view_scroll')(amount, 'units')

    def _codec_changed(self, event=None, save=True):
        audio = self.preset_var.get().startswith('오디오만')
        key = codec_key(self.codec_var.get())
        hints = {
            'auto': '자동으로 사용 가능한 코덱을 고릅니다 · MP4 저장',
            'h264': 'H.264만 다운로드 · MP4 저장 · 해당 코덱이 없으면 알려드려요',
            'av1': 'AV1만 다운로드 · MP4 저장 · 해당 코덱이 없으면 알려드려요',
            'vp9': 'VP9만 다운로드 · WebM 저장 · 해당 코덱이 없으면 알려드려요',
        }
        self.codec_hint.configure(text='영상 없이 오디오만 MP3로 저장합니다.' if audio else hints[key])
        self.codec_combo.configure(state='disabled' if audio else 'readonly')
        if save:
            self._save_preferences()

    def _check_updates(self):
        if self.engine_busy or self.is_busy:
            return
        self.engine_busy = True
        self.engine_label.configure(text='업데이트 확인 중…', foreground=MUTED)
        self._refresh_controls()
        def work():
            messages=[]
            def log(message):
                messages.append(message)
                self._log(message)
            try:
                path=ygt_engine.ensure_engine(log, force=True)
                result=ygt_engine._run([path, '--version'], timeout=20)
                if result.returncode:
                    raise RuntimeError(result.stderr or '엔진 실행 실패')
                fallback=any('업데이트 확인 실패' in m for m in messages)
                label=f'기존 버전 사용 · {result.stdout.strip()}' if fallback else f'최신 엔진 · {result.stdout.strip()}'
                self.engine_events.put((label, fallback))
            except Exception as exc:
                self._log(str(exc))
                self.engine_events.put(('업데이트 실패 · 다시 확인해 주세요', True))
        threading.Thread(target=work, daemon=True).start()

    def _poll_ui_state(self):
        if self._closing:
            return
        try:
            while True:
                label, warning = self.engine_events.get_nowait()
                self.engine_busy=False
                self.engine_label.configure(text=label, foreground='#EDBA70' if warning else '#81C5AD')
        except queue.Empty:
            pass
        state=(self.is_busy,self.engine_busy,tuple(self._get_urls()),self.notebook.select(),tuple(self._preview_urls))
        if state != self._last_controls:
            self._last_controls=state
            self._refresh_controls()
        self.after(150,self._poll_ui_state)

    def _preferences_path(self):
        return ygt_engine.engine_dir().parent / 'preferences.json'

    def _load_preferences(self):
        import json
        try:
            self._preferences=json.loads(self._preferences_path().read_text())
            if not isinstance(self._preferences,dict):
                self._preferences={}
        except (OSError,ValueError):
            self._preferences={}
        folder=self._preferences.get('folder')
        if isinstance(folder,str) and Path(folder).is_dir():
            self.download_dir=folder

    def _save_preferences(self):
        import json
        path=self._preferences_path()
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'quality':self.preset_var.get(),'codec':self.codec_var.get(),'folder':self.download_dir},ensure_ascii=False))
        except OSError as exc:
            self._log(f'설정 저장 실패: {exc}')

    @staticmethod
    def _display_folder(folder):
        home = str(Path.home())
        return '~' + folder[len(home):] if folder.startswith(home + os.sep) else folder

    def _open_folder(self):
        try:
            if sys.platform=='darwin':
                subprocess.Popen(['open',self.download_dir])
            elif os.name=='nt':
                os.startfile(self.download_dir)
            else:
                subprocess.Popen(['xdg-open',self.download_dir])
        except OSError as exc:
            messagebox.showerror('YGT',str(exc))

    def _copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.log_text.get('1.0','end-1c'))

    def _close_window(self):
        if self.is_busy or self.engine_busy:
            messagebox.showinfo('YGT','진행 중인 작업이 끝난 뒤 창을 닫아주세요.')
            return
        self._save_preferences()
        self._closing=True
        self.destroy()
