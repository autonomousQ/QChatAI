"""
QOpenRouter — Desktop chat UI
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "mistralai/mistral-7b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "z-ai/glm-4.5-air:free",
    "google/gemma-3-27b-it:free",
    "deepseek/deepseek-r1:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]

# ── Themes ─────────────────────────────────────────────────────────────────────
THEMES = {
    "dark": dict(
        bg="#1e1e2e", bg_input="#252537", bg_user="#2d2d52",
        bg_asst="#1e3228", bg_btn="#313145",
        fg="#cdd6f4", fg_dim="#585b70", fg_copy="#7f849c",
    ),
    "light": dict(
        bg="#f2f2f8", bg_input="#e6e6f0", bg_user="#ddddf8",
        bg_asst="#ddf0e8", bg_btn="#c8c8dc",
        fg="#1e1e2e", fg_dim="#7f849c", fg_copy="#6677a8",
    ),
}
THEME_CYCLE = ["dark", "light"]

BG_SEND   = "#6c63ff"
BG_CANCEL = "#c0566a"
FONT       = ("Segoe UI", 10)
FONT_MONO  = ("Consolas", 10)
FONT_BOLD  = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9, "italic")
PAD_X      = 12
CHAR_PX    = 7    # approximate pixel width per char in Consolas 10pt


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("QOpenRouter")
        root.geometry("860x680")
        root.minsize(620, 480)

        self._sending       = False
        self._cancel_flag   = False
        self._start_time    = 0.0
        self._timer_id      = None
        self._row_idx       = 0
        self._status_frame  = None
        self._status_lbl    = None
        self._current_model = ""
        self._stream_widget = None

        # Theme state
        self._theme_idx = 0   # starts on "dark"
        self._t = THEMES[THEME_CYCLE[0]]

        # Widget registries
        self._static_tw  = []   # (widget, {attr: theme_key}) — built once
        self._dyn_tw     = []   # (widget, {attr: theme_key}) — added per message
        self._resize_lbls = []  # tk.Label widgets needing wraplength updates
        self._resize_txts = []  # tk.Text widgets needing width updates

        # Force clam theme so ttk widget colors are fully controllable
        ttk.Style().theme_use("clam")

        self._build()
        self._apply_theme()
        root.bind_all("<MouseWheel>", self._on_mousewheel)

    # ── Theme ──────────────────────────────────────────────────────────────────

    def _sreg(self, w, **props):
        """Register a static (built-once) widget for theme updates."""
        self._static_tw.append((w, props))
        return w

    def _dreg(self, w, **props):
        """Register a dynamic (per-message) widget for theme updates."""
        self._dyn_tw.append((w, props))
        return w

    def _apply_theme(self):
        t = self._t
        # Root window background
        self.root.config(bg=t["bg"])
        # All registered widgets
        for w, props in self._static_tw + self._dyn_tw:
            cfg = {attr: t[key] for attr, key in props.items()}
            try:
                w.config(**cfg)
            except Exception:
                pass
        # Canvas / inner frame background
        try:
            self.canvas.config(bg=t["bg"])
            self.inner.config(bg=t["bg"])
        except Exception:
            pass
        # ttk styles — bordercolor/lightcolor/darkcolor prevent white borders
        s = ttk.Style()
        s.configure("Chat.TCombobox",
            fieldbackground=t["bg_asst"], background=t["bg_asst"],
            foreground=t["fg"], selectbackground=t["bg_btn"],
            selectforeground=t["fg"], arrowcolor=t["fg_dim"],
            insertcolor=t["fg"],
            bordercolor=t["bg_btn"],
            lightcolor=t["bg_asst"], darkcolor=t["bg_asst"],
            relief="flat", padding=4,
        )
        s.map("Chat.TCombobox",
            fieldbackground=[("readonly", t["bg_asst"]), ("active", t["bg_asst"])],
            foreground=[("readonly", t["fg"])],
            background=[("readonly", t["bg_asst"]), ("active", t["bg_asst"])],
            bordercolor=[("focus", t["bg_btn"]), ("!focus", t["bg_btn"])],
            lightcolor=[("focus", t["bg_asst"])],
            darkcolor=[("focus", t["bg_asst"])],
        )
        s.configure("Vertical.TScrollbar",
            background=t["bg_btn"], troughcolor=t["bg_input"],
            arrowcolor=t["fg_dim"],
            bordercolor=t["bg"], lightcolor=t["bg_btn"], darkcolor=t["bg_btn"],
            relief="flat",
        )
        s.map("Vertical.TScrollbar",
            background=[("active", t["fg_dim"]), ("disabled", t["bg_input"])],
            arrowcolor=[("active", t["fg"])],
        )
        # Combobox popup list colours (Tk option database)
        self.root.option_add("*TCombobox*Listbox.background",       t["bg_asst"],  "interactive")
        self.root.option_add("*TCombobox*Listbox.foreground",       t["fg"],       "interactive")
        self.root.option_add("*TCombobox*Listbox.selectBackground", t["bg_btn"],   "interactive")
        self.root.option_add("*TCombobox*Listbox.selectForeground", t["fg"],       "interactive")

    def _toggle_theme(self):
        self._theme_idx = (self._theme_idx + 1) % len(THEME_CYCLE)
        key = THEME_CYCLE[self._theme_idx]
        self._t = THEMES[key]
        self._apply_theme()
        # Button shows what you'll switch TO next (opposite of current)
        next_key = THEME_CYCLE[(self._theme_idx + 1) % len(THEME_CYCLE)]
        self.theme_btn.config(text=next_key.capitalize())

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        t = self._t

        # Chat scroll area
        chat_outer = self._sreg(tk.Frame(self.root, bg=t["bg"]), bg="bg")
        chat_outer.pack(fill="both", expand=True)

        vsb = ttk.Scrollbar(chat_outer, orient="vertical")
        vsb.pack(side="right", fill="y")

        self.canvas = tk.Canvas(chat_outer, bg=t["bg"],
                                yscrollcommand=vsb.set,
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=self.canvas.yview)

        self.inner = tk.Frame(self.canvas, bg=t["bg"])
        self.inner.columnconfigure(0, weight=1)
        self._cwin = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))

        # Prompt label + input
        self._sreg(
            tk.Label(self.root, text="Prompt", bg=t["bg"], fg=t["fg_dim"],
                     font=FONT, anchor="w"),
            bg="bg", fg="fg_dim",
        ).pack(fill="x", padx=14, pady=(6, 2))

        pf = self._sreg(tk.Frame(self.root, bg=t["bg_input"]), bg="bg_input")
        pf.pack(fill="x", padx=12, pady=(0, 6))

        self.prompt_box = self._sreg(
            tk.Text(pf, height=5, bg=t["bg_input"], fg=t["fg"],
                    insertbackground=t["fg"], font=FONT_MONO,
                    relief="flat", padx=10, pady=8, wrap="word"),
            bg="bg_input", fg="fg", insertbackground="fg",
        )
        self.prompt_box.pack(fill="x")
        self.prompt_box.bind("<Return>",       self._on_enter)
        self.prompt_box.bind("<Shift-Return>", lambda e: None)
        self.prompt_box.bind("<KeyRelease>",   self._on_prompt_change)
        self.prompt_box.bind("<<Paste>>",      lambda e: self.root.after(1, self._on_prompt_change))
        self.prompt_box.bind("<<Cut>>",        lambda e: self.root.after(1, self._on_prompt_change))
        self.prompt_box.focus_set()

        # Bottom bar
        bottom = self._sreg(tk.Frame(self.root, bg=t["bg"], pady=6), bg="bg")
        bottom.pack(fill="x", padx=12, pady=(0, 10))

        self._sreg(
            tk.Label(bottom, text="Model", bg=t["bg"], fg=t["fg_dim"], font=FONT),
            bg="bg", fg="fg_dim",
        ).pack(side="left")

        self.model_var = tk.StringVar(value=MODELS[0])
        self.model_cb = ttk.Combobox(
            bottom, textvariable=self.model_var,
            values=MODELS, width=44, font=FONT,
            state="readonly", style="Chat.TCombobox",
        )
        self.model_cb.pack(side="left", padx=(6, 0))

        # Send button (always blue/red — not theme-coloured)
        self.send_btn = tk.Button(
            bottom, text="Send", command=self._on_send_cancel,
            bg=BG_SEND, fg="#ffffff", font=FONT_BOLD,
            relief="flat", padx=16, pady=5, cursor="hand2",
            activebackground=BG_SEND, activeforeground="#ffffff",
        )
        self.send_btn.pack(side="right")

        # Reset button
        self.reset_btn = self._sreg(
            tk.Button(bottom, text="Reset", command=self._reset_prompt,
                      bg=t["bg_btn"], fg=t["fg_copy"], font=FONT,
                      relief="flat", padx=10, pady=5, cursor="hand2",
                      state="disabled",
                      activebackground=t["bg_btn"], activeforeground=t["fg"]),
            bg="bg_btn", fg="fg_copy", activebackground="bg_btn", activeforeground="fg",
        )
        self.reset_btn.pack(side="right", padx=(0, 6))

        # Theme toggle button
        self.theme_btn = self._sreg(
            tk.Button(bottom, text="Light", command=self._toggle_theme,
                      bg=t["bg_btn"], fg=t["fg_dim"], font=FONT,
                      relief="flat", padx=10, pady=5, cursor="hand2",
                      activebackground=t["bg_btn"], activeforeground=t["fg"]),
            bg="bg_btn", fg="fg_dim", activebackground="bg_btn", activeforeground="fg",
        )
        self.theme_btn.pack(side="right", padx=(0, 6))

    # ── Canvas / scroll ────────────────────────────────────────────────────────

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._cwin, width=event.width)
        wrap = max(200, int(event.width * 0.87))
        for lbl in self._resize_lbls:
            try:
                lbl.config(wraplength=wrap)
            except Exception:
                pass
        txt_w = max(30, int(event.width * 0.87 / CHAR_PX))
        for tw in self._resize_txts:
            try:
                tw.config(width=txt_w)
            except Exception:
                pass

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _scroll_bottom(self):
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(1.0)

    def _next_row(self):
        r = self._row_idx
        self._row_idx += 1
        return r

    # ── Prompt helpers ─────────────────────────────────────────────────────────

    def _on_prompt_change(self, event=None):
        has_text = bool(self.prompt_box.get("1.0", "end").strip())
        self.reset_btn.config(state="normal" if has_text else "disabled")

    def _reset_prompt(self):
        self.prompt_box.delete("1.0", "end")
        self._on_prompt_change()
        self.prompt_box.focus_set()

    # ── Widget factories ───────────────────────────────────────────────────────

    def _make_copy_btn(self, parent, get_text, side):
        t = self._t
        btn = self._dreg(
            tk.Button(parent, text="Copy",
                      command=lambda: (
                          self.root.clipboard_clear(),
                          self.root.clipboard_append(get_text()),
                      ),
                      bg=t["bg_btn"], fg=t["fg_copy"],
                      font=("Segoe UI", 8), relief="flat",
                      padx=6, pady=3, cursor="hand2",
                      activebackground=t["bg_btn"], activeforeground=t["fg"]),
            bg="bg_btn", fg="fg_copy",
            activebackground="bg_btn", activeforeground="fg",
        )
        btn.pack(side=side, padx=6, pady=(2, 6))
        return btn

    def _make_balloon_label(self, parent, text, bg_key):
        t = self._t
        canvas_w = self.canvas.winfo_width()
        wrap = max(200, int(canvas_w * 0.87)) if canvas_w > 1 else 700
        lbl = self._dreg(
            tk.Label(parent, text=text, bg=t[bg_key], fg=t["fg"],
                     font=FONT_MONO, wraplength=wrap,
                     justify="left", anchor="nw",
                     padx=12, pady=9),
            bg=bg_key, fg="fg",
        )
        self._resize_lbls.append(lbl)
        return lbl

    def _make_stream_text(self, parent):
        t = self._t
        canvas_w = self.canvas.winfo_width()
        txt_w = max(30, int(canvas_w * 0.87 / CHAR_PX)) if canvas_w > 1 else 100
        tw = self._dreg(
            tk.Text(parent, bg=t["bg_asst"], fg=t["fg"],
                    font=FONT_MONO, wrap="word",
                    width=txt_w, height=1,
                    relief="flat", borderwidth=0, highlightthickness=0,
                    padx=12, pady=9, cursor="arrow",
                    state="normal"),
            bg="bg_asst", fg="fg",
        )
        self._resize_txts.append(tw)
        return tw

    # ── Message rows ───────────────────────────────────────────────────────────

    def _hdr_row(self, text, anchor):
        """Thin label row above a balloon (e.g. 'Prompt', 'Response: (model)')."""
        t = self._t
        row = self._dreg(tk.Frame(self.inner, bg=t["bg"]), bg="bg")
        row.grid(row=self._next_row(), column=0, sticky="ew",
                 padx=PAD_X, pady=(8, 1))
        lbl = self._dreg(
            tk.Label(row, text=text, bg=t["bg"], fg=t["fg_dim"],
                     font=FONT_SMALL, anchor=anchor),
            bg="bg", fg="fg_dim",
        )
        lbl.pack(side="right" if anchor == "e" else "left")

    def add_user_message(self, text):
        """Flush-right balloon. Copy inside balloon at bottom-left."""
        t = self._t
        self._hdr_row("Prompt", "e")

        row = self._dreg(tk.Frame(self.inner, bg=t["bg"]), bg="bg")
        row.grid(row=self._next_row(), column=0, sticky="ew",
                 padx=PAD_X, pady=(0, 2))

        balloon = self._dreg(tk.Frame(row, bg=t["bg_user"]), bg="bg_user")
        lbl = self._make_balloon_label(balloon, text, "bg_user")
        lbl.pack(fill="both", expand=True)
        self._make_copy_btn(balloon, lambda: text, side="left")
        balloon.pack(side="right")

        self._scroll_bottom()

    def _add_status_row(self, text=""):
        t = self._t
        self._status_frame = self._dreg(tk.Frame(self.inner, bg=t["bg"]), bg="bg")
        self._status_frame.grid(row=self._next_row(), column=0, sticky="ew",
                                padx=PAD_X, pady=(0, 2))
        self._status_lbl = self._dreg(
            tk.Label(self._status_frame, text=text, bg=t["bg"],
                     fg=t["fg_dim"], font=FONT_SMALL, anchor="e"),
            bg="bg", fg="fg_dim",
        )
        self._status_lbl.pack(side="right")
        self._scroll_bottom()

    def _update_status(self, text):
        if self._status_lbl:
            self._status_lbl.config(text=text)

    def _remove_status_row(self):
        if self._status_frame:
            self._status_frame.destroy()
            self._status_frame = None
            self._status_lbl   = None

    def _begin_stream_balloon(self, model):
        """Create empty assistant balloon on first chunk. Runs on main thread."""
        self._remove_status_row()
        self._stop_timer()
        t = self._t

        self._hdr_row(f"Response: ({model})", "w")

        row = self._dreg(tk.Frame(self.inner, bg=t["bg"]), bg="bg")
        row.grid(row=self._next_row(), column=0, sticky="ew",
                 padx=PAD_X, pady=(0, 2))

        balloon = self._dreg(tk.Frame(row, bg=t["bg_asst"]), bg="bg_asst")
        balloon.pack(side="left")

        tw = self._make_stream_text(balloon)
        tw.pack(fill="both", expand=True)
        # Copy inside balloon at bottom-right — reads live content
        self._make_copy_btn(balloon, lambda: tw.get("1.0", "end-1c"), side="right")

        self._stream_widget = tw
        self._scroll_bottom()

    def _append_chunk(self, text):
        tw = self._stream_widget
        if tw is None or self._cancel_flag:
            return
        tw.insert("end", text)
        tw.update_idletasks()
        result = tw.count("1.0", "end", "displaylines")
        if result:
            tw.config(height=max(1, result[0]))
        self._scroll_bottom()

    def _end_stream(self, elapsed):
        if self._stream_widget:
            self._stream_widget.config(state="disabled")
        self._stream_widget = None
        self._sending = False
        self.send_btn.config(text="Send", bg=BG_SEND, activebackground=BG_SEND)
        t = self._t
        done_row = self._dreg(tk.Frame(self.inner, bg=t["bg"]), bg="bg")
        done_row.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=PAD_X, pady=(0, 8))
        self._dreg(
            tk.Label(done_row, text=f"Done · {elapsed}s",
                     bg=t["bg"], fg=t["fg_dim"], font=FONT_SMALL, anchor="w"),
            bg="bg", fg="fg_dim",
        ).pack(side="left")
        self._scroll_bottom()

    # ── Timer ──────────────────────────────────────────────────────────────────

    def _tick(self):
        if self._sending:
            elapsed = int(time.time() - self._start_time)
            self._update_status(f"Calling API… {elapsed}s")
            self._timer_id = self.root.after(1000, self._tick)

    def _stop_timer(self):
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None

    # ── Send / Cancel ──────────────────────────────────────────────────────────

    def _on_enter(self, event):
        if not (event.state & 0x1):
            self._on_send_cancel()
            return "break"

    def _on_send_cancel(self):
        if self._sending:
            self._cancel()
        else:
            self._send()

    def _send(self):
        prompt = self.prompt_box.get("1.0", "end").strip()
        if not prompt:
            return
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            messagebox.showerror("API Key Missing",
                                 "OPENROUTER_API_KEY not set.\n"
                                 "Add it to .env in the project root.")
            return

        self._current_model = self.model_var.get()
        self.prompt_box.delete("1.0", "end")
        self._on_prompt_change()

        self.add_user_message(prompt)
        self._add_status_row("Calling API… 0s")

        self._sending     = True
        self._cancel_flag = False
        self._start_time  = time.time()
        self.send_btn.config(text="Cancel", bg=BG_CANCEL, activebackground=BG_CANCEL)
        self._tick()

        threading.Thread(
            target=self._call_api,
            args=(api_key, self._current_model, prompt),
            daemon=True,
        ).start()

    def _cancel(self):
        self._cancel_flag = True
        self._stop_timer()
        self._sending = False
        self._stream_widget = None
        self._remove_status_row()
        self.send_btn.config(text="Send", bg=BG_SEND, activebackground=BG_SEND)

    # ── API (streaming) ────────────────────────────────────────────────────────

    def _call_api(self, api_key: str, model: str, prompt: str):
        try:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            balloon_created = False
            for chunk in stream:
                if self._cancel_flag:
                    break
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                if not balloon_created:
                    self.root.after(0, self._begin_stream_balloon, model)
                    balloon_created = True
                self.root.after(0, self._append_chunk, delta)

            if not self._cancel_flag:
                elapsed = int(time.time() - self._start_time)
                self.root.after(0, self._end_stream, elapsed)
        except Exception as exc:
            if not self._cancel_flag:
                self.root.after(0, self._on_error, str(exc))

    def _on_error(self, error: str):
        self._stop_timer()
        self._sending = False
        self._stream_widget = None
        self._remove_status_row()
        self.send_btn.config(text="Send", bg=BG_SEND, activebackground=BG_SEND)
        messagebox.showerror("API Error", error)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
