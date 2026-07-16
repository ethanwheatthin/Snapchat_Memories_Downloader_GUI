"""Step-based wizard UI for the Snapchat Memories Downloader.

The wizard owns navigation (step indicator, Back/Continue, slide
transitions) and the per-step screens. All processing logic stays on the
app object (SnapchatDownloaderGUI); steps read/write its tk variables and
call its existing browse_*/start_download methods.
"""

import json
import os
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk

import video_utils

# Palette — mirrors SnapchatDownloaderGUI.setup_styles()
BG = "#f4f7fb"
CARD = "#ffffff"
PRIMARY = "#2168f3"
SUCCESS = "#27ae60"
WARN = "#b07514"
ERROR = "#e74c3c"
TEXT = "#2b3440"
MUTED = "#6c757d"
CHIP_IDLE = "#dbe4f0"

SLIDE_DURATION = 0.22  # seconds
SLIDE_INTERVAL = 10    # ms between animation frames

README_URL = "https://github.com/ethanwheatthin/Snapchat_Memories_Downloader_GUI"
GUIDE_GET_DATA = README_URL + "#-how-to-get-your-snapchat-data"
GUIDE_LOCAL_FILES = README_URL + "#-processing-local-files-no-download-urls"
GUIDE_CHAT_MEDIA = README_URL + "#-processing-chat-media-merge-captions--fix-metadata"
FFMPEG_GUIDE_URL = "https://phoenixnap.com/kb/ffmpeg-windows"
VLC_DOWNLOAD_URL = "https://images.videolan.org/vlc/"


def help_link(parent, text, url, **pack_kwargs):
    """A small clickable hyperlink label on a card background."""
    link = tk.Label(parent, text=text, bg=CARD, fg=PRIMARY,
                    font=("Segoe UI", 9, "underline"), cursor="hand2")
    link.pack(anchor=tk.W, **pack_kwargs)
    link.bind("<Button-1>", lambda _e: webbrowser.open(url))
    return link


def inspect_memories_json(path):
    """Parse a memories_history.json and report what's inside.

    Returns a dict: ok, count, years (min, max) or None, has_urls, error.
    """
    result = {"ok": False, "count": 0, "years": None, "has_urls": False, "error": None}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        result["error"] = f"Could not read file: {exc}"
        return result

    items = data.get("Saved Media", []) if isinstance(data, dict) else []
    if not items:
        result["error"] = "No 'Saved Media' entries found — is this memories_history.json?"
        return result

    result["count"] = len(items)
    years = [item["Date"][:4] for item in items
             if isinstance(item.get("Date"), str) and len(item["Date"]) >= 4]
    if years:
        result["years"] = (min(years), max(years))
    for item in items:
        for url_key in ("Media Download Url", "Download Link"):
            url = item.get(url_key)
            if isinstance(url, str) and url.strip().lower().startswith("http"):
                result["has_urls"] = True
                break
        if result["has_urls"]:
            break
    result["ok"] = True
    return result


class ScrollableFrame(ttk.Frame):
    """A vertically scrollable frame.

    Mouse-wheel bindings are scoped to the pointer being over the canvas
    (bound on <Enter>, released on <Leave>) so several instances can
    coexist without stealing each other's wheel events.
    """

    def __init__(self, container, *args, **kwargs):
        super().__init__(container)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg=BG)
        self.v_scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.v_scrollbar.pack(side="right", fill="y")

        self.frame = ttk.Frame(self.canvas, *args, **kwargs)
        self._window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        self.frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))

        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _content_overflows(self):
        return self.frame.winfo_reqheight() > self.canvas.winfo_height()

    def _on_mousewheel(self, event):
        if not self._content_overflows():
            return
        try:
            if sys.platform == "darwin":
                delta = -1 * int(event.delta)
            else:
                delta = int(-1 * (event.delta / 120))
        except Exception:
            delta = 0
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def _bind_wheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda e: self._content_overflows() and self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self._content_overflows() and self.canvas.yview_scroll(1, "units"))

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")


