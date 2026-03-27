"""Map MIDI pitches to 5 GH frets (0=Green .. 4=Orange).

Core principles from the GH charting community:
  - Green = lowest pitch, Orange = highest
  - Mapping is relative to the phrase, not global
  - When a phrase has ≤5 unique pitches: direct 1:1 mapping spread across frets
  - When >5: use "wrapping" — sliding windows that restart fret direction
  - Chords map based on interval width between root and highest note
"""
from __future__ import annotations

from dataclasses import dataclass
from models import SongNote, ChartNote, Fret
from phrase_splitter import Phrase

MAX_FRETS = 5


def map_phrase_to_chart_notes(phrase: Phrase) -> list[ChartNote]:
    """Convert a phrase of SongNotes into ChartNotes with fret assignments."""
    result: list[ChartNote] = []

    for note in phrase.notes:
        if note.is_tie:
            continue

        if len(note.midi_pitches) == 1:
            frets = [_map_single_pitch(note.midi_pitches[0], phrase)]
        else:
            frets = _map_chord(note.midi_pitches, phrase)

        result.append(ChartNote(
            tick=note.tick,
            frets=sorted(set(frets)),
            sustain_ticks=_compute_sustain(note),
            is_forced=note.is_hammer_on,
        ))

    return result


def _map_single_pitch(midi: int, phrase: Phrase) -> int:
    unique_pitches = _unique_pitches_in_phrase(phrase)

    if len(unique_pitches) <= MAX_FRETS:
        return _direct_map(midi, unique_pitches)
    else:
        return _proportional_map(midi, unique_pitches)


def _direct_map(midi: int, unique_pitches: list[int]) -> int:
    """≤5 unique pitches: spread across frets with proportional spacing."""
    if len(unique_pitches) == 1:
        return Fret.YELLOW

    idx = unique_pitches.index(midi)
    fret = round(idx * (MAX_FRETS - 1) / (len(unique_pitches) - 1))
    return fret


def _proportional_map(midi: int, unique_pitches: list[int]) -> int:
    """Map using proportional position in the full pitch range."""
    lo, hi = unique_pitches[0], unique_pitches[-1]
    if lo == hi:
        return Fret.YELLOW

    proportion = (midi - lo) / (hi - lo)
    fret = round(proportion * (MAX_FRETS - 1))
    return max(0, min(MAX_FRETS - 1, fret))


def _map_chord(midi_pitches: list[int], phrase: Phrase) -> list[int]:
    """Map a chord to GH frets based on interval width and phrase context.

    Interval rules from charting guides:
      - 1-3 semitones (small): adjacent frets (1-2 gap)
      - 4-7 semitones (medium): skip one fret (1-3 gap)
      - 8+ semitones (large): skip two frets (1-4 gap)
      - 3+ note chord with wide voicing: 3-note GH chord
    """
    sorted_pitches = sorted(midi_pitches)
    root = sorted_pitches[0]
    top = sorted_pitches[-1]
    interval = top - root

    root_fret = _map_single_pitch(root, phrase)

    if len(sorted_pitches) >= 3 and interval >= 7:
        return _three_note_chord(root_fret, interval)

    if interval <= 3:
        gap = 1
    elif interval <= 7:
        gap = 2
    else:
        gap = 3

    second_fret = min(root_fret + gap, Fret.ORANGE)
    if second_fret == root_fret:
        second_fret = max(root_fret - gap, Fret.GREEN)

    return [root_fret, second_fret]


def _three_note_chord(root_fret: int, interval: int) -> list[int]:
    """Create a 3-note GH chord anchored at root_fret."""
    if root_fret <= 1:
        return [root_fret, root_fret + 1, root_fret + 2]
    elif root_fret >= 3:
        return [root_fret - 2, root_fret - 1, root_fret]
    else:
        return [root_fret - 1, root_fret, root_fret + 1]


def _unique_pitches_in_phrase(phrase: Phrase) -> list[int]:
    pitches = set()
    for note in phrase.notes:
        if not note.is_tie:
            pitches.update(note.midi_pitches)
    return sorted(pitches)


def _compute_sustain(note: SongNote) -> int:
    """Only keep sustain for notes longer than an eighth note."""
    EIGHTH = 96
    if note.duration_ticks > EIGHTH:
        return note.duration_ticks
    return 0
