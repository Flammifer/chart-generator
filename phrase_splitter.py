"""Split the note stream into musical phrases for fret mapping.

Phrases are determined by:
  1. Section markers from the GP file (if available)
  2. Significant rests (gaps longer than a whole note)
  3. Fixed bar groupings as fallback (every 4 bars)
"""
from __future__ import annotations

from dataclasses import dataclass

from models import SongNote, ParsedSong, TICKS_PER_QUARTER


WHOLE_NOTE_TICKS = TICKS_PER_QUARTER * 4
MIN_REST_FOR_PHRASE_BREAK = WHOLE_NOTE_TICKS


@dataclass
class Phrase:
    start_tick: int
    end_tick: int
    notes: list[SongNote]


def split_into_phrases(
    notes: list[SongNote],
    song: ParsedSong,
) -> list[Phrase]:
    if not notes:
        return []

    section_ticks = [song.bar_start_tick(s.bar_index) for s in song.sections]

    if section_ticks:
        return _split_by_sections(notes, section_ticks)

    return _split_by_rests_and_bars(notes, song)


def _split_by_sections(
    notes: list[SongNote],
    section_ticks: list[int],
) -> list[Phrase]:
    boundaries = sorted(set(section_ticks))
    phrases: list[Phrase] = []

    for i, boundary in enumerate(boundaries):
        next_boundary = boundaries[i + 1] if i + 1 < len(boundaries) else float("inf")
        phrase_notes = [n for n in notes if boundary <= n.tick < next_boundary]
        if phrase_notes:
            phrases.append(Phrase(
                start_tick=boundary,
                end_tick=int(next_boundary) if next_boundary != float("inf") else phrase_notes[-1].tick + phrase_notes[-1].duration_ticks,
                notes=phrase_notes,
            ))

    notes_before_first = [n for n in notes if n.tick < boundaries[0]]
    if notes_before_first:
        phrases.insert(0, Phrase(
            start_tick=notes_before_first[0].tick,
            end_tick=boundaries[0],
            notes=notes_before_first,
        ))

    return phrases


def _split_by_rests_and_bars(
    notes: list[SongNote],
    song: ParsedSong,
    bar_group_size: int = 4,
) -> list[Phrase]:
    rest_phrases = _split_by_rests(notes)

    result: list[Phrase] = []
    for phrase in rest_phrases:
        if _phrase_span_bars(phrase, song) > bar_group_size * 2:
            result.extend(_split_by_bar_groups(phrase, song, bar_group_size))
        else:
            result.append(phrase)

    return result


def _split_by_rests(notes: list[SongNote]) -> list[Phrase]:
    if not notes:
        return []

    sorted_notes = sorted(notes, key=lambda n: n.tick)
    phrases: list[Phrase] = []
    current_group: list[SongNote] = [sorted_notes[0]]

    for note in sorted_notes[1:]:
        prev = current_group[-1]
        gap = note.tick - (prev.tick + prev.duration_ticks)

        if gap >= MIN_REST_FOR_PHRASE_BREAK:
            phrases.append(_make_phrase(current_group))
            current_group = [note]
        else:
            current_group.append(note)

    if current_group:
        phrases.append(_make_phrase(current_group))

    return phrases


def _split_by_bar_groups(
    phrase: Phrase,
    song: ParsedSong,
    group_size: int,
) -> list[Phrase]:
    result: list[Phrase] = []
    bar_ticks = [song.bar_start_tick(i) for i in range(song.total_bars)]

    first_bar = 0
    for i, bt in enumerate(bar_ticks):
        if bt <= phrase.start_tick:
            first_bar = i

    for group_start_bar in range(first_bar, song.total_bars, group_size):
        tick_start = song.bar_start_tick(group_start_bar)
        group_end_bar = min(group_start_bar + group_size, song.total_bars)
        tick_end = song.bar_start_tick(group_end_bar) if group_end_bar < song.total_bars else phrase.end_tick

        group_notes = [n for n in phrase.notes if tick_start <= n.tick < tick_end]
        if group_notes:
            result.append(Phrase(
                start_tick=tick_start,
                end_tick=tick_end,
                notes=group_notes,
            ))

    return result


def _phrase_span_bars(phrase: Phrase, song: ParsedSong) -> int:
    span_ticks = phrase.end_tick - phrase.start_tick
    ts = song._time_sig_at_bar(0)
    return max(1, span_ticks // ts.ticks_per_bar)


def _make_phrase(notes: list[SongNote]) -> Phrase:
    return Phrase(
        start_tick=notes[0].tick,
        end_tick=notes[-1].tick + notes[-1].duration_ticks,
        notes=notes,
    )