class WizardStep(ttk.Frame):
    """Base class for wizard screens."""

    title = "Step"
    scrollable = True

    def __init__(self, parent, app, controller):
        super().__init__(parent, style="Main.TFrame")
        self.app = app
        self.controller = controller
        if self.scrollable:
            scroller = ScrollableFrame(self, style="Main.TFrame")
            scroller.pack(fill=tk.BOTH, expand=True)
            self.body = scroller.frame
        else:
            self.body = ttk.Frame(self, style="Main.TFrame")
            self.body.pack(fill=tk.BOTH, expand=True)
        self.build()

    # --- overridables -------------------------------------------------
    def build(self):
        pass

    def on_show(self):
        pass

    def is_valid(self):
        return True

    def invalid_hint(self):
        return ""

    def next_label(self):
        return "Continue  →"

    # --- helpers ------------------------------------------------------
    def card(self, pad=18, fill=tk.X, expand=False, pady=(0, 14)):
        card = ttk.Frame(self.body, style="Card.TFrame", padding=pad)
        card.pack(fill=fill, expand=expand, pady=pady)
        return card

    def heading(self, parent, text, style="Header.TLabel"):
        label = ttk.Label(parent, text=text, style=style)
        label.pack(anchor=tk.W, pady=(0, 6))
        return label

    def info(self, parent, text, style="Info.TLabel", **pack_kwargs):
        label = ttk.Label(parent, text=text, style=style,
                          wraplength=640, justify=tk.LEFT)
        label.pack(anchor=tk.W, **pack_kwargs)
        return label

    def path_row(self, parent, variable, browse_command, extra_buttons=()):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(0, 6))
        entry = ttk.Entry(row, textvariable=variable, font=("Segoe UI", 9))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(row, text="Browse...", command=browse_command,
                   style="Secondary.TButton").pack(side=tk.LEFT)
        for label, command in extra_buttons:
            ttk.Button(row, text=label, command=command,
                       style="Secondary.TButton").pack(side=tk.LEFT, padx=(8, 0))
        return row


