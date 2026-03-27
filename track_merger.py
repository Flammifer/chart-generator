"""Merge multiple guitar tracks into a single stream for charting.

Strategy:
  - During solo regions: ALWAYS use Lead guitar
  - Lead guitar takes priority when it has melodic content (varied pitches)
  - Rhythm guitar fills in when lead is resting or playing sustains
"""
from __future__ import annotations

from models import SongNote, ParsedSong, ParsedTrack, SoloRegion


def find_guitar_tracks(song: ParsedSong) -> tuple[ParsedTrack | None, ParsedTrack | None]:
    lead = None
    rhythm = None
    for track in song.tracks:
        if track.instrument_type not in ("electricGuitar", "acousticGuitar"):
            continue
        name_lower = track.name.lower()
        if "lead" in name_lower or "solo" in name_lower:
            lead = track
        elif "rhy" in name_lower or "rhythm" in name_lower:
            rhythm = track
        elif lead is None:
            lead = track
        elif rhythm is None:
            rhythm = track
    return lead, rhythm


def merge_tracks(
    song: ParsedSong,
    bar_window: int = 2,
    solo_regions: list[SoloRegion] | None = None,
) -> list[SongNote]:
    lead, rhythm = find_guitar_tracks(song)

    if lead is None and rhythm is None:
        raise ValueError("No guitar tracks found in the song")
    if lead is None:
        return rhythm.notes
    if rhythm is None:
        return lead.notes

    merged: list[SongNote] = []

    for bar_start_idx in range(0, song.total_bars, bar_window):
        bar_end_idx = min(bar_start_idx + bar_window, song.total_bars)
        tick_start = song.bar_start_tick(bar_start_idx)
        tick_end = song.bar_start_tick(bar_end_idx) if bar_end_idx < song.total_bars else float("inf")

        lead_notes = _notes_in_range(lead.notes, tick_start, tick_end)
        rhythm_notes = _notes_in_range(rhythm.notes, tick_start, tick_end)

        if solo_regions and _overlaps_solo(tick_start, tick_end, solo_regions):
            chosen = lead_notes if lead_notes else rhythm_notes
        else:
            chosen = _choose_track_notes(lead_notes, rhythm_notes)

        merged.extend(chosen)

    merged.sort(key=lambda n: n.tick)
    return merged


def _overlaps_solo(tick_start: int, tick_end: float, regions: list[SoloRegion]) -> bool:
    for r in regions:
        if tick_start < r.end_tick and tick_end > r.start_tick:
            return True
    return False


def _notes_in_range(notes: list[SongNote], start: int, end: float) -> list[SongNote]:
    return [n for n in notes if start <= n.tick < end and not n.is_tie]


def _choose_track_notes(
    lead_notes: list[SongNote],
    rhythm_notes: list[SongNote],
) -> list[SongNote]:
    if not lead_notes and not rhythm_notes:
        return []
    if not lead_notes:
        return rhythm_notes
    if not rhythm_notes:
        return lead_notes

    lead_variety = _pitch_variety(lead_notes)
    rhythm_variety = _pitch_variety(rhythm_notes)

    lead_is_melodic = lead_variety >= 2
    rhythm_is_chords = any(len(n.midi_pitches) > 1 for n in rhythm_notes)

    if lead_is_melodic:
        return lead_notes
    if rhythm_is_chords:
        return rhythm_notes

    return lead_notes if lead_variety >= rhythm_variety else rhythm_notes


def _pitch_variety(notes: list[SongNote]) -> int:
    all_pitches = set()
    for n in notes:
        all_pitches.update(n.midi_pitches)
    return len(all_pitches)
