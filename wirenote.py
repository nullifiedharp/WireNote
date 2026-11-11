#!/usr/bin/env python3
"""
WireNote — quick measurement annotator for wiring diagrams.

Right-click an image -> "Annotate", click next to a wire or pin, type the
expected/actual voltage, voltage drop and resistance, and the readings are
stamped onto the diagram where you clicked. Draw arrows to point at traces,
connectors and pins. Save, copy or print the result.

Copyright (C) 2026 NullHarp
Licensed under the GNU General Public License v3.0 — see LICENSE.
"""

import base64
import copy
import csv
import io
import json
import math
import os
import sys
import tempfile
import time
import webbrowser
import html as html_lib

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageDraw, ImageFont, ImageTk

APP_NAME = "WireNote"
APP_VERSION = "1.0.0"
APP_ID = "NullHarp.WireNote"
SIDE_EXT = ".wirenote.json"
REG_VERB = "WireNote.Annotate"
OPEN_TYPES = [("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"), ("All files", "*.*")]

# ── Theme ─────────────────────────────────────────────────────────────
BG = "#0f1012"
BAR = "#17181b"
BAR2 = "#1e2024"
BORDER = "#2b2e34"
FG = "#e7e7e7"
MUTED = "#9096a0"
DIM = "#5d626b"
ACCENT = "#5aa9f0"
UI_FONT = ("Segoe UI", 9) if sys.platform == "win32" else ("DejaVu Sans", 9)
MONO = ("Consolas", 9) if sys.platform == "win32" else ("DejaVu Sans Mono", 9)

ARROW_COLORS = ["#ffffff", "#f87171", "#4ade80", "#fbbf24", "#5aa9f0", "#c084fc", "#111111"]

# Label styles: dark boxes read best on screen, light boxes save ink on paper
LABEL_STYLES = {
    "dark": {"box": "#0c0d0f", "edge_none": "#4a4f57", "head": "#e5e5e5", "none": "#b4b9c0",
             "pass": "#4ade80", "fail": "#f87171", "warn": "#fbbf24", "leader": "#d0d0d0"},
    "light": {"box": "#ffffff", "edge_none": "#9aa0a6", "head": "#111111", "none": "#333333",
              "pass": "#15803d", "fail": "#c81e1e", "warn": "#b45309", "leader": "#333333"},
}

DEFAULT_SETTINGS = {
    "text_pt": 9,
    "tolerance": 10,
    "label_style": "dark",
    "wheel": "zoom",          # zoom | scroll
    "arrow_color": "#f87171",
    "recent_labels": [],
    "last_dir": "",
    "geometry": "",
    "zoomed": True,
}


# ═════════════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════════════
def settings_file():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_file(), "r", encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        with open(settings_file(), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


def num(v):
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def check(kind, exp, act, tol_pct):
    """pass / fail / none for one measurement pair.
    V  : actual within ±tol% of expected
    Vd : expected is a maximum — pass when actual <= expected
    Ω  : within ±tol%, with a 0.5 Ω allowance so near-zero specs work
    """
    e, a = num(exp), num(act)
    if e is None or a is None:
        return "none"
    if kind == "vd":
        return "pass" if a <= e + 1e-9 else "fail"
    floor = 0.5 if kind == "r" else 0.0
    return "pass" if abs(a - e) <= max(abs(e) * tol_pct / 100.0, floor) else "fail"


def overall(ann, tol):
    states = [check("v", ann.get("v_exp"), ann.get("v_act"), tol),
              check("vd", ann.get("vd_exp"), ann.get("vd_act"), tol),
              check("r", ann.get("r_exp"), ann.get("r_act"), tol)]
    states = [s for s in states if s != "none"]
    if not states:
        return "none"
    if "fail" in states:
        return "fail"
    return "pass" if all(s == "pass" for s in states) else "warn"


def label_lines(ann, tol):
    """[(text, state, bold)] for an annotation box."""
    out = []
    if ann.get("label", "").strip():
        out.append((ann["label"].strip(), "head", True))
    for key, sym, kind, dp in (("v", "V", "v", 2), ("vd", "Vd", "vd", 2), ("r", "Ω", "r", 1)):
        e, a = ann.get(key + "_exp", "").strip(), ann.get(key + "_act", "").strip()
        if not e and not a:
            continue
        diff = ""
        if num(e) is not None and num(a) is not None:
            d = num(a) - num(e)
            diff = f"  ({'+' if d > 0 else ''}{d:.{dp}f})"
        st = check(kind, e, a, tol)
        out.append((f"{sym}: {a or '?'} / {e or '?'}{diff}", st if st != "none" else "none", False))
    return out


def resource_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def make_icon_image(size=256):
    """Draws the app icon (also used by build.bat via --make-icon)."""
    S = 512
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((16, 16, S - 16, S - 16), radius=96, fill=(22, 24, 28, 255), outline=(58, 62, 70, 255), width=8)
    # wires
    d.line([(40, 170), (200, 170), (260, 250), (472, 250)], fill=(248, 113, 113, 255), width=26, joint="curve")
    d.line([(40, 330), (220, 330), (280, 380), (472, 380)], fill=(90, 169, 240, 255), width=26, joint="curve")
    # pin ring
    d.ellipse((222, 214, 298, 290), outline=(251, 191, 36, 255), width=16)
    # measurement tag + leader
    d.line([(298, 230), (350, 150)], fill=(230, 230, 230, 255), width=10)
    d.rounded_rectangle((330, 70, 480, 160), radius=16, fill=(245, 245, 245, 255))
    d.line([(352, 100), (456, 100)], fill=(21, 128, 61, 255), width=14)
    d.line([(352, 130), (420, 130)], fill=(60, 60, 60, 255), width=12)
    return im.resize((size, size), Image.LANCZOS)


def write_icons(folder):
    os.makedirs(folder, exist_ok=True)
    big = make_icon_image(256)
    big.save(os.path.join(folder, "icon.png"))
    big.save(os.path.join(folder, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Icons written to", folder)


def load_pil_font(px, bold=False):
    px = max(4, int(round(px)))
    names = (["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"] if bold
             else ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, px)
        except OSError:
            continue
    for n in (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(n, px)
        except OSError:
            pass
    return ImageFont.load_default()


# ── Windows integration ───────────────────────────────────────────────
def launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{os.path.abspath(__file__)}" "%1"'


def icon_value():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}",0'
    ico = os.path.join(resource_dir(), "assets", "icon.ico")
    return f'"{ico}"' if os.path.exists(ico) else ""


def register_context_menu():
    import winreg
    key = rf"Software\Classes\SystemFileAssociations\image\shell\{REG_VERB}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Annotate")
        iv = icon_value()
        if iv:
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, iv)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, launch_command())


def unregister_context_menu():
    import winreg
    key = rf"Software\Classes\SystemFileAssociations\image\shell\{REG_VERB}"
    for sub in (key + r"\command", key):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except FileNotFoundError:
            pass


