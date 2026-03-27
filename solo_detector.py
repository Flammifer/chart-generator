"""Detect guitar solo sections by comparing Lead vs Rhythm tracks.

Uses weighted scoring instead of binary criteria.
Key signals:
  - Lead plays in a higher register than rhythm (pitch divergence)
  - Lead has higher note density / complexity
  - Lead uses high frets (≥12 on real guitar)
  - Lead has wide pitch variety (melodic runs)

Solo regions get:
  - `E solo` / `E soloend` track events in the .chart
  - `N 6 0` (tap flag) on notes played on high frets
"""
from __future__ import annotations

from models import ParsedSong, ParsedTrack, SongNote, SoloRegion, TICKS_PER_QUARTER
from track_merger import find_guitar_tracks

HIGH_FRET_THRESHOLD = 12
ANALYSIS_WINDOW_BARS = 4
ANALYSIS_STEP_BARS = 2
MIN_SOLO_BARS = 2

DEFAULT_SOLO_THRESHOLD = 2.5


def detect_solo_regions(
    song: ParsedSong,
    threshold: float = DEFAULT_SOLO_THRESHOLD,
) -> list[SoloRegion]:
    lead, rhythm = find_guitar_tracks(song)
    if lead is None:
        return []

    explicit = _from_gp_markers(song)
    if explicit:
        return explicit

    return _detect_from_tracks(lead, rhythm, song, threshold)


_SOLO_KEYWORDS = {"solo", "соло", "guitar solo", "гитарное соло", "lead"}


def _from_gp_markers(song: ParsedSong) -> list[SoloRegion]:
    regions: list[SoloRegion] = []
    solo_start_bar = None

    section_bars = [(s.bar_index, s.name) for s in song.sections]
    section_bars.sort(key=lambda x: x[0])

    for i, (bar_idx, name) in enumerate(section_bars):
        name_lower = name.lower().strip()
        is_solo = any(kw in name_lower for kw in _SOLO_KEYWORDS)

        if is_solo and solo_start_bar is None:
            solo_start_bar = bar_idx
        elif not is_solo and solo_start_bar is not None:
            regions.append(SoloRegion(
                start_tick=song.bar_start_tick(solo_start_bar),
                end_tick=song.bar_start_tick(bar_idx),
            ))
            solo_start_bar = None

    if solo_start_bar is not None:
        end_bar = min(solo_start_bar + 16, song.total_bars)
        regions.append(SoloRegion(
            start_tick=song.bar_start_tick(solo_start_bar),
            end_tick=song.bar_start_tick(end_bar),
        ))

    return regions


def _detect_from_tracks(
    lead: ParsedTrack,
    rhythm: ParsedTrack | None,
    song: ParsedSong,
    threshold: float,
) -> list[SoloRegion]:
    lead_global_stats = _track_stats(lead.notes)
    rhythm_global_stats = _track_stats(rhythm.notes) if rhythm else None

    bar_scores: dict[int, float] = {}

    for bar_start in range(0, song.total_bars - ANALYSIS_STEP_BARS + 1, ANALYSIS_STEP_BARS):
        bar_end = min(bar_start + ANALYSIS_WINDOW_BARS, song.total_bars)
        tick_start = song.bar_start_tick(bar_start)
        tick_end = song.bar_start_tick(bar_end) if bar_end < song.total_bars else float("inf")

        lead_notes = _notes_in_range(lead.notes, tick_start, tick_end)
        rhythm_notes = _notes_in_range(rhythm.notes, tick_start, tick_end) if rhythm else []

        score = _solo_score(lead_notes, rhythm_notes,
                            lead_global_stats, rhythm_global_stats)

        for bar in range(bar_start, bar_end):
            bar_scores[bar] = max(bar_scores.get(bar, 0.0), score)

    solo_bars = [bar for bar, sc in bar_scores.items() if sc >= threshold]
    return _bars_to_regions(solo_bars, song)


