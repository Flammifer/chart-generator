"""Auto-detect song sections when GP file has no section markers.

Uses heuristics based on musical structure:
  - Changes in note density (sparse → dense = new section)
  - Changes in pitch register (low → high = new section)
  - Changes in chord vs single-note patterns
  - Regular phrase groupings as fallback
"""
from __future__ import annotations

from models import SongNote, ParsedSong, ChartEvent, TICKS_PER_QUARTER


ANALYSIS_WINDOW_BARS = 8
MIN_SECTION_GAP_BARS = 8


def detect_sections(
    notes: list[SongNote],
    song: ParsedSong,
) -> list[ChartEvent]:
    if song.sections:
        return [
            ChartEvent(
                tick=song.bar_start_tick(s.bar_index),
                event_type="section",
                value=s.name,
            )
            for s in song.sections
        ]

    return _auto_detect(notes, song)


def _auto_detect(notes: list[SongNote], song: ParsedSong) -> list[ChartEvent]:
    if not notes:
        return []

    bar_features = _compute_bar_features(notes, song)
    change_points = _find_change_points(bar_features)

    sections: list[ChartEvent] = []
    section_names = _generate_section_names(change_points, song.total_bars)

    for bar_idx, name in section_names:
        tick = song.bar_start_tick(bar_idx)
        sections.append(ChartEvent(tick=tick, event_type="section", value=name))

    if not sections:
        sections.append(ChartEvent(tick=0, event_type="section", value="intro"))

    return sections


def _compute_bar_features(
    notes: list[SongNote],
    song: ParsedSong,
) -> dict[int, dict]:
    features: dict[int, dict] = {}

    for bar_idx in range(song.total_bars):
        start = song.bar_start_tick(bar_idx)
        ts = song._time_sig_at_bar(bar_idx)
        end = start + ts.ticks_per_bar

        bar_notes = [n for n in notes if start <= n.tick < end and not n.is_tie]

        unique_pitches = set()
        is_chord = False
        for n in bar_notes:
            unique_pitches.update(n.midi_pitches)
            if len(n.midi_pitches) > 1:
                is_chord = True

        avg_pitch = sum(unique_pitches) / len(unique_pitches) if unique_pitches else 0

        features[bar_idx] = {
            "density": len(bar_notes),
            "pitch_variety": len(unique_pitches),
            "avg_pitch": avg_pitch,
            "has_chords": is_chord,
        }

    return features


def _find_change_points(features: dict[int, dict]) -> list[int]:
    """Find bars where the musical character changes significantly."""
    change_points = [0]
    bars = sorted(features.keys())

    for i in range(ANALYSIS_WINDOW_BARS, len(bars)):
        current = features[bars[i]]
        prev_window = [features[bars[j]] for j in range(i - ANALYSIS_WINDOW_BARS, i)]

        avg_prev_density = sum(f["density"] for f in prev_window) / len(prev_window)
        avg_prev_pitch = sum(f["avg_pitch"] for f in prev_window) / len(prev_window)
        prev_chords = any(f["has_chords"] for f in prev_window)

        density_change = abs(current["density"] - avg_prev_density) > avg_prev_density * 0.8 if avg_prev_density > 0 else current["density"] > 0
        pitch_change = abs(current["avg_pitch"] - avg_prev_pitch) > 7 if avg_prev_pitch > 0 else False
        chord_change = current["has_chords"] != prev_chords

        change_score = sum([density_change, pitch_change, chord_change])
        if change_score >= 2:
            if not change_points or bars[i] - change_points[-1] >= MIN_SECTION_GAP_BARS:
                change_points.append(bars[i])

    return change_points


def _generate_section_names(
    change_points: list[int],
    total_bars: int,
) -> list[tuple[int, str]]:
    """Assign generic section names based on position in the song."""
    if not change_points:
        return [(0, "intro")]

    result: list[tuple[int, str]] = []
    section_labels = ["intro", "verse", "chorus", "verse 2", "chorus 2",
                      "bridge", "solo", "chorus 3", "outro"]

    for i, bar_idx in enumerate(change_points):
        if i < len(section_labels):
            name = section_labels[i]
        else:
            name = f"section {i + 1}"
        result.append((bar_idx, name))

    return result
