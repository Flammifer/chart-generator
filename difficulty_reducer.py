"""Generate Hard, Medium, and Easy charts from the Expert chart.

Rules based on community charting guides:
  Expert: all notes, 5 frets, 3-note chords, fast runs
  Hard:   5 frets, no 3-note chords, thin repetitive patterns
  Medium: 4 frets (no orange), skeleton rhythm
  Easy:   3 frets (G R Y), no chords, strong beats only
"""
from __future__ import annotations

from models import ChartNote, DifficultyChart, TICKS_PER_QUARTER, Fret
from config import ChartConfig, DifficultyConfig


def generate_all_difficulties(
    expert_notes: list[ChartNote],
    config: ChartConfig,
) -> dict[str, DifficultyChart]:
    return {
        "Expert": DifficultyChart(notes=expert_notes),
        "Hard": _reduce(expert_notes, config.hard, config),
        "Medium": _reduce(expert_notes, config.medium, config),
        "Easy": _reduce(expert_notes, config.easy, config),
    }


def _reduce(
    notes: list[ChartNote],
    diff: DifficultyConfig,
    config: ChartConfig,
) -> DifficultyChart:
    min_gap = config.gap_ticks(diff.min_gap)
    result: list[ChartNote] = []
    consecutive_short_count = 0
    prev_gap = -1

    for note in notes:
        if not _min_gap_ok(note, result, min_gap):
            continue

        if diff.thin_repeated_eighths and result:
            current_gap = note.tick - result[-1].tick
            if current_gap == prev_gap and current_gap <= TICKS_PER_QUARTER:
                consecutive_short_count += 1
            else:
                consecutive_short_count = 0
            prev_gap = current_gap

            if consecutive_short_count >= diff.max_consecutive_same_gap:
                if consecutive_short_count % 2 == 1:
                    continue

        frets = _cap_chord(note.frets, diff.max_chord_size)
        frets = _remap_to_max_fret(frets, diff.max_fret)

        if diff.max_fret < Fret.ORANGE:
            frets = _smooth_big_jumps(frets, result, max_jump=diff.max_fret)

        sustain = note.sustain_ticks if diff.allow_sustains else 0
        forced = note.is_forced if diff.allow_forced else False

        result.append(ChartNote(
            tick=note.tick,
            frets=frets,
            sustain_ticks=sustain,
            is_forced=forced,
            is_tap=note.is_tap,
        ))

    return DifficultyChart(notes=result)


def _cap_chord(frets: list[int], max_size: int) -> list[int]:
    if len(frets) <= max_size:
        return list(frets)
    if max_size == 1:
        return [frets[0]]
    return [frets[0], frets[-1]]


def _remap_to_max_fret(frets: list[int], max_fret: int) -> list[int]:
    if all(f <= max_fret for f in frets):
        return list(frets)
    if max_fret == 0:
        return [0] * len(frets)
    result = []
    for f in frets:
        if f <= max_fret:
            result.append(f)
        else:
            result.append(round(f * max_fret / Fret.ORANGE))
    return list(set(result)) or [0]


def _smooth_big_jumps(
    frets: list[int],
    prev_notes: list[ChartNote],
    max_jump: int = 3,
) -> list[int]:
    if not prev_notes or not frets or not prev_notes[-1].frets:
        return frets
    prev_fret = prev_notes[-1].frets[0]
    jump = abs(frets[0] - prev_fret)
    if jump > max_jump:
        direction = 1 if frets[0] > prev_fret else -1
        overshoot = jump - max_jump
        shifted = [max(0, min(Fret.ORANGE, f - direction * overshoot)) for f in frets]
        return shifted
    return frets


def _min_gap_ok(note: ChartNote, prev_notes: list[ChartNote], min_gap: int) -> bool:
    if not prev_notes:
        return True
    return note.tick - prev_notes[-1].tick >= min_gap
