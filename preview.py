"""Audio-synced chart preview for visual offset adjustment."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from models import ParsedSong, ChartNote, SoloRegion, TICKS_PER_QUARTER

try:
    import pygame
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False

FRET_COLORS = ("#22cc22", "#cc2222", "#cccc22", "#2266cc", "#ff8822")
FRET_LABELS = ("G", "R", "Y", "B", "O")
LANE_HEIGHT = 26
TOP_PADDING = 10
CANVAS_HEIGHT = LANE_HEIGHT * 5 + TOP_PADDING * 2
NOTE_RADIUS = 5
PIXELS_PER_MS = 0.15
CURSOR_INTERVAL_MS = 25
LABEL_AREA_PX = 24


class _PreviewNote:
    __slots__ = ("time_ms", "frets", "sustain_ms")

    def __init__(self, time_ms: float, frets: list[int], sustain_ms: float):
        self.time_ms = time_ms
        self.frets = frets
        self.sustain_ms = sustain_ms


def build_preview_notes(
    expert_notes: list[ChartNote],
    song: ParsedSong,
) -> list[_PreviewNote]:
    tempo_map = _build_tempo_map(song)
    result: list[_PreviewNote] = []
    for note in expert_notes:
        t = _tick_to_ms(note.tick, tempo_map)
        sus = _tick_to_ms(note.tick + note.sustain_ticks, tempo_map) - t if note.sustain_ticks else 0
        result.append(_PreviewNote(t, note.frets, sus))
    return result


def build_solo_regions_ms(
    solo_regions: list[SoloRegion],
    song: ParsedSong,
) -> list[tuple[float, float]]:
    tempo_map = _build_tempo_map(song)
    return [
        (_tick_to_ms(r.start_tick, tempo_map), _tick_to_ms(r.end_tick, tempo_map))
        for r in solo_regions
    ]


def _build_tempo_map(song: ParsedSong) -> list[tuple[int, float]]:
    result = []
    for tc in song.tempo_changes:
        tick = song.bar_start_tick(tc.bar_index)
        result.append((tick, tc.bpm))
    result.sort()
    if not result:
        result.append((0, 120.0))
    return result


def _tick_to_ms(tick: int, tempo_map: list[tuple[int, float]]) -> float:
    ms = 0.0
    prev_tick = 0
    prev_bpm = tempo_map[0][1]

    for map_tick, bpm in tempo_map:
        if map_tick > tick:
            break
        delta = map_tick - prev_tick
        if delta > 0:
            ms += delta * 60000.0 / (prev_bpm * TICKS_PER_QUARTER)
        prev_tick = map_tick
        prev_bpm = bpm

    remaining = tick - prev_tick
    if remaining > 0:
        ms += remaining * 60000.0 / (prev_bpm * TICKS_PER_QUARTER)

    return ms


SPEED_OPTIONS = (0.25, 0.5, 0.75, 1.0)
BASE_SAMPLE_RATE = 44100


class PreviewWindow(tk.Toplevel):

    def __init__(
        self,
        parent: tk.Tk,
        notes: list[_PreviewNote],
        solo_regions_ms: list[tuple[float, float]],
        audio_path: str | None,
        offset_var: tk.IntVar,
        on_apply: callable,
    ):
        super().__init__(parent)
        self.title("Preview — offset adjustment")
        self._notes = notes
        self._solos_ms = solo_regions_ms
        self._audio_path = audio_path
        self._offset_var = offset_var
        self._on_apply = on_apply

        self._playing = False
        self._paused = False
        self._origin_time = 0.0
        self._origin_ms = 0.0
        self._speed = 1.0
        self._cursor_job: str | None = None
        self._audio_ok = False

        if notes:
            last = max(notes, key=lambda n: n.time_ms + n.sustain_ms)
            self._duration_ms = last.time_ms + last.sustain_ms + 3000
        else:
            self._duration_ms = 10000

        self._total_px = max(int(self._duration_ms * PIXELS_PER_MS), 900)

        self._init_audio()
        self._build_ui()
        self._draw_all()
        self._offset_var.trace_add("write", self._on_offset_trace)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_audio(self) -> None:
        if not _HAS_PYGAME or not self._audio_path:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100)
            pygame.mixer.music.load(self._audio_path)
            self._audio_ok = True
        except Exception:
            self._audio_ok = False

    def _build_ui(self) -> None:
        self.resizable(True, False)
        self.minsize(700, 260)
        self.geometry("1000x260")

        ctrl = ttk.Frame(self, padding=(8, 6))
        ctrl.pack(fill="x")

        self._play_btn = ttk.Button(ctrl, text="▶  Play", command=self._toggle_play, width=10)
        self._play_btn.pack(side="left", padx=4)

        ttk.Button(ctrl, text="⏹  Stop", command=self._stop, width=10).pack(side="left", padx=4)

        self._time_lbl = ttk.Label(ctrl, text="0:00 / 0:00", width=14,
                                   font=("Consolas", 10))
        self._time_lbl.pack(side="left", padx=12)

        ttk.Separator(ctrl, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(ctrl, text="Speed:").pack(side="left", padx=(0, 4))
        self._speed_str = tk.StringVar(value="1x")
        speed_combo = ttk.Combobox(
            ctrl, textvariable=self._speed_str, width=5, state="readonly",
            values=[f"{s:.2g}x" for s in SPEED_OPTIONS],
        )
        speed_combo.pack(side="left")
        speed_combo.bind("<<ComboboxSelected>>", self._on_speed_change)

        ttk.Separator(ctrl, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(ctrl, text="Offset (ms):").pack(side="left", padx=(0, 4))
        spin = ttk.Spinbox(
            ctrl, from_=-30000, to=30000, increment=50,
            textvariable=self._offset_var, width=8,
        )
        spin.pack(side="left")

        ttk.Button(ctrl, text="Apply & Re-export",
                   command=self._on_apply).pack(side="right", padx=8)

        if not self._audio_ok:
            ttk.Label(ctrl, text="(no audio)",
                      foreground="gray").pack(side="right", padx=8)

        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(
            canvas_frame, height=CANVAS_HEIGHT,
            bg="#0e0e1a", highlightthickness=0,
        )
        self._hscroll = ttk.Scrollbar(canvas_frame, orient="horizontal",
                                      command=self._canvas.xview)
        self._canvas.configure(
            xscrollcommand=self._hscroll.set,
            scrollregion=(0, 0, self._total_px, CANVAS_HEIGHT),
        )
        self._hscroll.pack(side="bottom", fill="x")
        self._canvas.pack(side="top", fill="both", expand=True)

        for i, label in enumerate(FRET_LABELS):
            y = self._lane_y(i)
            self._canvas.create_line(
                LABEL_AREA_PX, y, self._total_px, y,
                fill="#1a1a30", tags="grid",
            )
            self._canvas.create_text(
                4, y, text=label, fill=FRET_COLORS[i],
                font=("Consolas", 9, "bold"), anchor="w", tags="grid",
            )

        self._cursor = self._canvas.create_line(
            0, 0, 0, CANVAS_HEIGHT, fill="#ffffff", width=2,
        )

        self._canvas.bind("<Button-1>", self._on_click)

    def _lane_y(self, fret_idx: int) -> int:
        return TOP_PADDING + fret_idx * LANE_HEIGHT + LANE_HEIGHT // 2

    def _draw_all(self) -> None:
        self._canvas.delete("note")
        self._canvas.delete("solo_bg")

        try:
            offset = self._offset_var.get()
        except (tk.TclError, ValueError):
            offset = 0

        for s_start, s_end in self._solos_ms:
            x0 = (s_start + offset) * PIXELS_PER_MS
            x1 = (s_end + offset) * PIXELS_PER_MS
            self._canvas.create_rectangle(
                x0, 0, x1, CANVAS_HEIGHT,
                fill="#1a0a2e", outline="", tags="solo_bg",
            )

        for note in self._notes:
            x = (note.time_ms + offset) * PIXELS_PER_MS
            for fret in note.frets:
                if not (0 <= fret <= 4):
                    continue
                y = self._lane_y(fret)
                color = FRET_COLORS[fret]

                if note.sustain_ms > 0:
                    x_end = (note.time_ms + offset + note.sustain_ms) * PIXELS_PER_MS
                    self._canvas.create_rectangle(
                        x, y - 3, x_end, y + 3,
                        fill=color, outline="", tags="note",
                    )

                r = NOTE_RADIUS
                self._canvas.create_oval(
                    x - r, y - r, x + r, y + r,
                    fill=color, outline="#ffffff", width=1, tags="note",
                )

        self._canvas.tag_raise(self._cursor)

    def _on_offset_trace(self, *_args) -> None:
        self._draw_all()

    def _on_speed_change(self, _event: tk.Event) -> None:
        new_speed = float(self._speed_str.get().rstrip("x"))
        if new_speed == self._speed:
            return

        was_playing = self._playing or self._paused
        current_song_ms = self._current_song_ms()

        if self._audio_ok:
            pygame.mixer.music.stop()
        self._cancel_cursor()
        self._playing = False
        self._paused = False

        self._speed = new_speed
        self._reinit_mixer_for_speed()
        self._origin_ms = current_song_ms

        if was_playing:
            self._start_playback_from(current_song_ms)
        else:
            x = current_song_ms * PIXELS_PER_MS
            self._canvas.coords(self._cursor, x, 0, x, CANVAS_HEIGHT)

    def _reinit_mixer_for_speed(self) -> None:
        if not _HAS_PYGAME or not self._audio_path:
            return
        try:
            pygame.mixer.quit()
            freq = max(8000, int(BASE_SAMPLE_RATE * self._speed))
            pygame.mixer.init(frequency=freq)
            pygame.mixer.music.load(self._audio_path)
            self._audio_ok = True
        except Exception:
            self._audio_ok = False

    def _current_song_ms(self) -> float:
        if not self._playing:
            return self._origin_ms
        if self._audio_ok:
            pos = pygame.mixer.music.get_pos()
            if pos >= 0:
                return self._origin_ms + pos * self._speed
        elapsed_real = (time.perf_counter() - self._origin_time) * 1000
        return self._origin_ms + elapsed_real * self._speed

    def _toggle_play(self) -> None:
        if self._playing:
            self._pause()
        else:
            self._play()

    def _play(self) -> None:
        if not self._audio_ok:
            return
        if self._paused:
            self._resume()
        else:
            self._start_playback_from(self._origin_ms)

    def _resume(self) -> None:
        self._playing = True
        self._paused = False
        self._play_btn.configure(text="⏸ Pause")
        pygame.mixer.music.unpause()
        self._schedule_cursor()

    def _start_playback_from(self, song_ms: float) -> None:
        if not self._audio_ok:
            return
        self._playing = True
        self._paused = False
        self._play_btn.configure(text="⏸ Pause")
        self._origin_ms = song_ms

        start_sec = max(0, song_ms / 1000.0)
        try:
            pygame.mixer.music.play(start=start_sec)
        except Exception:
            pygame.mixer.music.play()
        self._origin_time = time.perf_counter()

        self._schedule_cursor()

    def _pause(self) -> None:
        self._playing = False
        self._paused = True
        self._play_btn.configure(text="▶  Play")
        self._origin_ms = self._current_song_ms()

        if self._audio_ok:
            pygame.mixer.music.pause()
        self._cancel_cursor()

    def _stop(self) -> None:
        self._playing = False
        self._paused = False
        self._play_btn.configure(text="▶  Play")
        self._origin_ms = 0.0

        if self._audio_ok:
            pygame.mixer.music.stop()
        self._cancel_cursor()

        self._canvas.coords(self._cursor, 0, 0, 0, CANVAS_HEIGHT)
        self._time_lbl.configure(text=self._format_time(0))

    def _schedule_cursor(self) -> None:
        self._cancel_cursor()
        self._cursor_job = self.after(CURSOR_INTERVAL_MS, self._update_cursor)

    def _cancel_cursor(self) -> None:
        if self._cursor_job:
            self.after_cancel(self._cursor_job)
            self._cursor_job = None

    def _update_cursor(self) -> None:
        if not self._playing:
            return

        current_ms = self._current_song_ms()

        if current_ms >= self._duration_ms:
            self._stop()
            return

        x = current_ms * PIXELS_PER_MS
        self._canvas.coords(self._cursor, x, 0, x, CANVAS_HEIGHT)

        visible_w = self._canvas.winfo_width()
        scroll_left = x - visible_w * 0.3
        frac = max(0.0, scroll_left / self._total_px)
        self._canvas.xview_moveto(frac)

        self._time_lbl.configure(text=self._format_time(current_ms))

        self._cursor_job = self.after(CURSOR_INTERVAL_MS, self._update_cursor)

    def _format_time(self, ms: float) -> str:
        cur = int(ms / 1000)
        total = int(self._duration_ms / 1000)
        return f"{cur // 60}:{cur % 60:02d} / {total // 60}:{total % 60:02d}"

    def _on_click(self, event: tk.Event) -> None:
        canvas_x = self._canvas.canvasx(event.x)
        target_ms = max(0, canvas_x / PIXELS_PER_MS)
        target_ms = min(target_ms, self._duration_ms)

        was_active = self._playing or self._paused
        if self._audio_ok:
            pygame.mixer.music.stop()
        self._cancel_cursor()
        self._playing = False
        self._paused = False
        self._origin_ms = target_ms

        if was_active:
            self._start_playback_from(target_ms)
        else:
            x = target_ms * PIXELS_PER_MS
            self._canvas.coords(self._cursor, x, 0, x, CANVAS_HEIGHT)
            self._time_lbl.configure(text=self._format_time(target_ms))

    def _on_close(self) -> None:
        self._cancel_cursor()
        if _HAS_PYGAME and pygame.mixer.get_init():
            pygame.mixer.music.stop()
            if self._speed != 1.0:
                pygame.mixer.quit()
                pygame.mixer.init(frequency=BASE_SAMPLE_RATE)
        self.destroy()