class WizardController(ttk.Frame):
    """Owns the step indicator, content area, footer nav, and transitions."""

    def __init__(self, parent, app):
        super().__init__(parent, style="Main.TFrame")
        self.app = app
        self.steps = []
        self._indicator_cells = []
        self.current = 0
        self._shown = False
        self._animating = False

        self.indicator = ttk.Frame(self, style="Main.TFrame")
        self.indicator.pack(anchor=tk.W, pady=(0, 14))

        self.content = ttk.Frame(self, style="Main.TFrame")
        self.content.pack(fill=tk.BOTH, expand=True)

        footer = ttk.Frame(self, style="Main.TFrame")
        footer.pack(fill=tk.X, pady=(14, 0))
        self.back_btn = ttk.Button(footer, text="←  Back", style="Secondary.TButton",
                                   command=self.go_back, width=12)
        self.back_btn.pack(side=tk.LEFT)
        self.next_btn = ttk.Button(footer, text="Continue  →", style="Primary.TButton",
                                   command=self.go_next, width=16)
        self.hint_label = tk.Label(footer, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.next_btn.pack(side=tk.RIGHT)
        self.hint_label.pack(side=tk.RIGHT, padx=(0, 12))

    # --- construction ---------------------------------------------------
    def add_step(self, step_cls):
        step = step_cls(self.content, self.app, self)
        index = len(self.steps)
        self.steps.append(step)

        cell = ttk.Frame(self.indicator, style="Main.TFrame")
        cell.pack(side=tk.LEFT, padx=(0 if index == 0 else 18, 0))
        chip = tk.Label(cell, text=str(index + 1), width=2, font=("Segoe UI", 9, "bold"),
                        bg=CHIP_IDLE, fg=MUTED)
        chip.pack(side=tk.LEFT)
        name = tk.Label(cell, text=step.title, bg=BG, fg=MUTED, font=("Segoe UI", 10))
        name.pack(side=tk.LEFT, padx=(6, 0))
        for widget in (chip, name):
            widget.bind("<Button-1>", lambda _e, i=index: self._on_indicator_click(i))
        self._indicator_cells.append((chip, name))
        return step

    def start(self):
        self.show_step(0, animate=False)

    # --- navigation -------------------------------------------------------
    def _on_indicator_click(self, index):
        # Only completed (earlier) steps are clickable shortcuts.
        if index < self.current and not self._animating and not self.app.is_downloading:
            self.show_step(index)

    def go_next(self):
        if self._animating or self.current >= len(self.steps) - 1:
            return
        if not self.steps[self.current].is_valid():
            self.refresh_nav()
            return
        self.show_step(self.current + 1)

    def go_back(self):
        if self._animating or self.current == 0 or self.app.is_downloading:
            return
        self.show_step(self.current - 1)

    def show_step(self, index, animate=True):
        old = self.steps[self.current] if self._shown else None
        new = self.steps[index]
        direction = 1 if index >= self.current else -1
        self.current = index
        new.on_show()

        width = self.content.winfo_width()
        if not animate or old is None or old is new or width <= 1:
            if old is not None and old is not new:
                old.place_forget()
            new.place(in_=self.content, x=0, y=0, relwidth=1, relheight=1)
            self._shown = True
            self.refresh_nav()
            return

        self._animating = True
        self.refresh_nav()
        new.place(in_=self.content, x=direction * width, y=0, relwidth=1, relheight=1)
        new.lift()
        start = time.perf_counter()

        def tick():
            t = (time.perf_counter() - start) / SLIDE_DURATION
            if t >= 1.0:
                old.place_forget()
                new.place_configure(x=0)
                self._animating = False
                self.refresh_nav()
                return
            progress = 1 - (1 - t) ** 3  # ease-out cubic
            offset = int(progress * width)
            old.place_configure(x=-direction * offset)
            new.place_configure(x=direction * (width - offset))
            self.after(SLIDE_INTERVAL, tick)

        tick()

    # --- chrome updates ---------------------------------------------------
    def refresh_nav(self):
        step = self.steps[self.current]
        is_last = self.current == len(self.steps) - 1

        back_ok = self.current > 0 and not self._animating and not self.app.is_downloading
        self.back_btn.config(state=tk.NORMAL if back_ok else tk.DISABLED)

        if is_last:
            self.next_btn.pack_forget()
            self.hint_label.config(text="")
        else:
            if not self.next_btn.winfo_manager():
                self.next_btn.pack(side=tk.RIGHT)
            valid = step.is_valid()
            self.next_btn.config(text=step.next_label(),
                                 state=tk.NORMAL if valid and not self._animating else tk.DISABLED)
            self.hint_label.config(text="" if valid else step.invalid_hint())

        for i, (chip, name) in enumerate(self._indicator_cells):
            if i < self.current:
                chip.config(bg=SUCCESS, fg="white", text="✓")
                name.config(fg=MUTED, font=("Segoe UI", 10))
            elif i == self.current:
                chip.config(bg=PRIMARY, fg="white", text=str(i + 1))
                name.config(fg=TEXT, font=("Segoe UI", 10, "bold"))
            else:
                chip.config(bg=CHIP_IDLE, fg=MUTED, text=str(i + 1))
                name.config(fg=MUTED, font=("Segoe UI", 10))


class TaskStep(WizardStep):
    """Step 1 — pick what to process."""

    title = "Task"
    scrollable = False

    def build(self):
        self.heading(self.body, "What do you want to do?", style="PageHeader.TLabel")
        self.info(self.body, "Pick a task — you can come back and switch at any time.",
                  style="PageInfo.TLabel", pady=(0, 14))

        row = ttk.Frame(self.body, style="Main.TFrame")
        row.pack(fill=tk.X)
        row.columnconfigure(0, weight=1, uniform="taskcards")
        row.columnconfigure(1, weight=1, uniform="taskcards")

        self._cards = {}
        self._cards["memories"] = self._choice_card(
            row, 0, "🖼", "Memories",
            "Download your memories export from Snapchat, or apply metadata "
            "to memories you already downloaded.")
        self._cards["chatmedia"] = self._choice_card(
            row, 1, "💬", "Chat media",
            "Merge captions and fix timestamps for the chat_media folder "
            "of your export.")

        self._highlight(self.app.task_choice.get())
        self._build_tools_card()
        self._refresh_tools()

    def on_show(self):
        self._highlight(self.app.task_choice.get())
        self._refresh_tools()

    # --- required tools ---------------------------------------------------
    def _build_tools_card(self):
        tools_card = ttk.Frame(self.body, style="Card.TFrame", padding=18)
        tools_card.pack(fill=tk.X, pady=(14, 0))
        header = ttk.Frame(tools_card, style="Card.TFrame")
        header.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(header, text="Required tools", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Re-check", command=self._refresh_tools,
                   style="Secondary.TButton").pack(side=tk.RIGHT)
        ttk.Label(tools_card,
                  text="ffmpeg and VLC are essential — they handle video conversion to H.264 "
                       "and merging captions/stickers onto your media. ffmpeg must be available "
                       "on your system PATH; VLC just needs to be installed. If you just "
                       "installed one, restart this app so it is picked up.",
                  style="Info.TLabel", wraplength=640, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 10))
        self.tools_frame = ttk.Frame(tools_card, style="Card.TFrame")
        self.tools_frame.pack(fill=tk.X)

    def _refresh_tools(self):
        for child in self.tools_frame.winfo_children():
            child.destroy()

        ffmpeg_ok = video_utils.check_ffmpeg()
        self._tool_row("ffmpeg", ffmpeg_ok, "found on PATH", "not found on your system PATH",
                       "ffmpeg install guide", FFMPEG_GUIDE_URL)

        vlc_ok = bool(video_utils.find_vlc_executable() or video_utils.HAS_VLC)
        self._tool_row("VLC", vlc_ok, "installed", "not installed",
                       "Download VLC", VLC_DOWNLOAD_URL)

    def _tool_row(self, name, ok, ok_text, missing_text, link_text, url):
        row = ttk.Frame(self.tools_frame, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(0, 4))
        if ok:
            text, color = f"✓ {name} — {ok_text}", SUCCESS
        else:
            text, color = f"✗ {name} — {missing_text}", ERROR
        tk.Label(row, text=text, bg=CARD, fg=color, font=("Segoe UI", 9),
                 wraplength=460, justify=tk.LEFT).pack(side=tk.LEFT)
        if not ok:
            link = tk.Label(row, text=link_text, bg=CARD, fg=PRIMARY,
                            font=("Segoe UI", 9, "underline"), cursor="hand2")
            link.pack(side=tk.LEFT, padx=(10, 0))
            link.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))

    def _choice_card(self, parent, column, icon, title, desc):
        card = tk.Frame(parent, bg=CARD, highlightthickness=2,
                        highlightbackground="#e2e8f0", cursor="hand2")
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill=tk.BOTH, expand=True, padx=18, pady=16)
        icon_label = tk.Label(inner, text=icon, bg=CARD, font=("Segoe UI Emoji", 20))
        icon_label.pack(anchor=tk.W)
        title_label = tk.Label(inner, text=title, bg=CARD, fg=TEXT,
                               font=("Segoe UI", 12, "bold"))
        title_label.pack(anchor=tk.W, pady=(6, 4))
        desc_label = tk.Label(inner, text=desc, bg=CARD, fg=MUTED, font=("Segoe UI", 9),
                              wraplength=320, justify=tk.LEFT)
        desc_label.pack(anchor=tk.W)

        key = "memories" if column == 0 else "chatmedia"
        for widget in (card, inner, icon_label, title_label, desc_label):
            widget.bind("<Button-1>", lambda _e, k=key: self._select(k))
        return card

    def _highlight(self, key):
        for name, card in self._cards.items():
            card.config(highlightbackground=PRIMARY if name == key else "#e2e8f0")

    def _select(self, key):
        self.app.task_choice.set(key)
        self._highlight(key)
        self.controller.refresh_nav()

    def is_valid(self):
        return self.app.task_choice.get() in ("memories", "chatmedia")

    def invalid_hint(self):
        return "Pick a task to continue"