def _solo_score(
    lead_notes: list[SongNote],
    rhythm_notes: list[SongNote],
    lead_global: _TrackStats,
    rhythm_global: _TrackStats | None,
) -> float:
    if not lead_notes:
        return 0.0

    score = 0.0

    lead_density = len(lead_notes)
    rhythm_density = len(rhythm_notes) if rhythm_notes else 0

    if rhythm_density > 0:
        ratio = lead_density / rhythm_density
        if ratio >= 2.5:
            score += 1.0
        elif ratio >= 1.8:
            score += 0.75
        elif ratio >= 1.3:
            score += 0.5
    elif lead_density > 8:
        score += 0.5

    lead_pitches = set()
    for n in lead_notes:
        lead_pitches.update(n.midi_pitches)
    pitch_count = len(lead_pitches)
    if pitch_count >= 10:
        score += 1.0
    elif pitch_count >= 6:
        score += 0.5

    max_fret = max((n.max_guitar_fret for n in lead_notes), default=0)
    if max_fret >= HIGH_FRET_THRESHOLD:
        score += 1.0

    lead_avg = _avg_pitch(lead_notes)
    if lead_global.avg_pitch > 0 and lead_avg > lead_global.avg_pitch + 5:
        score += 0.5
    if lead_avg > lead_global.avg_pitch + 10:
        score += 0.5

    if rhythm_notes and rhythm_global:
        rhythm_avg = _avg_pitch(rhythm_notes)
        local_gap = lead_avg - rhythm_avg
        global_gap = lead_global.avg_pitch - rhythm_global.avg_pitch
        extra_gap = local_gap - global_gap
        if extra_gap >= 10:
            score += 1.0
        elif extra_gap >= 5:
            score += 0.5

    return score


class _TrackStats:
    __slots__ = ("avg_pitch", "note_count")

    def __init__(self, avg_pitch: float, note_count: int):
        self.avg_pitch = avg_pitch
        self.note_count = note_count


def _track_stats(notes: list[SongNote]) -> _TrackStats:
    playable = [n for n in notes if not n.is_tie]
    avg = _avg_pitch(playable) if playable else 0.0
    return _TrackStats(avg_pitch=avg, note_count=len(playable))


def _avg_pitch(notes: list[SongNote]) -> float:
    if not notes:
        return 0.0
    total = sum(sum(n.midi_pitches) / len(n.midi_pitches) for n in notes)
    return total / len(notes)


def _bars_to_regions(solo_bars: list[int], song: ParsedSong) -> list[SoloRegion]:
    if not solo_bars:
        return []

    sorted_bars = sorted(set(solo_bars))
    regions: list[SoloRegion] = []
    region_start = sorted_bars[0]
    prev_bar = sorted_bars[0]

    for bar in sorted_bars[1:]:
        if bar - prev_bar > ANALYSIS_WINDOW_BARS:
            if prev_bar - region_start + 1 >= MIN_SOLO_BARS:
                regions.append(_make_region(region_start, prev_bar, song))
            region_start = bar
        prev_bar = bar

    if prev_bar - region_start + 1 >= MIN_SOLO_BARS:
        regions.append(_make_region(region_start, prev_bar, song))

    return regions


def _make_region(start_bar: int, end_bar: int, song: ParsedSong) -> SoloRegion:
    end = end_bar + 1
    end_tick = song.bar_start_tick(end) if end < song.total_bars \
        else song.bar_start_tick(end_bar) + song._time_sig_at_bar(end_bar).ticks_per_bar
    return SoloRegion(
        start_tick=song.bar_start_tick(start_bar),
        end_tick=end_tick,
    )


def _notes_in_range(notes: list[SongNote], start: int, end: float) -> list[SongNote]:
    return [n for n in notes if start <= n.tick < end and not n.is_tie]


def mark_tap_notes_in_solo(
    notes: list[SongNote],
    chart_notes: list,
    solo_regions: list[SoloRegion],
) -> None:
    fret_by_tick: dict[int, int] = {}
    for n in notes:
        if not n.is_tie:
            fret_by_tick[n.tick] = n.max_guitar_fret

    for cn in chart_notes:
        if not _in_solo(cn.tick, solo_regions):
            continue
        original_fret = fret_by_tick.get(cn.tick, 0)
        if original_fret >= HIGH_FRET_THRESHOLD:
            cn.is_tap = True


def _in_solo(tick: int, regions: list[SoloRegion]) -> bool:
    return any(r.start_tick <= tick < r.end_tick for r in regions)
