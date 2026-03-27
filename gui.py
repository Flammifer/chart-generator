"""Minimal GUI for GP-to-YARG chart generation."""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from pipeline import generate_chart, re_export_with_offset, GenerationResult
from preview import PreviewWindow, build_preview_notes, build_solo_regions_ms
from config import ChartConfig

FILETYPES_GP = [("Guitar Pro", "*.gp *.gp3 *.gp4 *.gp5 *.gpx"), ("All", "*.*")]
FILETYPES_AUDIO = [("Audio", "*.mp3 *.ogg *.opus *.wav"), ("All", "*.*")]


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("GP → YARG Chart Generator")
        self.resizable(False, False)
        self.config_ = self._load_config()
        self._last_result: GenerationResult | None = None
        self._last_audio_path: str | None = None
        self._build_ui()
        self._center_window()

    def _load_config(self) -> ChartConfig:
        path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.isfile(path):
            return ChartConfig.load(path)
        return ChartConfig()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 4}
        main = ttk.Frame(self, padding=16)
        main.pack()

        # ── File selectors ──
        file_frame = ttk.LabelFrame(main, text="Files", padding=8)
        file_frame.pack(fill="x", **pad)

        ttk.Label(file_frame, text="Guitar Pro tab:").grid(row=0, column=0, sticky="w")
        self.gp_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.gp_var, width=52).grid(row=0, column=1, padx=4)
        ttk.Button(file_frame, text="...", width=3, command=self._browse_gp).grid(row=0, column=2)

        ttk.Label(file_frame, text="Audio (mp3/ogg):").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.audio_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.audio_var, width=52).grid(row=1, column=1, padx=4, pady=(4, 0))
        ttk.Button(file_frame, text="...", width=3, command=self._browse_audio).grid(row=1, column=2, pady=(4, 0))

        # ── Settings ──
        set_frame = ttk.LabelFrame(main, text="Settings", padding=8)
        set_frame.pack(fill="x", **pad)

        ttk.Label(set_frame, text="Export folder:").grid(row=0, column=0, sticky="w")
        self.output_var = tk.StringVar(value=self.config_.output_dir)
        ttk.Entry(set_frame, textvariable=self.output_var, width=42).grid(row=0, column=1, padx=4)
        ttk.Button(set_frame, text="...", width=3, command=self._browse_output).grid(row=0, column=2)

        ttk.Label(set_frame, text="Audio offset (ms):").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.offset_var = tk.IntVar(value=self.config_.audio_offset_ms)
        offset_frame = ttk.Frame(set_frame)
        offset_frame.grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))
        self.offset_spin = ttk.Spinbox(
            offset_frame, from_=-30000, to=30000, increment=100,
            textvariable=self.offset_var, width=8,
        )
        self.offset_spin.pack(side="left")
        ttk.Label(offset_frame, text="(+ = ноты позже, − = ноты раньше)",
                  font=("Segoe UI", 8)).pack(side="left", padx=(6, 0))

        # ── Buttons ──
        btn_frame = ttk.Frame(main)
        btn_frame.pack(pady=(8, 4))

        self.generate_btn = ttk.Button(btn_frame, text="Generate Chart", command=self._on_generate)
        self.generate_btn.pack(side="left", padx=4)

        self.preview_btn = ttk.Button(btn_frame, text="Preview", command=self._on_preview,
                                      state="disabled")
        self.preview_btn.pack(side="left", padx=4)

        # ── Progress ──
        self.progress = ttk.Progressbar(main, mode="indeterminate", length=400)
        self.progress.pack(pady=(0, 4))

        # ── Log ──
        self.log_text = tk.Text(main, height=12, width=62,
                                font=("Consolas", 9), bg="#1e1e1e", fg="#cccccc")
        self.log_text.pack(**pad)
        self.log_text.bind("<Key>", lambda e: "break")

    def _center_window(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _browse_gp(self) -> None:
        path = filedialog.askopenfilename(filetypes=FILETYPES_GP)
        if path:
            self.gp_var.set(path)
            if not self.audio_var.get():
                self._try_find_audio(path)

    def _browse_audio(self) -> None:
        path = filedialog.askopenfilename(filetypes=FILETYPES_AUDIO)
        if path:
            self.audio_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_var.get() or None)
        if path:
            self.output_var.set(path)

    def _try_find_audio(self, gp_path: str) -> None:
        """Auto-detect audio file next to the GP file."""
        folder = os.path.dirname(gp_path)
        stem = os.path.splitext(os.path.basename(gp_path))[0]
        for ext in (".mp3", ".ogg", ".opus", ".wav"):
            for candidate in (os.path.join(folder, stem + ext),
                              os.path.join(folder, "song" + ext)):
                if os.path.isfile(candidate):
                    self.audio_var.set(candidate)
                    return

    def _log(self, msg: str) -> None:
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _on_generate(self) -> None:
        gp_path = self.gp_var.get().strip()
        audio_path = self.audio_var.get().strip() or None
        output_base = self.output_var.get().strip() or None

        if not gp_path:
            self._log("Select a Guitar Pro file first.")
            return
        if not os.path.isfile(gp_path):
            self._log(f"GP file not found: {gp_path}")
            return

        self.log_text.delete("1.0", "end")

        self.generate_btn.config(state="disabled")
        self.progress.start(15)

        config = ChartConfig.load(os.path.join(os.path.dirname(__file__), "config.json")) \
            if os.path.isfile(os.path.join(os.path.dirname(__file__), "config.json")) \
            else ChartConfig()

        if output_base:
            config.output_dir = output_base

        try:
            config.audio_offset_ms = self.offset_var.get()
        except tk.TclError:
            config.audio_offset_ms = 0

        thread = threading.Thread(
            target=self._run_generation,
            args=(gp_path, audio_path, config),
            daemon=True,
        )
        thread.start()

    def _run_generation(self, gp_path: str, audio_path: str | None, config: ChartConfig) -> None:
        def log_from_thread(msg: str) -> None:
            self.after(0, self._log, msg)

        result = generate_chart(
            gp_path=gp_path,
            audio_path=audio_path,
            config=config,
            on_progress=log_from_thread,
        )

        def finish() -> None:
            self.progress.stop()
            self.generate_btn.config(state="normal")

            if result.error:
                self._log(f"\nERROR: {result.error}")
                return

            self._last_result = result
            self._last_audio_path = audio_path
            self.preview_btn.config(state="normal")

            self._log(f"\n{'='*50}")
            self._log(f"{result.song_artist} - {result.song_title}")
            self._log(f"BPM: {result.bpm}  |  Bars: {result.total_bars}")
            self._log(f"Expert: {result.expert_notes}  Hard: {result.hard_notes}  "
                       f"Medium: {result.medium_notes}  Easy: {result.easy_notes}")
            self._log(f"Solos: {result.solo_count}")
            if config.audio_offset_ms:
                self._log(f"Audio offset: {config.audio_offset_ms} ms")
            self._log(f"Output: {result.output_dir}")
            if audio_path:
                self._log(f"Audio copied: {os.path.basename(audio_path)} → {config.audio_filename or 'song.mp3'}")
            else:
                self._log("No audio file — add song.mp3 to output folder manually.")

        self.after(0, finish)


    def _on_preview(self) -> None:
        res = self._last_result
        if not res or not res._song or not res._expert_chart_notes:
            self._log("Generate a chart first.")
            return

        preview_notes = build_preview_notes(res._expert_chart_notes, res._song)
        solo_ms = build_solo_regions_ms(res._solo_regions, res._song)

        audio_for_preview = self._last_audio_path
        if not audio_for_preview and res.output_dir:
            candidate = os.path.join(res.output_dir, res._audio_filename)
            if os.path.isfile(candidate):
                audio_for_preview = candidate

        PreviewWindow(
            parent=self,
            notes=preview_notes,
            solo_regions_ms=solo_ms,
            audio_path=audio_for_preview,
            offset_var=self.offset_var,
            on_apply=self._on_re_export,
        )

    def _on_re_export(self) -> None:
        res = self._last_result
        if not res:
            return

        try:
            offset = self.offset_var.get()
        except tk.TclError:
            offset = 0

        try:
            re_export_with_offset(res, offset, self._last_audio_path)
            self._log(f"Re-exported with offset={offset} ms → {res.output_dir}")
        except Exception as e:
            self._log(f"Re-export error: {e}")


if __name__ == "__main__":
    App().mainloop()