class SourceStep(WizardStep):
    """Step 2 — pick the export file/folder; auto-detects download vs local."""

    title = "Source"

    def build(self):
        app = self.app
        self._inspection = None
        self._inspect_token = 0
        self._inspected_path = None
        self._pending_result = None
        self._polling = False

        # --- memories pane ------------------------------------------------
        self.mem_pane = ttk.Frame(self.body, style="Main.TFrame")

        method_card = ttk.Frame(self.mem_pane, style="Card.TFrame", padding=18)
        method_card.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(method_card, text="How do you want to get your memories?",
                  style="Header.TLabel").pack(anchor=tk.W, pady=(0, 8))

        ttk.Radiobutton(method_card, text="Download from Snapchat",
                        variable=app.memories_method, value="download",
                        style="Card.TRadiobutton",
                        command=self._on_method_change).pack(anchor=tk.W)
        ttk.Label(method_card,
                  text="Fetches every memory using the download URLs inside "
                       "memories_history.json. Use this when your export includes URLs.",
                  style="Info.TLabel", wraplength=600, justify=tk.LEFT).pack(
            anchor=tk.W, padx=(24, 0), pady=(0, 8))

        ttk.Radiobutton(method_card, text="Process local files",
                        variable=app.memories_method, value="local",
                        style="Card.TRadiobutton",
                        command=self._on_method_change).pack(anchor=tk.W)
        ttk.Label(method_card,
                  text="Applies metadata to memories you already have on disk — for exports "
                       "without download URLs, or files from a previous download. Requires "
                       "the memories/ folder layout from your export.",
                  style="Info.TLabel", wraplength=600, justify=tk.LEFT).pack(
            anchor=tk.W, padx=(24, 0))
        help_link(method_card, "Guide: setting up local processing",
                  GUIDE_LOCAL_FILES, padx=(24, 0), pady=(2, 0))

        json_card = ttk.Frame(self.mem_pane, style="Card.TFrame", padding=18)
        json_card.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(json_card, text="Memories export file", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 6))
        ttk.Label(json_card, text="Select memories_history.json from your Snapchat export "
                                  "(in the export's json/ or memories/ folder).",
                  style="Info.TLabel", wraplength=640, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))
        row = ttk.Frame(json_card, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(row, textvariable=app.json_path, font=("Segoe UI", 9)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(row, text="Browse...", command=app.browse_json,
                   style="Secondary.TButton").pack(side=tk.LEFT)

        help_link(json_card, "Don't have your export yet? How to request your Snapchat data",
                  GUIDE_GET_DATA, pady=(0, 8))

        self.result_label = ttk.Label(json_card, text="", style="Info.TLabel",
                                      wraplength=640, justify=tk.LEFT)
        self.result_label.pack(anchor=tk.W)

        self.folder_card = ttk.Frame(self.mem_pane, style="Card.TFrame", padding=18)
        ttk.Label(self.folder_card, text="Local memories folder", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 6))
        folder_row = ttk.Frame(self.folder_card, style="Card.TFrame")
        folder_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(folder_row, textvariable=app.memories_path, font=("Segoe UI", 9)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(folder_row, text="Browse...", command=app.browse_memories,
                   style="Secondary.TButton").pack(side=tk.LEFT)
        app.memories_section_info = ttk.Label(
            self.folder_card,
            text="Select the memories/ folder OR a parent directory (e.g. snapchat/) "
                 "to process all exports in bulk",
            style="Info.TLabel", wraplength=640, justify=tk.LEFT)
        app.memories_section_info.pack(anchor=tk.W)
        help_link(self.folder_card, "Guide: processing local files (no download URLs)",
                  GUIDE_LOCAL_FILES, pady=(6, 0))

        # --- chat media pane ------------------------------------------------
        self.chat_pane = ttk.Frame(self.body, style="Main.TFrame")
        chat_card = ttk.Frame(self.chat_pane, style="Card.TFrame", padding=18)
        chat_card.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(chat_card, text="Chat media folder", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 6))
        ttk.Label(chat_card, text="Select the chat_media/ folder from your export — timestamps and "
                                  "senders are matched automatically from json/chat_history.json when present.",
                  style="Info.TLabel", wraplength=640, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))
        chat_row = ttk.Frame(chat_card, style="Card.TFrame")
        chat_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(chat_row, textvariable=app.chat_media_path, font=("Segoe UI", 9)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(chat_row, text="Browse...", command=app.browse_chat_media,
                   style="Secondary.TButton").pack(side=tk.LEFT)
        app.chat_media_section_info = ttk.Label(chat_card, text="", style="Info.TLabel",
                                                wraplength=640, justify=tk.LEFT)
        app.chat_media_section_info.pack(anchor=tk.W)
        help_link(chat_card, "Guide: requesting the right export and processing chat media",
                  GUIDE_CHAT_MEDIA, pady=(6, 0))

        # React to path edits (typed or browsed)
        app.json_path.trace_add("write", self._on_json_changed)
        app.memories_path.trace_add("write", lambda *_: self._refresh())
        app.chat_media_path.trace_add("write", lambda *_: self._refresh())

    # --- lifecycle ------------------------------------------------------
    def on_show(self):
        task = self.app.task_choice.get()
        self.mem_pane.pack_forget()
        self.chat_pane.pack_forget()
        if task == "chatmedia":
            self.chat_pane.pack(fill=tk.BOTH, expand=True)
        else:
            self.mem_pane.pack(fill=tk.BOTH, expand=True)
            path = self.app.json_path.get().strip()
            if path and path != self._inspected_path:
                self._start_inspection(path)
        self._sync_route()

    # --- json inspection ------------------------------------------------
    def _on_json_changed(self, *_):
        path = self.app.json_path.get().strip()
        if not path:
            self._inspection = None
            self._inspected_path = None
            self.result_label.config(text="", foreground=MUTED)
            self._sync_route()
            return
        if not os.path.isfile(path):
            self._inspection = None
            self._inspected_path = None
            self.result_label.config(text="File not found", foreground=ERROR)
            self._sync_route()
            return
        self._start_inspection(path)

    def _start_inspection(self, path):
        self._inspect_token += 1
        token = self._inspect_token
        self._inspected_path = path
        self._pending_result = None
        self.result_label.config(text="⏳ Reading export…", foreground=MUTED)

        def work():
            # Tk isn't thread-safe, so stash the result and let the
            # main-thread poller apply it.
            self._pending_result = (token, inspect_memories_json(path))

        threading.Thread(target=work, daemon=True).start()
        if not self._polling:
            self._polling = True
            self.after(50, self._poll_inspection)

    def _poll_inspection(self):
        pending = self._pending_result
        if pending is not None:
            self._pending_result = None
            token, result = pending
            if token == self._inspect_token:
                self._polling = False
                self._apply_inspection(token, result)
                return
        self.after(50, self._poll_inspection)

    def _apply_inspection(self, token, result):
        if token != self._inspect_token:
            return
        self._inspection = result
        # Auto-assist: a download can't work without URLs, so pre-select
        # local processing. The user can still switch methods themselves.
        if result["ok"] and not result["has_urls"] \
                and self.app.memories_method.get() == "download":
            self.app.memories_method.set("local")
        self._update_result_text()
        self._sync_route()

    def _update_result_text(self):
        result = self._inspection
        if result is None:
            return
        count = result["count"]
        years = result["years"]
        span = f" ({years[0]}–{years[1]})" if years and years[0] != years[1] else \
               (f" ({years[0]})" if years else "")
        method = self.app.memories_method.get()
        if result["error"]:
            self.result_label.config(text=f"⚠ {result['error']}", foreground=ERROR)
        elif not result["has_urls"]:
            self.result_label.config(
                text=f"⚠ Found {count:,} memories{span} but no download URLs — this export "
                     f"only works with local processing",
                foreground=WARN)
        elif method == "local":
            self.result_label.config(
                text=f"✓ Found {count:,} memories{span} — metadata will be applied to "
                     f"your local files",
                foreground=SUCCESS)
        else:
            self.result_label.config(
                text=f"✓ Found {count:,} memories{span} with download URLs — ready to download",
                foreground=SUCCESS)

    # --- routing ----------------------------------------------------------
    def _on_method_change(self):
        self._update_result_text()
        self._sync_route()

    def _sync_route(self):
        app = self.app
        task = app.task_choice.get()

        if task == "chatmedia":
            app.mode.set("chatmedia")
        elif app.memories_method.get() == "local":
            app.mode.set("local")
        else:
            app.mode.set("download")

        # Local processing needs the memories folder card
        if task == "memories" and app.mode.get() == "local":
            if not self.folder_card.winfo_manager():
                self.folder_card.pack(fill=tk.X, pady=(0, 14))
        else:
            self.folder_card.pack_forget()

        self._refresh()

    def _refresh(self):
        self.controller.refresh_nav()

    # --- validation -------------------------------------------------------
    def is_valid(self):
        app = self.app
        if app.task_choice.get() == "chatmedia":
            return os.path.isdir(app.chat_media_path.get().strip())
        res = self._inspection
        if not (res and res["ok"]):
            return False
        if app.memories_method.get() == "local":
            return os.path.isdir(app.memories_path.get().strip())
        return res["has_urls"]

    def invalid_hint(self):
        app = self.app
        if app.task_choice.get() == "chatmedia":
            return "Select your chat_media folder"
        res = self._inspection
        if not (res and res["ok"]):
            return "Select a valid memories_history.json"
        if app.memories_method.get() == "local":
            return "Select your local memories folder"
        return "This export has no download URLs — choose 'Process local files'"


class OptionsStep(WizardStep):
    """Step 3 — output location, caption handling, advanced options."""

    title = "Options"

    def build(self):
        app = self.app

        out_card = self.card()
        self.heading(out_card, "Save location")
        self.path_row(out_card, app.output_path, app.browse_output,
                      extra_buttons=[("Open", app.open_output_dir),
                                     ("Open Log", app.open_debug_log)])
        self.info(out_card, "Processed files are written here, organized by year.")

        overlay_card = self.card()
        self.heading(overlay_card, "Captions and stickers")
        for value, text in (
            ("merge", "With overlay only — merge captions/stickers onto media"),
            ("original", "Original only — save photo/video without overlay"),
            ("both", "Both versions — save original AND overlay in the same folder"),
        ):
            ttk.Radiobutton(overlay_card, text=text, variable=app.overlay_mode,
                            value=value, style="Card.TRadiobutton").pack(anchor=tk.W, pady=(0, 4))

        adv_card = self.card()
        self._adv_open = False
        self.adv_toggle = tk.Label(adv_card, text="▸  Advanced options", bg=CARD, fg=PRIMARY,
                                   font=("Segoe UI", 10, "bold"), cursor="hand2")
        self.adv_toggle.pack(anchor=tk.W)
        self.adv_toggle.bind("<Button-1>", lambda _e: self._toggle_advanced())
        self.adv_frame = ttk.Frame(adv_card, style="Card.TFrame")

        # download-only rows
        self.retries_row = ttk.Frame(self.adv_frame, style="Card.TFrame")
        ttk.Label(self.retries_row, text="Download retries:", style="Status.TLabel").pack(side=tk.LEFT)
        tk.Spinbox(self.retries_row, from_=1, to=10, width=5,
                   textvariable=app.max_retries).pack(side=tk.LEFT, padx=(8, 16))
        ttk.Label(self.retries_row, text="Concurrent downloads:", style="Status.TLabel").pack(side=tk.LEFT)
        tk.Spinbox(self.retries_row, from_=1, to=16, width=5,
                   textvariable=app.max_threads).pack(side=tk.LEFT, padx=(8, 0))

        self.resume_check = ttk.Checkbutton(
            self.adv_frame, text="Skip existing files (resume an interrupted download)",
            variable=app.skip_existing, style="Card.TCheckbutton",
            command=self._toggle_reconvert)
        self.reconvert_check = ttk.Checkbutton(
            self.adv_frame, text="Re-convert existing videos to H.264 if needed",
            variable=app.reconvert_videos, style="Card.TCheckbutton")

        # local/chatmedia row
        self.skip_local_check = ttk.Checkbutton(
            self.adv_frame, text="Skip already-processed files in the output folder",
            variable=app.skip_existing_local, style="Card.TCheckbutton")

        # all routes
        self.gps_check = ttk.Checkbutton(
            self.adv_frame, text="Use GPS coordinates to determine local timezone (recommended)",
            variable=app.use_gps_tz, style="Card.TCheckbutton")

        self._build_tools_row()

    def _build_tools_row(self):
        tools_card = self.card(pad=12, pady=(0, 0))
        ffmpeg_ok = video_utils.check_ffmpeg()
        vlc_ok = bool(video_utils.find_vlc_executable() or video_utils.HAS_VLC)

        row = ttk.Frame(tools_card, style="Card.TFrame")
        row.pack(fill=tk.X)
        if ffmpeg_ok and vlc_ok:
            ttk.Label(row, text="✓ ffmpeg and VLC detected — videos are converted to H.264 and "
                                "captions can be merged automatically",
                      style="Info.TLabel", wraplength=640, justify=tk.LEFT).pack(side=tk.LEFT)
        else:
            missing = []
            if not ffmpeg_ok:
                missing.append(("ffmpeg", FFMPEG_GUIDE_URL))
            if not vlc_ok:
                missing.append(("VLC", VLC_DOWNLOAD_URL))
            names = " and ".join(name for name, _ in missing)
            ttk.Label(row, text=f"⚠ {names} not found — caption merging and H.264 conversion "
                                f"may be unavailable.",
                      style="Info.TLabel", wraplength=460, justify=tk.LEFT).pack(side=tk.LEFT)
            for name, url in missing:
                link = tk.Label(row, text=f"Download {name}", bg=CARD, fg=PRIMARY,
                                font=("Segoe UI", 9, "underline"), cursor="hand2")
                link.pack(side=tk.LEFT, padx=(10, 0))
                link.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))

    def _toggle_advanced(self):
        self._adv_open = not self._adv_open
        if self._adv_open:
            self.adv_toggle.config(text="▾  Advanced options")
            self.adv_frame.pack(fill=tk.X, pady=(10, 0))
            self._layout_advanced()
        else:
            self.adv_toggle.config(text="▸  Advanced options")
            self.adv_frame.pack_forget()

    def _layout_advanced(self):
        mode = self.app.mode.get()
        for widget in (self.retries_row, self.resume_check, self.reconvert_check,
                       self.skip_local_check, self.gps_check):
            widget.pack_forget()
        if mode == "download":
            self.retries_row.pack(anchor=tk.W, pady=(0, 8))
            self.resume_check.pack(anchor=tk.W, pady=(0, 4))
            self._toggle_reconvert()
        else:
            self.skip_local_check.pack(anchor=tk.W, pady=(0, 4))
        self.gps_check.pack(anchor=tk.W, pady=(4, 0))

    def _toggle_reconvert(self):
        if self.app.skip_existing.get() and self.app.mode.get() == "download":
            self.reconvert_check.pack(anchor=tk.W, padx=(24, 0), pady=(0, 4),
                                      after=self.resume_check)
        else:
            self.reconvert_check.pack_forget()
            self.app.reconvert_videos.set(False)

    def on_show(self):
        if self._adv_open:
            self._layout_advanced()

    def next_label(self):
        return "Review  →"


