"""Configuration for chart generation.

All timing values are in fractions of a quarter note:
  1.0 = quarter, 0.5 = eighth, 0.25 = 16th, 2.0 = half, etc.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from models import TICKS_PER_QUARTER


@dataclass
class DifficultyConfig:
    min_gap: float
    max_chord_size: int
    max_fret: int
    allow_forced: bool
    allow_sustains: bool
    thin_repeated_eighths: bool
    max_consecutive_same_gap: int


@dataclass
class ChartConfig:
    hard: DifficultyConfig = field(default_factory=lambda: DifficultyConfig(
        min_gap=0.5,
        max_chord_size=2,
        max_fret=4,
        allow_forced=True,
        allow_sustains=True,
        thin_repeated_eighths=True,
        max_consecutive_same_gap=4,
    ))
    medium: DifficultyConfig = field(default_factory=lambda: DifficultyConfig(
        min_gap=1.0,
        max_chord_size=2,
        max_fret=3,
        allow_forced=False,
        allow_sustains=True,
        thin_repeated_eighths=False,
        max_consecutive_same_gap=999,
    ))
    easy: DifficultyConfig = field(default_factory=lambda: DifficultyConfig(
        min_gap=2.0,
        max_chord_size=1,
        max_fret=2,
        allow_forced=False,
        allow_sustains=False,
        thin_repeated_eighths=False,
        max_consecutive_same_gap=999,
    ))

    output_dir: str = ""
    audio_filename: str = "song.ogg"
    audio_offset_ms: int = 0

    star_power_interval_bars: int = 12
    star_power_duration_bars: int = 3
    phrase_bar_group_size: int = 4
    merge_bar_window: int = 2
    solo_sensitivity: float = 2.5

    def gap_ticks(self, gap_quarters: float) -> int:
        return int(gap_quarters * TICKS_PER_QUARTER)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> ChartConfig:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        cfg = cls()
        for diff_name in ("hard", "medium", "easy"):
            if diff_name in data:
                diff_data = data[diff_name]
                setattr(cfg, diff_name, DifficultyConfig(**diff_data))
        for key in ("output_dir", "audio_filename", "audio_offset_ms",
                     "star_power_interval_bars", "star_power_duration_bars",
                     "phrase_bar_group_size", "merge_bar_window",
                     "solo_sensitivity"):
            if key in data:
                setattr(cfg, key, data[key])
        return cfg