def copy_image_to_clipboard(img):
    """Puts a PIL image on the Windows clipboard as CF_DIB."""
    import ctypes
    from ctypes import wintypes
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    data = buf.getvalue()[14:]  # strip BITMAPFILEHEADER
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k32.GlobalFree.argtypes = [ctypes.c_void_p]
    u32.OpenClipboard.argtypes = [ctypes.c_void_p]
    u32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    u32.SetClipboardData.restype = ctypes.c_void_p
    for _ in range(10):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Clipboard is busy")
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(0x0002, len(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        if not u32.SetClipboardData(8, h):
            k32.GlobalFree(h)
            raise RuntimeError("SetClipboardData failed")
    finally:
        u32.CloseClipboard()


# ═════════════════════════════════════════════════════════════════════
#  App
# ═════════════════════════════════════════════════════════════════════
class WireNote:
    def __init__(self, root, path=None):
        self.root = root
        self.cfg = load_settings()
        self.px_per_pt = float(root.tk.call("tk", "scaling"))

        # document
        self.img = None
        self.src_path = None
        self.out_path = None
        self.anns, self.arrows = [], []
        self.unit = 1.0                   # image px per screen px at fit-width when doc was made
        self.text_pt = self.cfg["text_pt"]
        self.dirty = False
        self.undo_stack, self.redo_stack = [], []
        self.next_id = 1

        # view
        self.scale, self.pan_x, self.pan_y = 1.0, 0.0, 0.0
        self.auto_fit = True
        self.tool = "annotate"
        self.sel = None                   # ("ann"|"arrow", id)
        self.drag = None
        self.space = False
        self.geom = {}
        self._photo = None
        self._view_key = None
        self._hq_job = None
        self._fonts = {}
        self.form_ctx = None

        self._build_style()
        self._build_ui()
        self._bind_keys()
        self.set_tool("annotate")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if path:
            self.root.after(60, lambda: self.open_path(path))
        else:
            self.redraw()

    # ── UI construction ───────────────────────────────────────────────
    def _build_style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure(".", background=BAR, foreground=FG, fieldbackground=BAR2, bordercolor=BORDER,
                     lightcolor=BORDER, darkcolor=BORDER, troughcolor=BG, font=UI_FONT)
        st.configure("TCombobox", fieldbackground="#121316", background=BAR2, foreground=FG, arrowcolor=MUTED,
                     selectbackground="#121316", selectforeground=FG, padding=2)
        st.map("TCombobox", fieldbackground=[("readonly", "#121316")])
        st.configure("Vertical.TScrollbar", background=BAR2, troughcolor=BG, arrowcolor=MUTED, bordercolor=BG)
        st.configure("Horizontal.TScrollbar", background=BAR2, troughcolor=BG, arrowcolor=MUTED, bordercolor=BG)
        st.map("TScrollbar", background=[("active", "#33363d")])
        st.configure("Treeview", background="#121316", fieldbackground="#121316", foreground=FG, rowheight=22,
                     bordercolor=BORDER)
        st.configure("Treeview.Heading", background=BAR2, foreground=MUTED, relief="flat")
        st.map("Treeview", background=[("selected", "#253447")])
        st.configure("TSpinbox", fieldbackground="#121316", foreground=FG, arrowcolor=MUTED, background=BAR2)
        self.root.option_add("*TCombobox*Listbox.background", "#121316")
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#253447")
        self.root.option_add("*Menu.background", BAR2)
        self.root.option_add("*Menu.foreground", FG)
        self.root.option_add("*Menu.activeBackground", "#253447")
        self.root.option_add("*Menu.activeForeground", FG)

    def _btn(self, parent, text, cmd, tip=None, width=None):
        b = tk.Button(parent, text=text, command=cmd, bg=BAR, fg="#c9cdd3", activebackground="#262930",
                      activeforeground=FG, relief="flat", bd=0, padx=9, pady=4, font=UI_FONT,
                      highlightthickness=1, highlightbackground=BORDER, cursor="hand2")
        if width:
            b.configure(width=width)
        b.bind("<Enter>", lambda e: b.configure(bg="#23262c") if b.cget("bg") == BAR else None)
        b.bind("<Leave>", lambda e: b.configure(bg=BAR) if b.cget("bg") == "#23262c" else None)
        if tip:
            self._tip(b, tip)
        return b

    def _sep(self, parent):
        tk.Frame(parent, width=1, bg=BORDER).pack(side="left", fill="y", padx=6, pady=3)

    def _tip(self, widget, text):
        def show(_):
            self.status_hint.configure(text=text)
        def hide(_):
            self.status_hint.configure(text=self._hint_text())
        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")

    def _build_ui(self):
        r = self.root
        r.title(APP_NAME)
        r.configure(bg=BG)
        r.minsize(760, 420)
        try:
            self._icon_photo = ImageTk.PhotoImage(make_icon_image(64))
            r.iconphoto(True, self._icon_photo)
        except Exception:
            pass
        if self.cfg.get("geometry"):
            try:
                r.geometry(self.cfg["geometry"])
            except tk.TclError:
                pass
        else:
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            r.geometry(f"{int(sw * .8)}x{int(sh * .8)}+{int(sw * .1)}+{int(sh * .08)}")
        if self.cfg.get("zoomed", True) and sys.platform == "win32":
            r.state("zoomed")

        # ── toolbar
        tb = tk.Frame(r, bg=BAR, highlightthickness=0)
        tb.pack(side="top", fill="x")
        inner = tk.Frame(tb, bg=BAR)
        inner.pack(side="top", fill="x", padx=6, pady=5)

        self._btn(inner, "📂 Open", self.open_dialog, "Open a diagram (Ctrl+O) · Ctrl+V pastes a screenshot").pack(side="left")
        self._sep(inner)

        self.tool_btns = {}
        for key, text, tip in (("annotate", "✚ Annotate", "Click next to a wire/pin to add a reading (A)"),
                               ("arrow", "➚ Arrow", "Drag to draw an indicator arrow (W)"),
                               ("select", "↖ Select", "Select, move, edit, delete (S)")):
            b = self._btn(inner, text, lambda k=key: self.set_tool(k), tip)
            b.pack(side="left", padx=(0, 3))
            self.tool_btns[key] = b
        self._sep(inner)

        tk.Label(inner, text="Arrow", bg=BAR, fg=DIM, font=UI_FONT).pack(side="left", padx=(0, 4))
        self.swatches = {}
        for c in ARROW_COLORS:
            sw = tk.Frame(inner, width=18, height=18, bg=c, highlightthickness=2, highlightbackground=BAR, cursor="hand2")
            sw.pack(side="left", padx=2)
            sw.bind("<Button-1>", lambda e, c=c: self.set_arrow_color(c))
            self.swatches[c] = sw
        self._sep(inner)

        tk.Label(inner, text="Text", bg=BAR, fg=DIM, font=UI_FONT).pack(side="left", padx=(0, 4))
        self.text_var = tk.StringVar(value=str(self.text_pt))
        sp = ttk.Spinbox(inner, from_=6, to=28, width=3, textvariable=self.text_var, command=self.on_text_size,
                         font=UI_FONT)
        sp.pack(side="left")
        sp.bind("<Return>", lambda e: self.on_text_size())
        sp.bind("<FocusOut>", lambda e: self.on_text_size())
        tk.Label(inner, text="pt", bg=BAR, fg=DIM, font=UI_FONT).pack(side="left", padx=(2, 0))
        self._sep(inner)

        self._btn(inner, "−", lambda: self.zoom_center(1 / 1.2), "Zoom out (-)").pack(side="left")
        self.zoom_lbl = tk.Label(inner, text="—", bg=BAR, fg=ACCENT, font=MONO, width=6, cursor="hand2")
        self.zoom_lbl.pack(side="left")
        self.zoom_lbl.bind("<Button-1>", lambda e: self.fit_width())
        self._btn(inner, "+", lambda: self.zoom_center(1.2), "Zoom in (+)").pack(side="left")
        self._btn(inner, "↔ Fit", self.fit_width, "Fit to window width (0)").pack(side="left", padx=(4, 0))
        self._btn(inner, "⛶ Whole", self.fit_whole, "Show the whole diagram (Shift+0)").pack(side="left", padx=(3, 0))

        # right side
        more = tk.Menubutton(inner, text="☰", bg=BAR, fg="#c9cdd3", activebackground="#262930", activeforeground=FG,
                             relief="flat", bd=0, padx=10, pady=4, font=UI_FONT, highlightthickness=1,
                             highlightbackground=BORDER, cursor="hand2")
        more.pack(side="right")
        self._build_menu(more)
        self._btn(inner, "💾 Save", self.save, "Save annotated image (Ctrl+S)").pack(side="right", padx=(3, 3))
        self._btn(inner, "🖨 Print", self.print_report, "Print diagram + measurement table (Ctrl+P)").pack(side="right", padx=(3, 0))
        self._btn(inner, "📋 Copy", self.copy_image, "Copy annotated image to clipboard (Ctrl+C)").pack(side="right", padx=(3, 0))
        self._btn(inner, "📊 Summary", self.show_summary, "Table of all readings (T)").pack(side="right", padx=(3, 0))
        self._sep_right(inner)
        self._btn(inner, "↷", self.redo, "Redo (Ctrl+Y)").pack(side="right", padx=(3, 0))
        self._btn(inner, "↶", self.undo, "Undo (Ctrl+Z)").pack(side="right", padx=(3, 0))
        tk.Frame(tb, height=1, bg=BORDER).pack(side="bottom", fill="x")

        # ── status bar
        sb = tk.Frame(r, bg=BAR)
        sb.pack(side="bottom", fill="x")
        tk.Frame(sb, height=1, bg=BORDER).pack(side="top", fill="x")
        self.status_hint = tk.Label(sb, text="", bg=BAR, fg=MUTED, font=UI_FONT, anchor="w")
        self.status_hint.pack(side="left", padx=10, pady=3)
        self.status_info = tk.Label(sb, text="", bg=BAR, fg=DIM, font=MONO, anchor="e")
        self.status_info.pack(side="right", padx=10)
        self.status_counts = tk.Label(sb, text="", bg=BAR, fg=MUTED, font=UI_FONT)
        self.status_counts.pack(side="right", padx=10)

        # ── workspace
        ws = tk.Frame(r, bg=BG)
        ws.pack(side="top", fill="both", expand=True)
        ws.grid_rowconfigure(0, weight=1)
        ws.grid_columnconfigure(0, weight=1)
        self.cv = tk.Canvas(ws, bg=BG, highlightthickness=0, bd=0)
        self.cv.grid(row=0, column=0, sticky="nsew")
        self.vbar = ttk.Scrollbar(ws, orient="vertical", command=self.on_vscroll)
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar = ttk.Scrollbar(ws, orient="horizontal", command=self.on_hscroll)
        self.hbar.grid(row=1, column=0, sticky="ew")

        self.cv.bind("<Configure>", self.on_resize)
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_motion_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Double-Button-1>", self.on_double)
        self.cv.bind("<Motion>", self.on_hover)
        for b in ("2", "3"):
            self.cv.bind(f"<ButtonPress-{b}>", self.on_pan_press)
            self.cv.bind(f"<B{b}-Motion>", self.on_pan_motion)
            self.cv.bind(f"<ButtonRelease-{b}>", lambda e, b=b: self.on_pan_release(e, b))
        self.cv.bind("<MouseWheel>", self.on_wheel)
        self.cv.bind("<Button-4>", lambda e: self.on_wheel(e, 120))
        self.cv.bind("<Button-5>", lambda e: self.on_wheel(e, -120))

        self._build_form()
        self.toast_lbl = tk.Label(self.cv, text="", bg="#1f6f43", fg="#eafff2", font=(UI_FONT[0], 10, "bold"),
                                  padx=14, pady=5)
        self._toast_job = None

    def _sep_right(self, parent):
        tk.Frame(parent, width=1, bg=BORDER).pack(side="right", fill="y", padx=6, pady=3)

    def _build_menu(self, mb):
        m = tk.Menu(mb, tearoff=0, bd=0, font=UI_FONT)
        mb["menu"] = m
        m.add_command(label="Open image…", accelerator="Ctrl+O", command=self.open_dialog)
        m.add_command(label="Paste screenshot", accelerator="Ctrl+V", command=self.paste_image)
        m.add_separator()
        m.add_command(label="Save annotated image", accelerator="Ctrl+S", command=self.save)
        m.add_command(label="Save as… (PNG / JPG / PDF)", accelerator="Ctrl+Shift+S", command=lambda: self.save(ask=True))
        m.add_command(label="Export readings CSV / table", accelerator="T", command=self.show_summary)
        m.add_command(label="Print report (image + table)", accelerator="Ctrl+P", command=self.print_report)
        m.add_command(label="Print image only", command=self.print_image_only)
        m.add_separator()
        self.style_var = tk.StringVar(value=self.cfg["label_style"])
        sm = tk.Menu(m, tearoff=0)
        sm.add_radiobutton(label="Dark labels (screen)", variable=self.style_var, value="dark", command=self.on_style)
        sm.add_radiobutton(label="Light labels (print-friendly)", variable=self.style_var, value="light", command=self.on_style)
        m.add_cascade(label="Label style", menu=sm)
        self.wheel_var = tk.StringVar(value=self.cfg["wheel"])
        wm = tk.Menu(m, tearoff=0)
        wm.add_radiobutton(label="Wheel zooms (Shift = side-scroll)", variable=self.wheel_var, value="zoom", command=self.on_wheel_mode)
        wm.add_radiobutton(label="Wheel scrolls (Ctrl = zoom)", variable=self.wheel_var, value="scroll", command=self.on_wheel_mode)
        m.add_cascade(label="Mouse wheel", menu=wm)
        m.add_command(label="Pass/fail tolerance…", command=self.ask_tolerance)
        m.add_separator()
        if sys.platform == "win32":
            m.add_command(label="Add “Annotate” to right-click menu", command=self.do_register)
            m.add_command(label="Remove “Annotate” from right-click menu", command=self.do_unregister)
            m.add_separator()
        m.add_command(label="Clear all annotations", command=self.clear_all)
        m.add_command(label="Shortcuts & help", command=self.show_help)
        m.add_command(label=f"About {APP_NAME}", command=self.show_about)

    def _build_form(self):
        f = tk.Frame(self.cv, bg="#1b1d21", highlightthickness=1, highlightbackground="#3a3e46")
        self.form = f
        hdr = tk.Frame(f, bg="#1b1d21")
        hdr.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(6, 4))
        self.form_title = tk.Label(hdr, text="ADD READING", bg="#1b1d21", fg=MUTED, font=(UI_FONT[0], 8, "bold"))
        self.form_title.pack(side="left")
        x = tk.Label(hdr, text="✕", bg="#1b1d21", fg=DIM, font=UI_FONT, cursor="hand2")
        x.pack(side="right")
        x.bind("<Button-1>", lambda e: self.close_form())

        self.f_label = ttk.Combobox(f, width=30, font=UI_FONT)
        self.f_label.grid(row=1, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 6))

        tk.Label(f, text="Expected", bg="#1b1d21", fg=DIM, font=(UI_FONT[0], 8)).grid(row=2, column=1)
        tk.Label(f, text="Actual", bg="#1b1d21", fg=DIM, font=(UI_FONT[0], 8)).grid(row=2, column=2)
        self.f_fields = {}
        for i, (key, sym, hint) in enumerate((("v", "V", ""), ("vd", "Vd", "max"), ("r", "Ω", ""))):
            lab = tk.Label(f, text=sym, bg="#1b1d21", fg=MUTED, font=(MONO[0], 9, "bold"), width=3, anchor="e")
            lab.grid(row=3 + i, column=0, sticky="e", padx=(8, 4), pady=2)
            if hint:
                self._form_tip(lab, "Voltage drop: expected is the MAX allowed — passes when actual ≤ expected")
            ents = []
            for j, side in enumerate(("exp", "act")):
                e = tk.Entry(f, width=10, bg="#111215", fg=FG, insertbackground=FG, relief="flat",
                             highlightthickness=1, highlightbackground="#33363d", highlightcolor=ACCENT,
                             font=(MONO[0], 10))
                e.grid(row=3 + i, column=1 + j, padx=(0, 6 if j == 0 else 8), pady=2, ipady=2)
                e.bind("<KeyRelease>", lambda ev: self._form_live())
                self.f_fields[f"{key}_{side}"] = e
                ents.append(e)

        btns = tk.Frame(f, bg="#1b1d21")
        btns.grid(row=6, column=0, columnspan=3, sticky="ew", padx=8, pady=(8, 8))
        self.f_ok = tk.Button(btns, text="✓ Place  (Enter)", command=self.submit_form, bg="#1d3550", fg="#9fd0ff",
                              activebackground="#24466b", activeforeground="#cfe6ff", relief="flat", bd=0,
                              padx=10, pady=4, font=UI_FONT, cursor="hand2")
        self.f_ok.pack(side="left", fill="x", expand=True)
        self.f_del = tk.Button(btns, text="🗑", command=self.delete_from_form, bg="#3a1d1f", fg="#fca5a5",
                               activebackground="#55262a", activeforeground="#ffd0d0", relief="flat", bd=0,
                               padx=10, pady=4, font=UI_FONT, cursor="hand2")
        self.f_cancel = tk.Button(btns, text="Esc", command=self.close_form, bg="#25272c", fg=MUTED,
                                  activebackground="#2e3137", activeforeground=FG, relief="flat", bd=0,
                                  padx=10, pady=4, font=UI_FONT, cursor="hand2")
        self.f_cancel.pack(side="left", padx=(5, 0))

        for w in [self.f_label] + list(self.f_fields.values()):
            w.bind("<Return>", lambda e: (self.submit_form(), "break")[1])
            w.bind("<KP_Enter>", lambda e: (self.submit_form(), "break")[1])
            w.bind("<Escape>", lambda e: (self.close_form(), "break")[1])

    def _form_tip(self, w, text):
        w.bind("<Enter>", lambda e: self.status_hint.configure(text=text))
        w.bind("<Leave>", lambda e: self.status_hint.configure(text=self._hint_text()))

    def _bind_keys(self):
        r = self.root
        r.bind("<Control-o>", lambda e: self.open_dialog())
        r.bind("<Control-s>", lambda e: self.save())
        r.bind("<Control-S>", lambda e: self.save(ask=True))
        r.bind("<Control-z>", lambda e: self._unless_typing(e, self.undo))
        r.bind("<Control-y>", lambda e: self._unless_typing(e, self.redo))
        r.bind("<Control-Z>", lambda e: self._unless_typing(e, self.redo))
        r.bind("<Control-c>", lambda e: self._unless_typing(e, self.copy_image))
        r.bind("<Control-v>", lambda e: self._unless_typing(e, self.paste_image))
        r.bind("<Control-p>", lambda e: self.print_report())
        r.bind("<F11>", lambda e: r.attributes("-fullscreen", not r.attributes("-fullscreen")))
        r.bind("<KeyPress-space>", self._space_down)
        r.bind("<KeyRelease-space>", self._space_up)
        r.bind("<Key>", self.on_key)

    def _typing(self, e=None):
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, ttk.Entry, ttk.Combobox, ttk.Spinbox))

    def _unless_typing(self, e, fn):
        if self._typing():
            return None
        fn()
        return "break"

    # ── coordinates ───────────────────────────────────────────────────
    def i2s(self, x, y):
        return x * self.scale + self.pan_x, y * self.scale + self.pan_y

    def s2i(self, x, y):
        return (x - self.pan_x) / self.scale, (y - self.pan_y) / self.scale

    def on_image(self, sx, sy):
        if not self.img:
            return False
        x, y = self.s2i(sx, sy)
        return 0 <= x <= self.img.width and 0 <= y <= self.img.height

    # ── document ops ──────────────────────────────────────────────────
    def snapshot(self):
        return json.dumps({"anns": self.anns, "arrows": self.arrows, "text_pt": self.text_pt})

    def push_undo(self):
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _restore(self, snap):
        d = json.loads(snap)
        self.anns, self.arrows, self.text_pt = d["anns"], d["arrows"], d["text_pt"]
        self.text_var.set(str(self.text_pt))
        self.sel = None
        self.mark_dirty()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot())
            self._restore(self.undo_stack.pop())
            self.toast("Undo")

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot())
            self._restore(self.redo_stack.pop())
            self.toast("Redo")

    def mark_dirty(self, dirty=True):
        self.dirty = dirty
        self.update_title()
        self.draw_annotations()

    def update_title(self):
        name = os.path.basename(self.src_path) if self.src_path else ("Pasted image" if self.img else "")
        t = f"{'● ' if self.dirty else ''}{name} — {APP_NAME}" if name else APP_NAME
        self.root.title(t)

    def new_id(self):
        self.next_id += 1
        return self.next_id

    def confirm_discard(self):
        if not self.dirty or not (self.anns or self.arrows):
            return True
        r = messagebox.askyesnocancel(APP_NAME, "Save your annotations before continuing?", parent=self.root)
        if r is None:
            return False
        if r:
            return self.save()
        return True

    # ── open / paste ──────────────────────────────────────────────────
    def open_dialog(self):
        if not self.confirm_discard():
            return
        p = filedialog.askopenfilename(parent=self.root, title="Open wiring diagram", filetypes=OPEN_TYPES,
                                       initialdir=self.cfg.get("last_dir") or None)
        if p:
            self.open_path(p, confirmed=True)

    def open_path(self, path, confirmed=False):
        if not confirmed and not self.confirm_discard():
            return
        try:
            im = Image.open(path)
            im.load()
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Couldn't open that image:\n{ex}", parent=self.root)
            return
        self.cfg["last_dir"] = os.path.dirname(os.path.abspath(path))
        self._set_image(im, os.path.abspath(path))
        side = self.src_path + SIDE_EXT
        if os.path.exists(side):
            self._load_sidecar(side)

    def paste_image(self):
        try:
            from PIL import ImageGrab
            data = ImageGrab.grabclipboard()
        except Exception:
            data = None
        if isinstance(data, list) and data:
            if os.path.isfile(data[0]):
                self.open_path(data[0])
                return
        if isinstance(data, Image.Image):
            if not self.confirm_discard():
                return
            self._set_image(data, None)
            self.toast("Pasted screenshot from clipboard")
            return
        self.toast("No image on the clipboard", error=True)

    def _set_image(self, im, path):
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        self.img = im
        self.src_path = path
        self.out_path = None
        self.anns, self.arrows = [], []
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.sel = None
        self.text_pt = self.cfg["text_pt"]
        self.text_var.set(str(self.text_pt))
        self.close_form()
        self.root.update_idletasks()
        cw = max(200, self.cv.winfo_width())
        self.unit = im.width / cw
        self.fit_width()
        self.dirty = False
        self.update_title()

    def _load_sidecar(self, side):
        try:
            with open(side, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.anns = d.get("anns", [])
            self.arrows = d.get("arrows", [])
            self.unit = d.get("unit", self.unit)
            self.text_pt = d.get("text_pt", self.text_pt)
            self.text_var.set(str(self.text_pt))
            self.out_path = d.get("out_path") if d.get("out_path") and os.path.isdir(os.path.dirname(d["out_path"])) else None
            ids = [a["id"] for a in self.anns + self.arrows] or [0]
            self.next_id = max(ids) + 1
            self.draw_annotations()
            n = len(self.anns)
            self.toast(f"Restored {n} reading{'s' if n != 1 else ''} and {len(self.arrows)} arrow{'s' if len(self.arrows) != 1 else ''}")
        except Exception as ex:
            self.toast(f"Couldn't read saved annotations ({ex})", error=True)

    # ── view / zoom ───────────────────────────────────────────────────
    def fit_width(self):
        if not self.img:
            return
        cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
        self.scale = cw / self.img.width
        self.pan_x = 0
        ih = self.img.height * self.scale
        self.pan_y = (ch - ih) / 2 if ih < ch else 0
        self.auto_fit = True
        self.redraw()

    def fit_whole(self):
        if not self.img:
            return
        cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
        self.scale = min(cw / self.img.width, ch / self.img.height)
        self.pan_x = (cw - self.img.width * self.scale) / 2
        self.pan_y = (ch - self.img.height * self.scale) / 2
        self.auto_fit = False
        self.redraw()

    def zoom_at(self, sx, sy, factor):
        if not self.img:
            return
        cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
        lo = min(cw / self.img.width, ch / self.img.height) * 0.5
        ns = max(lo, min(20.0, self.scale * factor))
        f = ns / self.scale
        self.pan_x = sx - (sx - self.pan_x) * f
        self.pan_y = sy - (sy - self.pan_y) * f
        self.scale = ns
        self.auto_fit = False
        self.redraw()

    def zoom_center(self, factor):
        self.zoom_at(self.cv.winfo_width() / 2, self.cv.winfo_height() / 2, factor)

    def actual_pixels(self):
        if self.img:
            self.zoom_center(1.0 / self.scale)

    def clamp_pan(self):
        if not self.img:
            return
        cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
        iw, ih = self.img.width * self.scale, self.img.height * self.scale
        m = 60
        if iw <= cw:
            self.pan_x = (cw - iw) / 2
        else:
            self.pan_x = min(m, max(cw - iw - m, self.pan_x))
        if ih <= ch:
            self.pan_y = (ch - ih) / 2
        else:
            self.pan_y = min(m, max(ch - ih - m, self.pan_y))

    def on_resize(self, e):
        if self.img and self.auto_fit:
            self.fit_width()
        else:
            self.redraw()

    def _scroll_metrics(self, axis):
        if axis == "x":
            return self.img.width * self.scale, self.cv.winfo_width(), self.pan_x
        return self.img.height * self.scale, self.cv.winfo_height(), self.pan_y

    def _on_scroll(self, axis, *args):
        if not self.img:
            return
        total, view, pan = self._scroll_metrics(axis)
        if args[0] == "moveto":
            pan = -float(args[1]) * total
        elif args[0] == "scroll":
            step = view * 0.9 if args[2] == "pages" else 60
            pan -= int(args[1]) * step
        if axis == "x":
            self.pan_x = pan
        else:
            self.pan_y = pan
        self.auto_fit = False
        self.redraw()

    def on_vscroll(self, *a):
        self._on_scroll("y", *a)

    def on_hscroll(self, *a):
        self._on_scroll("x", *a)

    def _update_scrollbars(self):
        if not self.img:
            self.hbar.set(0, 1)
            self.vbar.set(0, 1)
            return
        for axis, bar in (("x", self.hbar), ("y", self.vbar)):
            total, view, pan = self._scroll_metrics(axis)
            if total <= view:
                bar.set(0, 1)
            else:
                first = max(0.0, -pan / total)
                bar.set(first, min(1.0, first + view / total))

    # ── rendering ─────────────────────────────────────────────────────
    def redraw(self, hq=False):
        self.clamp_pan()
        self._draw_image(hq)
        self.draw_annotations()
        self._update_scrollbars()
        if self.img:
            self.zoom_lbl.configure(text=f"{self.scale * 100:.0f}%")
            self.status_info.configure(text=f"{self.img.width}×{self.img.height}px")
        if not hq:
            if self._hq_job:
                self.root.after_cancel(self._hq_job)
            self._hq_job = self.root.after(140, lambda: self._draw_image(True))

    def _draw_image(self, hq):
        self._hq_job = None if hq else self._hq_job
        cv = self.cv
        if not self.img:
            cv.delete("all")
            self._photo = None
            w, h = cv.winfo_width(), cv.winfo_height()
            cv.create_rectangle(24, 24, w - 24, h - 24, outline="#2a2d33", dash=(6, 4), width=2, tags="empty")
            cv.create_text(w / 2, h / 2 - 34, text="⚡", fill="#3a3e46", font=(UI_FONT[0], 34), tags="empty")
            cv.create_text(w / 2, h / 2 + 10, text="Open a wiring diagram", fill=FG, font=(UI_FONT[0], 14, "bold"), tags="empty")
            cv.create_text(w / 2, h / 2 + 36, text="📂 Open (Ctrl+O)   ·   paste a screenshot (Ctrl+V)   ·   or right-click any image → Annotate",
                           fill=DIM, font=UI_FONT, tags="empty")
            cv.tag_bind("empty", "<Button-1>", lambda e: self.open_dialog())
            self.zoom_lbl.configure(text="—")
            self.status_info.configure(text="")
            return
        cv.delete("empty")
        key = (round(self.scale, 6), round(self.pan_x, 1), round(self.pan_y, 1), cv.winfo_width(), cv.winfo_height(), hq)
        if key == self._view_key:
            return
        self._view_key = key
        cw, ch = cv.winfo_width(), cv.winfo_height()
        s = self.scale
        W, H = self.img.size
        x0, y0 = max(0.0, -self.pan_x / s), max(0.0, -self.pan_y / s)
        x1, y1 = min(W, (cw - self.pan_x) / s), min(H, (ch - self.pan_y) / s)
        cv.delete("img")
        if x1 <= x0 or y1 <= y0:
            return
        ix0, iy0 = int(math.floor(x0)), int(math.floor(y0))
        ix1, iy1 = int(math.ceil(x1)), int(math.ceil(y1))
        crop = self.img.crop((ix0, iy0, ix1, iy1))
        tw, th = max(1, round((ix1 - ix0) * s)), max(1, round((iy1 - iy0) * s))
        if s < 1:
            f = int(1 / s)
            if hq and f >= 2:
                crop = crop.reduce(f)
            rs = Image.LANCZOS if hq else Image.BILINEAR
        else:
            rs = Image.BICUBIC if hq else Image.BILINEAR
        self._photo = ImageTk.PhotoImage(crop.resize((tw, th), rs))
        sx, sy = self.i2s(ix0, iy0)
        cv.create_image(round(sx), round(sy), image=self._photo, anchor="nw", tags="img")
        cv.tag_lower("img")

    def _font(self, px, bold=False):
        px = max(1, int(round(px)))
        k = (px, bold)
        if k not in self._fonts:
            self._fonts[k] = tkfont.Font(family="Arial", size=-px, weight="bold" if bold else "normal")
        return self._fonts[k]

    def text_px_img(self):
        """Label font size in image pixels."""
        return self.text_pt * self.px_per_pt * self.unit

    def label_metrics(self, ann, measure, fpx):
        """Shared layout for screen + export. measure(text,bold)->width"""
        lines = label_lines(ann, self.cfg["tolerance"])
        pad = max(1.0, fpx * 0.38)
        lh = fpx * 1.35
        w = max((measure(t, b) for t, _, b in lines), default=0) + pad * 2
        h = len(lines) * lh + pad * 2 - (lh - fpx) if lines else 0
        return lines, pad, lh, w, h

    def draw_annotations(self):
        cv = self.cv
        cv.delete("ann")
        self.geom = {"label": {}, "anchor": {}, "arrow": {}}
        if not self.img:
            self._update_counts()
            return
        s = self.scale
        sty = LABEL_STYLES[self.cfg["label_style"]]
        k = s * self.unit  # screen px per "fit px"

        for ar in self.arrows:
            x1, y1 = self.i2s(ar["x1"], ar["y1"])
            x2, y2 = self.i2s(ar["x2"], ar["y2"])
            selected = self.sel == ("arrow", ar["id"])
            w = max(1.0, ar.get("w", 2.0) * k)
            hs = max(6.0, 4.5 * w)
            cv.create_line(x1, y1, x2, y2, fill=ar["color"], width=w, arrow="last", capstyle="round",
                           arrowshape=(hs, hs * 1.1, hs * 0.45), tags=("ann", "arw"))
            if selected:
                for (hx, hy) in ((x1, y1), (x2, y2)):
                    cv.create_oval(hx - 5, hy - 5, hx + 5, hy + 5, outline=ACCENT, width=2, fill="#0b1520", tags=("ann", "arw"))
            self.geom["arrow"][ar["id"]] = (x1, y1, x2, y2)

        if self.drag and self.drag.get("kind") == "new-arrow" and self.drag.get("cur"):
            x1, y1 = self.i2s(*self.drag["start"])
            x2, y2 = self.drag["cur"]
            w = max(1.0, 2.0 * k)
            hs = max(6.0, 4.5 * w)
            cv.create_line(x1, y1, x2, y2, fill=self.cfg["arrow_color"], width=w, arrow="last", dash=(6, 3),
                           arrowshape=(hs, hs * 1.1, hs * 0.45), tags=("ann", "arw"))

        fpx = self.text_px_img() * s
        for ann in self.anns:
            selected = self.sel == ("ann", ann["id"])
            ax, ay = self.i2s(ann["ax"], ann["ay"])
            st = overall(ann, self.cfg["tolerance"])
            edge = sty[st] if st != "none" else sty["edge_none"]
            dot_r = max(2.0, 2.6 * k)
            self.geom["anchor"][ann["id"]] = (ax, ay)
            if fpx < 3:  # too small to read: show anchor only
                cv.create_oval(ax - dot_r, ay - dot_r, ax + dot_r, ay + dot_r, fill=edge, outline="", tags="ann")
                continue
            lines, pad, lh, bw, bh = self.label_metrics(ann, lambda t, b: self._font(fpx, b).measure(t), fpx)
            lx, ly = self.i2s(ann["lx"], ann["ly"])
            if lines:
                bx0, by0 = lx, ly - bh / 2
                bx1, by1 = bx0 + bw, by0 + bh
                cx = bx1 if ax > bx1 else (bx0 if ax < bx0 else ax)
                cy = by1 if ay > by1 else (by0 if ay < by0 else ay)
                if not (bx0 <= ax <= bx1 and by0 <= ay <= by1):
                    cv.create_line(ax, ay, cx, cy, fill=ACCENT if selected else sty["leader"], width=max(1, 0.8 * k),
                                   dash=(3, 2), tags="ann")
                cv.create_rectangle(bx0, by0, bx1, by1, fill=sty["box"], outline=ACCENT if selected else edge,
                                    width=2 if selected else max(1, round(0.9 * k)), tags="ann")
                ty = by0 + pad
                for text, state, bold in lines:
                    col = sty["head"] if state == "head" else sty[state]
                    cv.create_text(bx0 + pad, ty, text=text, anchor="nw", fill=col, font=self._font(fpx, bold), tags="ann")
                    ty += lh
                self.geom["label"][ann["id"]] = (bx0, by0, bx1, by1)
            cv.create_oval(ax - dot_r, ay - dot_r, ax + dot_r, ay + dot_r, fill=ACCENT if selected else edge,
                           outline="", tags="ann")
        cv.tag_raise("ann")
        cv.tag_raise("arw")
        self._update_counts()

    def _update_counts(self):
        if not self.anns:
            self.status_counts.configure(text="")
            return
        tol = self.cfg["tolerance"]
        p = sum(1 for a in self.anns if overall(a, tol) == "pass")
        f = sum(1 for a in self.anns if overall(a, tol) == "fail")
        self.status_counts.configure(text=f"{len(self.anns)} readings   ✓ {p} pass   ✗ {f} fail   ·   {len(self.arrows)} arrows")

    # ── hit testing ───────────────────────────────────────────────────
    def hit(self, x, y):
        g = self.geom
        if self.sel and self.sel[0] == "arrow" and self.sel[1] in g.get("arrow", {}):
            x1, y1, x2, y2 = g["arrow"][self.sel[1]]
            if math.hypot(x - x1, y - y1) < 8:
                return ("arrow", self.sel[1], "p1")
            if math.hypot(x - x2, y - y2) < 8:
                return ("arrow", self.sel[1], "p2")
        for aid in reversed(list(g.get("anchor", {}))):
            ax, ay = g["anchor"][aid]
            if math.hypot(x - ax, y - ay) < 7:
                return ("ann", aid, "anchor")
        for aid in reversed(list(g.get("label", {}))):
            x0, y0, x1, y1 = g["label"][aid]
            if x0 <= x <= x1 and y0 <= y <= y1:
                return ("ann", aid, "label")
        for aid in reversed(list(g.get("arrow", {}))):
            x1, y1, x2, y2 = g["arrow"][aid]
            dx, dy = x2 - x1, y2 - y1
            L2 = dx * dx + dy * dy
            if L2 < 1:
                continue
            t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / L2))
            if math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) < 6:
                return ("arrow", aid, "body")
        return None

    def find(self, kind, oid):
        coll = self.anns if kind == "ann" else self.arrows
        return next((o for o in coll if o["id"] == oid), None)

    # ── mouse ─────────────────────────────────────────────────────────
    def on_press(self, e):
        self.cv.focus_set()
        if self.form_ctx:
            self._commit_or_close_form()
            self.drag = {"kind": "noop"}
            return
        if not self.img:
            return
        if self.space:
            self.drag = {"kind": "pan", "sx": e.x, "sy": e.y, "px": self.pan_x, "py": self.pan_y, "moved": False}
            return
        h = self.hit(e.x, e.y)
        if self.tool == "arrow" and not (h and h[0] == "arrow" and self.sel == ("arrow", h[1])):
            self.drag = {"kind": "new-arrow", "start": self.s2i(e.x, e.y), "sx": e.x, "sy": e.y, "cur": None, "moved": False}
            return
        if h:
            kind, oid, part = h
            self.sel = (kind, oid)
            obj = copy.deepcopy(self.find(kind, oid))
            self.drag = {"kind": "move", "what": h, "orig": obj, "sx": e.x, "sy": e.y, "moved": False,
                         "snap": self.snapshot()}
            self.draw_annotations()
            return
        if self.sel:
            self.sel = None
            self.draw_annotations()
        self.drag = {"kind": "pan", "sx": e.x, "sy": e.y, "px": self.pan_x, "py": self.pan_y, "moved": False,
                     "click": True}

    def on_motion_drag(self, e):
        d = self.drag
        if not d or d["kind"] == "noop":
            return
        if not d["moved"] and math.hypot(e.x - d["sx"], e.y - d["sy"]) < 4:
            return
        d["moved"] = True
        if d["kind"] == "pan":
            self.pan_x = d["px"] + (e.x - d["sx"])
            self.pan_y = d["py"] + (e.y - d["sy"])
            self.auto_fit = False
            self.cv.configure(cursor="fleur")
            self.redraw()
        elif d["kind"] == "new-arrow":
            d["cur"] = (e.x, e.y)
            self.draw_annotations()
        elif d["kind"] == "move":
            if d.get("snap"):
                self.undo_stack.append(d.pop("snap"))
                self.redo_stack.clear()
            kind, oid, part = d["what"]
            obj, o = self.find(kind, oid), d["orig"]
            dx, dy = (e.x - d["sx"]) / self.scale, (e.y - d["sy"]) / self.scale
            if kind == "ann":
                if part == "label":
                    obj["lx"], obj["ly"] = o["lx"] + dx, o["ly"] + dy
                else:
                    obj["ax"], obj["ay"] = o["ax"] + dx, o["ay"] + dy
            else:
                if part in ("body", "p1"):
                    obj["x1"], obj["y1"] = o["x1"] + dx, o["y1"] + dy
                if part in ("body", "p2"):
                    obj["x2"], obj["y2"] = o["x2"] + dx, o["y2"] + dy
            self.dirty = True
            self.draw_annotations()

    def on_release(self, e):
        d, self.drag = self.drag, None
        self.on_hover(e)
        if not d or d["kind"] == "noop":
            return
        if d["kind"] == "new-arrow":
            if d["moved"] and math.hypot(e.x - d["sx"], e.y - d["sy"]) > 6:
                self.push_undo()
                x2, y2 = self.s2i(e.x, e.y)
                ar = {"id": self.new_id(), "x1": d["start"][0], "y1": d["start"][1], "x2": x2, "y2": y2,
                      "color": self.cfg["arrow_color"], "w": 2.0}
                self.arrows.append(ar)
                self.sel = None
                self.mark_dirty()
            else:
                self.draw_annotations()
            return
        if d["kind"] == "move":
            if d["moved"]:
                self.mark_dirty()
            return
        if d["kind"] == "pan":
            if d["moved"]:
                self.redraw()
            elif d.get("click") and self.tool == "annotate" and self.on_image(e.x, e.y):
                self.open_form(e.x, e.y)

    def on_double(self, e):
        h = self.hit(e.x, e.y)
        if h and h[0] == "ann":
            self.sel = ("ann", h[1])
            self.draw_annotations()
            self.open_form(e.x, e.y, edit_id=h[1])

    def on_hover(self, e):
        if self.drag:
            return
        if self.space:
            self.cv.configure(cursor="fleur")
            return
        h = self.hit(e.x, e.y) if self.img else None
        if h and not (self.tool == "arrow" and h[2] != "p1" and h[2] != "p2"):
            self.cv.configure(cursor="fleur" if h[2] in ("label", "body") else "hand2")
        elif self.tool == "select":
            self.cv.configure(cursor="arrow")
        else:
            self.cv.configure(cursor="crosshair")

    def on_pan_press(self, e):
        self.drag = {"kind": "pan", "sx": e.x, "sy": e.y, "px": self.pan_x, "py": self.pan_y, "moved": False}

    def on_pan_motion(self, e):
        self.on_motion_drag(e)

    def on_pan_release(self, e, button):
        d, self.drag = self.drag, None
        self.on_hover(e)
        if d and not d.get("moved") and button == "3" and self.img:
            h = self.hit(e.x, e.y)
            if h:
                self.sel = (h[0], h[1])
                self.draw_annotations()
                self._item_menu(e, h)

    def _item_menu(self, e, h):
        m = tk.Menu(self.root, tearoff=0, font=UI_FONT)
        if h[0] == "ann":
            m.add_command(label="Edit reading", command=lambda: self.open_form(e.x, e.y, edit_id=h[1]))
        else:
            cm = tk.Menu(m, tearoff=0)
            for c in ARROW_COLORS:
                cm.add_command(label="■  " + c, foreground=c if c != "#111111" else "#888", command=lambda c=c: self._recolor(h[1], c))
            m.add_cascade(label="Colour", menu=cm)
        m.add_command(label="Delete", command=self.delete_selected)
        m.tk_popup(e.x_root, e.y_root)

    def _recolor(self, aid, c):
        ar = self.find("arrow", aid)
        if ar:
            self.push_undo()
            ar["color"] = c
            self.mark_dirty()

    def on_wheel(self, e, delta=None):
        if not self.img:
            return
        delta = delta if delta is not None else e.delta
        ctrl = bool(e.state & 0x0004)
        shift = bool(e.state & 0x0001)
        zoom_mode = (self.cfg["wheel"] == "zoom" and not shift) or (self.cfg["wheel"] == "scroll" and ctrl)
        if zoom_mode:
            self.zoom_at(e.x, e.y, 1.15 if delta > 0 else 1 / 1.15)
        else:
            step = 80 if delta > 0 else -80
            if shift:
                self.pan_x += step
            else:
                self.pan_y += step
            self.auto_fit = False
            self.redraw()

    def _space_down(self, e):
        if self._typing():
            return
        if not self.space:
            self.space = True
            self.cv.configure(cursor="fleur")

    def _space_up(self, e):
        self.space = False
        self.cv.configure(cursor="crosshair" if self.tool != "select" else "arrow")

    def on_key(self, e):
        if self._typing() or (e.state & 0x0004):
            return
        k = e.keysym
        if k in ("Delete", "BackSpace"):
            self.delete_selected()
        elif k == "Escape":
            if self.form_ctx:
                self.close_form()
            else:
                self.sel = None
                self.draw_annotations()
        elif k in ("a", "A"):
            self.set_tool("annotate")
        elif k in ("w", "W"):
            self.set_tool("arrow")
        elif k in ("s", "S"):
            self.set_tool("select")
        elif k in ("t", "T"):
            self.show_summary()
        elif k in ("plus", "equal", "KP_Add"):
            self.zoom_center(1.2)
        elif k in ("minus", "KP_Subtract"):
            self.zoom_center(1 / 1.2)
        elif k == "0":
            self.fit_width()
        elif k == "parenright" or (k == "0" and e.state & 0x0001):
            self.fit_whole()
        elif k == "1":
            self.actual_pixels()
        elif k in ("Return", "e", "E") and self.sel and self.sel[0] == "ann":
            ann = self.find("ann", self.sel[1])
            if ann:
                x, y = self.i2s(ann["ax"], ann["ay"])
                self.open_form(x, y, edit_id=ann["id"])

    # ── tools ─────────────────────────────────────────────────────────
    def _hint_text(self):
        if not self.img:
            return "Open a diagram (Ctrl+O), paste a screenshot (Ctrl+V), or right-click an image → Annotate"
        return {
            "annotate": "Click next to a wire or pin to add a reading · drag a label to move it · double-click to edit · right/middle-drag or Space+drag to pan",
            "arrow": "Drag from the label toward the wire, pin or connector · right-click an arrow to recolour or delete",
            "select": "Click to select · drag labels, anchor dots or arrow ends · Delete removes · Enter edits",
        }[self.tool]

    def set_tool(self, t):
        self.tool = t
        self.close_form()
        for k, b in self.tool_btns.items():
            if k == t:
                b.configure(bg="#1b2d40", fg="#8cc8ff", highlightbackground="#2f5376")
            else:
                b.configure(bg=BAR, fg="#c9cdd3", highlightbackground=BORDER)
        self.cv.configure(cursor="arrow" if t == "select" else "crosshair")
        self.status_hint.configure(text=self._hint_text())
        self._paint_swatches()

    def _paint_swatches(self):
        for col, sw in self.swatches.items():
            sw.configure(highlightbackground="#e0e0e0" if col == self.cfg["arrow_color"] else BAR)

    def set_arrow_color(self, c):
        self.cfg["arrow_color"] = c
        self._paint_swatches()
        if self.sel and self.sel[0] == "arrow":
            self._recolor(self.sel[1], c)

    def on_text_size(self):
        try:
            v = max(6, min(28, int(float(self.text_var.get()))))
        except ValueError:
            v = self.text_pt
        self.text_var.set(str(v))
        if v != self.text_pt:
            if self.img:
                self.push_undo()
            self.text_pt = v
            self.cfg["text_pt"] = v
            if self.img:
                self.mark_dirty()

    def on_style(self):
        self.cfg["label_style"] = self.style_var.get()
        self.draw_annotations()

    def on_wheel_mode(self):
        self.cfg["wheel"] = self.wheel_var.get()

    def ask_tolerance(self):
        from tkinter import simpledialog
        v = simpledialog.askinteger(APP_NAME, "Pass/fail tolerance for V and Ω (± percent):",
                                    initialvalue=self.cfg["tolerance"], minvalue=1, maxvalue=50, parent=self.root)
        if v:
            self.cfg["tolerance"] = v
            self.draw_annotations()

    def delete_selected(self):
        if not self.sel:
            return
        self.push_undo()
        kind, oid = self.sel
        if kind == "ann":
            self.anns = [a for a in self.anns if a["id"] != oid]
        else:
            self.arrows = [a for a in self.arrows if a["id"] != oid]
        self.sel = None
        self.mark_dirty()

    def clear_all(self):
        if (self.anns or self.arrows) and messagebox.askyesno(APP_NAME, "Remove all readings and arrows?", parent=self.root):
            self.push_undo()
            self.anns, self.arrows, self.sel = [], [], None
            self.mark_dirty()

    # ── reading form ──────────────────────────────────────────────────
    def open_form(self, sx, sy, edit_id=None):
        self.close_form()
        ix, iy = self.s2i(sx, sy)
        self.form_ctx = {"ix": ix, "iy": iy, "edit": edit_id}
        recent = list(dict.fromkeys([a.get("label", "") for a in reversed(self.anns) if a.get("label")] +
                                    self.cfg.get("recent_labels", [])))[:40]
        self.f_label["values"] = recent
        ann = self.find("ann", edit_id) if edit_id else None
        self.f_label.set(ann.get("label", "") if ann else "")
        for k, e in self.f_fields.items():
            e.delete(0, "end")
            if ann:
                e.insert(0, ann.get(k, ""))
        self.form_title.configure(text="EDIT READING" if ann else "ADD READING")
        if ann:
            self.f_del.pack(side="left", padx=(5, 0), before=self.f_cancel)
            self.f_ok.configure(text="✓ Update  (Enter)")
        else:
            self.f_del.pack_forget()
            self.f_ok.configure(text="✓ Place  (Enter)")
        self._form_live()
        self.form.update_idletasks()
        fw, fh = self.form.winfo_reqwidth(), self.form.winfo_reqheight()
        cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
        x = sx + 18 if sx + 18 + fw < cw - 6 else sx - fw - 18
        y = min(max(6, sy - fh / 2), ch - fh - 6)
        self.form.place(x=max(6, x), y=y)
        self.form.lift()
        # temporary crosshair marker where the reading will go
        self.cv.delete("pending")
        if not ann:
            self.cv.create_oval(sx - 4, sy - 4, sx + 4, sy + 4, outline=ACCENT, width=2, tags="pending")
        self.f_label.focus_set()

    def _form_live(self):
        tol = self.cfg["tolerance"]
        cols = {"pass": "#4ade80", "fail": "#f87171", "none": FG}
        for key, kind in (("v", "v"), ("vd", "vd"), ("r", "r")):
            st = check(kind, self.f_fields[key + "_exp"].get(), self.f_fields[key + "_act"].get(), tol)
            self.f_fields[key + "_act"].configure(fg=cols[st])

    def _form_values(self):
        d = {"label": self.f_label.get().strip()}
        for k, e in self.f_fields.items():
            d[k] = e.get().strip()
        return d

    def _commit_or_close_form(self):
        if any(self._form_values().values()):
            self.submit_form()
        else:
            self.close_form()

    def submit_form(self):
        if not self.form_ctx:
            return
        d = self._form_values()
        ctx = self.form_ctx
        if not any(d.values()):
            self.close_form()
            return
        self.push_undo()
        if ctx["edit"]:
            ann = self.find("ann", ctx["edit"])
            if ann:
                ann.update(d)
        else:
            s = self.scale
            fpx = self.text_px_img() * s
            ann = {"id": self.new_id(), "ax": ctx["ix"], "ay": ctx["iy"], **d}
            lines, pad, lh, bw, bh = self.label_metrics(ann, lambda t, b: self._font(fpx, b).measure(t), fpx)
            off = 14 / s
            ann["lx"], ann["ly"] = ctx["ix"] + off, ctx["iy"]
            # flip to the left if it would run off the right edge
            if ann["lx"] + bw / s > self.img.width:
                ann["lx"] = ctx["ix"] - off - bw / s
            self.anns.append(ann)
            self.sel = None
        if d["label"]:
            rl = [d["label"]] + [x for x in self.cfg.get("recent_labels", []) if x != d["label"]]
            self.cfg["recent_labels"] = rl[:60]
        self.close_form()
        self.mark_dirty()

    def delete_from_form(self):
        if self.form_ctx and self.form_ctx["edit"]:
            self.sel = ("ann", self.form_ctx["edit"])
            self.close_form()
            self.delete_selected()

    def close_form(self):
        self.form_ctx = None
        self.form.place_forget()
        self.cv.delete("pending")
        self.cv.focus_set()

    # ── export ────────────────────────────────────────────────────────
    def render_export(self):
        """Full-resolution annotated image (PIL RGB).
        If the diagram is smaller than the screen it was annotated on, the export is
        upscaled to match the on-screen fit-width view so the labels stay legible."""
        f = max(1.0, min(1.0 / self.unit, 4.0, 14000 / max(self.img.size)))
        if f > 1.02:
            img = self.img.resize((round(self.img.width * f), round(self.img.height * f)), Image.LANCZOS)
        else:
            f, img = 1.0, self.img
        sty = LABEL_STYLES[self.cfg["label_style"]]
        fpx = self.text_px_img() * f
        u = self.unit * f
        fonts = {}
        S = lambda o, keys: {**o, **{k: o[k] * f for k in keys}}
        anns = [S(a, ("ax", "ay", "lx", "ly")) for a in self.anns]
        arrows = [S(a, ("x1", "y1", "x2", "y2")) for a in self.arrows]

        def font(b):
            if b not in fonts:
                fonts[b] = load_pil_font(fpx, b)
            return fonts[b]

        def measure(t, b):
            return font(b).getlength(t)

        layouts = []
        minx, miny, maxx, maxy = 0, 0, img.width, img.height
        for ann in anns:
            lines, pad, lh, bw, bh = self.label_metrics(ann, measure, fpx)
            box = (ann["lx"], ann["ly"] - bh / 2, ann["lx"] + bw, ann["ly"] + bh / 2) if lines else None
            layouts.append((ann, lines, pad, lh, box))
            pts = [(ann["ax"], ann["ay"])] + ([(box[0], box[1]), (box[2], box[3])] if box else [])
            for x, y in pts:
                minx, miny, maxx, maxy = min(minx, x), min(miny, y), max(maxx, x), max(maxy, y)
        for ar in arrows:
            for x, y in ((ar["x1"], ar["y1"]), (ar["x2"], ar["y2"])):
                minx, miny, maxx, maxy = min(minx, x), min(miny, y), max(maxx, x), max(maxy, y)
        m = int(6 * u)
        ox = int(-minx + m) if minx < 0 else 0
        oy = int(-miny + m) if miny < 0 else 0
        W = int(max(img.width, maxx + m)) + ox if maxx > img.width else img.width + ox
        H = int(max(img.height, maxy + m)) + oy if maxy > img.height else img.height + oy
        out = Image.new("RGB", (W, H), "white")
        out.paste(img, (ox, oy))
        d = ImageDraw.Draw(out)

        for ann, lines, pad, lh, box in layouts:
            st = overall(ann, self.cfg["tolerance"])
            edge = sty[st] if st != "none" else sty["edge_none"]
            ax, ay = ann["ax"] + ox, ann["ay"] + oy
            if box:
                bx0, by0, bx1, by1 = box[0] + ox, box[1] + oy, box[2] + ox, box[3] + oy
                cx = bx1 if ax > bx1 else (bx0 if ax < bx0 else ax)
                cy = by1 if ay > by1 else (by0 if ay < by0 else ay)
                if not (bx0 <= ax <= bx1 and by0 <= ay <= by1):
                    self._dashed(d, ax, ay, cx, cy, sty["leader"], max(1, round(0.8 * u)), 3 * u, 2 * u)
                d.rectangle((bx0, by0, bx1, by1), fill=sty["box"], outline=edge, width=max(1, round(0.9 * u)))
                ty = by0 + pad
                for text, state, bold in lines:
                    col = sty["head"] if state == "head" else sty[state]
                    d.text((bx0 + pad, ty), text, fill=col, font=font(bold))
                    ty += lh
            r = max(2.0, 2.6 * u)
            d.ellipse((ax - r, ay - r, ax + r, ay + r), fill=edge)
        for ar in arrows:
            x1, y1, x2, y2 = ar["x1"] + ox, ar["y1"] + oy, ar["x2"] + ox, ar["y2"] + oy
            w = max(1, round(ar.get("w", 2.0) * u))
            hs = max(6.0, 4.5 * w)
            L = math.hypot(x2 - x1, y2 - y1) or 1
            ux, uy = (x2 - x1) / L, (y2 - y1) / L
            bx, by = x2 - ux * hs, y2 - uy * hs
            d.line([(x1, y1), (bx + ux * 1, by + uy * 1)], fill=ar["color"], width=w)
            hw = hs * 0.45
            d.polygon([(x2, y2), (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)], fill=ar["color"])
        return out

    @staticmethod
    def _dashed(d, x1, y1, x2, y2, col, w, on, off):
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1:
            return
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        t = 0.0
        while t < L:
            t2 = min(L, t + on)
            d.line([(x1 + ux * t, y1 + uy * t), (x1 + ux * t2, y1 + uy * t2)], fill=col, width=w)
            t = t2 + off

    def _write_sidecar(self, near_output=None):
        data = {"app": APP_NAME, "version": APP_VERSION, "unit": self.unit, "text_pt": self.text_pt,
                "anns": self.anns, "arrows": self.arrows, "out_path": self.out_path}
        targets = []
        if self.src_path:
            targets.append(self.src_path + SIDE_EXT)
        if near_output:
            targets.append(near_output + SIDE_EXT)
        for t in targets:
            try:
                with open(t, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1)
                return True
            except OSError:
                continue
        return False

    def save(self, ask=False):
        if not self.img:
            self.toast("Open a diagram first", error=True)
            return False
        path = self.out_path
        if ask or not path:
            stem = os.path.splitext(os.path.basename(self.src_path))[0] if self.src_path else "diagram"
            init_dir = os.path.dirname(self.src_path) if self.src_path else (self.cfg.get("last_dir") or None)
            path = filedialog.asksaveasfilename(
                parent=self.root, title="Save annotated diagram", initialdir=init_dir,
                initialfile=f"{stem}_annotated.png", defaultextension=".png",
                filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg"), ("PDF", "*.pdf")])
            if not path:
                return False
        try:
            out = self.render_export()
            ext = os.path.splitext(path)[1].lower()
            if ext in (".jpg", ".jpeg"):
                out.save(path, quality=95, subsampling=0)
            elif ext == ".pdf":
                out.save(path, "PDF", resolution=150)
            else:
                out.save(path, optimize=True)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Couldn't save:\n{ex}", parent=self.root)
            return False
        self.out_path = path
        self._write_sidecar(None if self.src_path else os.path.splitext(path)[0])
        self.dirty = False
        self.update_title()
        self.toast(f"Saved  {os.path.basename(path)}")
        return True

    def copy_image(self):
        if not self.img:
            self.toast("Open a diagram first", error=True)
            return
        if sys.platform != "win32":
            self.toast("Image clipboard copy is Windows-only — use Save", error=True)
            return
        try:
            copy_image_to_clipboard(self.render_export())
            self.toast("📋 Annotated image copied — paste into email, Teams, Word…")
        except Exception as ex:
            self.toast(f"Copy failed: {ex}", error=True)

    def print_image_only(self):
        if not self.img:
            return
        p = os.path.join(tempfile.gettempdir(), f"{APP_NAME}_print_{int(time.time())}.png")
        self.render_export().save(p)
        try:
            os.startfile(p, "print")
        except Exception:
            webbrowser.open("file:///" + p.replace("\\", "/"))

    def print_report(self):
        if not self.img:
            self.toast("Open a diagram first", error=True)
            return
        buf = io.BytesIO()
        self.render_export().save(buf, "PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        tol = self.cfg["tolerance"]
        title = os.path.basename(self.src_path) if self.src_path else "Wiring diagram"
        rows = []
        col = {"pass": "#15803d", "fail": "#b91c1c", "warn": "#b45309", "none": "#555"}
        lab = {"pass": "PASS", "fail": "FAIL", "warn": "PARTIAL", "none": "—"}
        for i, a in enumerate(self.anns, 1):
            st = overall(a, tol)
            def cell(k, kind):
                e, ac = a.get(k + "_exp", ""), a.get(k + "_act", "")
                if not e and not ac:
                    return "—"
                c = col[check(kind, e, ac, tol)]
                return f'<span style="color:{c};font-weight:600">{html_lib.escape(ac or "?")}</span> / {html_lib.escape(e or "?")}'
            rows.append(f"<tr><td>{i}</td><td>{html_lib.escape(a.get('label') or '—')}</td><td>{cell('v','v')}</td>"
                        f"<td>{cell('vd','vd')}</td><td>{cell('r','r')}</td>"
                        f"<td style='color:{col[st]};font-weight:700'>{lab[st]}</td></tr>")
        table = ""
        if rows:
            table = ("<h2>Readings</h2><table><thead><tr><th>#</th><th>Location</th><th>Voltage act / exp</th>"
                     "<th>V-drop act / max</th><th>Resistance act / exp</th><th>Result</th></tr></thead><tbody>"
                     + "".join(rows) + "</tbody></table>"
                     f"<p class='n'>V and Ω pass within ±{tol}% (Ω also within 0.5 Ω). Voltage drop passes at or below the expected maximum.</p>")
        doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html_lib.escape(title)} — {APP_NAME}</title>
<style>
@page {{ size: landscape; margin: 10mm; }}
body{{font-family:Arial,Helvetica,sans-serif;font-size:10pt;color:#111;margin:0}}
header{{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #111;padding-bottom:4px;margin-bottom:8px}}
h1{{font-size:13pt;margin:0}} h2{{font-size:11pt;margin:12px 0 5px}}
img{{width:100%;height:auto;display:block;border:1px solid #bbb}}
table{{border-collapse:collapse;width:100%;font-size:9pt;page-break-inside:auto}}
th{{background:#222;color:#fff;text-align:left;padding:4px 7px}} td{{padding:3px 7px;border-bottom:1px solid #ddd}}
tr{{page-break-inside:avoid}} .n{{color:#666;font-size:8pt}}
</style></head><body>
<header><h1>{html_lib.escape(title)}</h1><span>{time.strftime('%Y-%m-%d %H:%M')}</span></header>
<img src="data:image/png;base64,{b64}">{table}
<script>window.onload=function(){{setTimeout(function(){{window.print()}},300)}}</script>
</body></html>"""
        p = os.path.join(tempfile.gettempdir(), f"{APP_NAME}_report_{int(time.time())}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(doc)
        webbrowser.open("file:///" + p.replace("\\", "/"))
        self.toast("Report opened in your browser — print dialog will appear")

    # ── summary window ────────────────────────────────────────────────
    def show_summary(self):
        if not self.anns:
            self.toast("No readings yet", error=True)
            return
        tol = self.cfg["tolerance"]
        win = tk.Toplevel(self.root)
        win.title(f"Readings — {APP_NAME}")
        win.configure(bg=BAR)
        win.geometry("760x380")
        win.transient(self.root)
        cols = ("n", "loc", "v", "vd", "r", "res")
        tv = ttk.Treeview(win, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("n", "#", 36), ("loc", "Location", 230), ("v", "Voltage act / exp", 130),
                        ("vd", "V-drop act / max", 130), ("r", "Ω act / exp", 120), ("res", "Result", 80)):
            tv.heading(c, text=t, anchor="w")
            tv.column(c, width=w, anchor="w", stretch=(c == "loc"))
        tv.tag_configure("pass", foreground="#4ade80")
        tv.tag_configure("fail", foreground="#f87171")
        tv.tag_configure("warn", foreground="#fbbf24")
        tv.tag_configure("none", foreground=FG)
        lab = {"pass": "✓ PASS", "fail": "✗ FAIL", "warn": "⚠ PARTIAL", "none": "—"}
        rows = []
        for i, a in enumerate(self.anns, 1):
            def pair(k):
                e, ac = a.get(k + "_exp", ""), a.get(k + "_act", "")
                return f"{ac or '?'} / {e or '?'}" if (e or ac) else "—"
            st = overall(a, tol)
            row = (i, a.get("label") or "—", pair("v"), pair("vd"), pair("r"), lab[st])
            rows.append(row)
            tv.insert("", "end", iid=str(a["id"]), values=row, tags=(st,))
        tv.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        def goto(_=None):
            s = tv.selection()
            if not s:
                return
            ann = self.find("ann", int(s[0]))
            if ann:
                self.sel = ("ann", ann["id"])
                cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
                if self.scale < 1.0 / self.unit * 1.5:
                    self.scale = 1.0 / self.unit * 1.5
                self.pan_x = cw / 2 - ann["ax"] * self.scale
                self.pan_y = ch / 2 - ann["ay"] * self.scale
                self.auto_fit = False
                self.redraw()
        tv.bind("<Double-1>", goto)

        bar = tk.Frame(win, bg=BAR)
        bar.pack(fill="x", padx=8, pady=(0, 8))

        def copy_tsv():
            hdr = "#\tLocation\tVoltage act/exp\tV-drop act/max\tOhms act/exp\tResult"
            txt = hdr + "\n" + "\n".join("\t".join(str(x) for x in r) for r in rows)
            self.root.clipboard_clear()
            self.root.clipboard_append(txt.replace("✓ ", "").replace("✗ ", "").replace("⚠ ", ""))
            self.toast("Table copied — paste into Excel, Sheets or a note")

        def export_csv():
            stem = os.path.splitext(os.path.basename(self.src_path))[0] if self.src_path else "readings"
            p = filedialog.asksaveasfilename(parent=win, defaultextension=".csv", initialfile=f"{stem}_readings.csv",
                                             initialdir=os.path.dirname(self.src_path) if self.src_path else None,
                                             filetypes=[("CSV", "*.csv")])
            if p:
                with open(p, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["#", "Location", "V expected", "V actual", "Vd max", "Vd actual", "Ohm expected", "Ohm actual", "Result"])
                    for i, a in enumerate(self.anns, 1):
                        w.writerow([i, a.get("label", ""), a.get("v_exp", ""), a.get("v_act", ""), a.get("vd_exp", ""),
                                    a.get("vd_act", ""), a.get("r_exp", ""), a.get("r_act", ""), overall(a, tol).upper()])
                self.toast(f"Saved {os.path.basename(p)}")

        self._btn(bar, "📋 Copy table", copy_tsv).pack(side="left")
        self._btn(bar, "⤓ Export CSV", export_csv).pack(side="left", padx=(5, 0))
        tk.Label(bar, text="Double-click a row to jump to it", bg=BAR, fg=DIM, font=UI_FONT).pack(side="left", padx=10)
        self._btn(bar, "Close", win.destroy).pack(side="right")
        win.bind("<Escape>", lambda e: win.destroy())

    # ── misc ──────────────────────────────────────────────────────────
    def toast(self, msg, error=False):
        self.toast_lbl.configure(text=msg, bg="#7f1d1d" if error else "#1f6f43", fg="#ffe4e4" if error else "#eafff2")
        self.toast_lbl.place(relx=0.5, rely=1.0, y=-18, anchor="s")
        self.toast_lbl.lift()
        if self._toast_job:
            self.root.after_cancel(self._toast_job)
        self._toast_job = self.root.after(2600, self.toast_lbl.place_forget)

    def do_register(self):
        try:
            register_context_menu()
            messagebox.showinfo(APP_NAME, "Added “Annotate” to the right-click menu for images.\n\n"
                                "On Windows 11 it's under “Show more options” (or Shift+right-click).", parent=self.root)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Couldn't update the registry:\n{ex}", parent=self.root)

    def do_unregister(self):
        try:
            unregister_context_menu()
            messagebox.showinfo(APP_NAME, "Removed “Annotate” from the right-click menu.", parent=self.root)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Couldn't update the registry:\n{ex}", parent=self.root)

    def show_help(self):
        messagebox.showinfo(f"{APP_NAME} — shortcuts", (
            "TOOLS\n"
            "  A  Annotate — click next to a wire/pin, type readings, Enter\n"
            "  W  Arrow — drag to point at a trace, connector or pin\n"
            "  S  Select — drag labels, anchor dots, arrow ends\n\n"
            "EDITING\n"
            "  Double-click / Enter  edit reading      Delete  remove\n"
            "  Right-click item  edit · recolour · delete\n"
            "  Ctrl+Z / Ctrl+Y  undo / redo\n\n"
            "VIEW\n"
            "  Wheel  zoom at cursor (Shift+wheel side-scroll)\n"
            "  Right/middle-drag, Space+drag, or drag empty area  pan\n"
            "  0  fit width     Shift+0  whole diagram     1  100%     F11  full screen\n\n"
            "FILE\n"
            "  Ctrl+O open   Ctrl+V paste screenshot   Ctrl+S save   Ctrl+Shift+S save as\n"
            "  Ctrl+C copy annotated image   Ctrl+P print report   T readings table\n\n"
            "Readings are colour-coded: green = in spec, red = out of spec.\n"
            "V and Ω pass within ±tolerance (default 10%). Voltage drop passes\n"
            "when actual ≤ the expected maximum.\n\n"
            "Saving also writes <image>.wirenote.json next to the original so\n"
            "re-opening the same diagram brings your readings back."), parent=self.root)

    def show_about(self):
        messagebox.showinfo(APP_NAME, f"{APP_NAME} {APP_VERSION}\nQuick measurement annotator for wiring diagrams.\n\n"
                            "© 2026 NullHarp — GPLv3\ngithub.com/nullifiedharp/WireNote", parent=self.root)

    def on_close(self):
        if not self.confirm_discard():
            return
        try:
            self.cfg["zoomed"] = self.root.state() == "zoomed"
            if not self.cfg["zoomed"]:
                self.cfg["geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        save_settings(self.cfg)
        self.root.destroy()


def main():
    args = sys.argv[1:]
    if args and args[0] == "--make-icon":
        write_icons(args[1] if len(args) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"))
        return
    if args and args[0] in ("--register", "--unregister"):
        (register_context_menu if args[0] == "--register" else unregister_context_menu)()
        print("Context menu", "added." if args[0] == "--register" else "removed.")
        return
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    path = next((a for a in args if os.path.isfile(a)), None)
    root = tk.Tk()
    WireNote(root, path)
    root.mainloop()


if __name__ == "__main__":
    main()