class RunStep(WizardStep):
    """Step 4 — review the plan, start it, watch progress."""

    title = "Run"
    scrollable = False

    MODE_LABELS = {
        "download": ("Download from Snapchat", "Start Download"),
        "local": ("Process local memories files", "Process Local Files"),
        "chatmedia": ("Process chat media", "Process Chat Media"),
    }
    OVERLAY_LABELS = {
        "merge": "Merge captions onto media",
        "original": "Original only (no overlay)",
        "both": "Both versions (original + overlay)",
    }

    def build(self):
        app = self.app

        summary_card = self.card()
        self.heading(summary_card, "Ready to go")
        self.summary_frame = ttk.Frame(summary_card, style="Card.TFrame")
        self.summary_frame.pack(fill=tk.X, pady=(2, 0))

        run_card = self.card(fill=tk.BOTH, expand=True, pady=(0, 0))
        controls = ttk.Frame(run_card, style="Card.TFrame")
        controls.pack(fill=tk.X, pady=(0, 12))
        app.download_btn = ttk.Button(controls, text="Start Download",
                                      command=self._start, style="Primary.TButton")
        app.download_btn.pack(side=tk.LEFT, padx=(0, 10))
        app.stop_btn = ttk.Button(controls, text="⏹ Stop", command=app.stop_download_func,
                                  style="Stop.TButton", state=tk.DISABLED)
        app.stop_btn.pack(side=tk.LEFT)

        app.progress_bar = ttk.Progressbar(run_card, style="Custom.Horizontal.TProgressbar",
                                           mode="determinate")
        app.progress_bar.pack(fill=tk.X, pady=(0, 8))
        app.status_label = ttk.Label(run_card, text="Ready", style="Status.TLabel")
        app.status_label.pack(anchor=tk.W, pady=(0, 8))

        log_frame = ttk.Frame(run_card, style="Card.TFrame")
        log_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        app.log_text = tk.Text(log_frame, wrap=tk.WORD, font=("Consolas", 9),
                               bg="#f8f9fa", fg="#2f3542", relief=tk.FLAT,
                               yscrollcommand=scrollbar.set, height=10)
        app.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=app.log_text.yview)

    def _start(self):
        self.app.start_download()
        self.controller.refresh_nav()

    def _summary_rows(self):
        app = self.app
        mode = app.mode.get()
        task_label = self.MODE_LABELS.get(mode, (mode, "Start"))[0]
        rows = [("Task", task_label)]
        if mode == "chatmedia":
            rows.append(("Chat media folder", app.chat_media_path.get() or "—"))
        else:
            rows.append(("Export file", app.json_path.get() or "—"))
            if mode == "local":
                rows.append(("Memories folder", app.memories_path.get() or "—"))
        rows.append(("Save to", app.output_path.get() or "—"))
        rows.append(("Captions", self.OVERLAY_LABELS.get(app.overlay_mode.get(),
                                                         app.overlay_mode.get())))
        extras = []
        if mode == "download":
            extras.append(f"{app.max_threads.get()} concurrent, {app.max_retries.get()} retries")
            if app.skip_existing.get():
                extras.append("resume mode")
        elif app.skip_existing_local.get():
            extras.append("skip already-processed")
        extras.append("GPS timezone" if app.use_gps_tz.get() else "system timezone")
        rows.append(("Settings", ", ".join(extras)))
        return rows

    def on_show(self):
        for child in self.summary_frame.winfo_children():
            child.destroy()
        for r, (key, value) in enumerate(self._summary_rows()):
            ttk.Label(self.summary_frame, text=key, style="Info.TLabel").grid(
                row=r, column=0, sticky="w", padx=(0, 18), pady=1)
            ttk.Label(self.summary_frame, text=value, style="Status.TLabel",
                      wraplength=520, justify=tk.LEFT).grid(row=r, column=1, sticky="w", pady=1)
        if not self.app.is_downloading:
            mode = self.app.mode.get()
            self.app.download_btn.config(text=self.MODE_LABELS.get(mode, ("", "Start"))[1])
            self.app.status_label.config(text="Ready", foreground=TEXT)
