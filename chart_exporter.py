"""Export the chart data to .chart file format + song.ini for YARG/Clone Hero."""
from __future__ import annotations

import os
from models import (
    ParsedSong, DifficultyChart, ChartEvent,
    TICKS_PER_QUARTER,
)

DIFFICULTY_TRACK_NAMES = {
    "Expert": "ExpertSingle",
    "Hard": "HardSingle",
    "Medium": "MediumSingle",
    "Easy": "EasySingle",
}


def export_chart(
    song: ParsedSong,
    difficulties: dict[str, DifficultyChart],
    sections: list[ChartEvent],
    output_dir: str,
    audio_filename: str = "song.ogg",
    audio_offset_ms: int = 0,
) -> str:
    os.makedirs(output_dir, exist_ok=True)

    for stale in ("notes.chart", "song.ini"):
        stale_path = os.path.join(output_dir, stale)
        if os.path.isfile(stale_path):
            os.remove(stale_path)

    lines: list[str] = []
    _write_song_section(lines, song, audio_filename, audio_offset_ms)
    _write_sync_track(lines, song)
    _write_events(lines, sections)

    for diff_name in ("Expert", "Hard", "Medium", "Easy"):
        if diff_name in difficulties:
            _write_difficulty(lines, diff_name, difficulties[diff_name])

    chart_path = os.path.join(output_dir, "notes.chart")
    with open(chart_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    ini_path = os.path.join(output_dir, "song.ini")
    _write_song_ini(ini_path, song, audio_offset_ms)

    return chart_path


def _write_song_section(
    lines: list[str],
    song: ParsedSong,
    audio_filename: str,
    audio_offset_ms: int = 0,
) -> None:
    offset_sec = audio_offset_ms / 1000.0
    lines.append("[Song]")
    lines.append("{")
    lines.append(f'  Name = "{song.title}"')
    lines.append(f'  Artist = "{song.artist}"')
    lines.append(f'  Charter = "chart-generator"')
    lines.append(f'  Album = "{song.album}"')
    lines.append(f'  Year = ", 2025"')
    lines.append(f"  Offset = {offset_sec}")
    lines.append(f"  Resolution = {TICKS_PER_QUARTER}")
    lines.append(f"  Player2 = bass")
    lines.append(f"  Difficulty = 0")
    lines.append(f"  PreviewStart = 0")
    lines.append(f"  PreviewEnd = 0")
    lines.append(f'  Genre = "rock"')
    lines.append(f'  MediaType = "cd"')
    lines.append(f'  MusicStream = "{audio_filename}"')
    lines.append("}")


def _write_sync_track(lines: list[str], song: ParsedSong) -> None:
    lines.append("[SyncTrack]")
    lines.append("{")

    prev_ts = None
    for bar_idx, ts in sorted(song.time_signatures.items()):
        if prev_ts and ts.numerator == prev_ts.numerator and ts.denominator == prev_ts.denominator:
            continue
        prev_ts = ts
        tick = song.bar_start_tick(bar_idx)
        den_exp = _denominator_exponent(ts.denominator)
        if den_exp != 2:
            lines.append(f"  {tick} = TS {ts.numerator} {den_exp}")
        else:
            lines.append(f"  {tick} = TS {ts.numerator}")

    for tc in song.tempo_changes:
        tick = song.bar_start_tick(tc.bar_index)
        bpm_int = int(round(tc.bpm * 1000))
        lines.append(f"  {tick} = B {bpm_int}")

    lines.append("}")


def _write_events(lines: list[str], sections: list[ChartEvent]) -> None:
    lines.append("[Events]")
    lines.append("{")
    for event in sections:
        lines.append(f'  {event.tick} = E "section {event.value}"')
    lines.append("}")


def _write_difficulty(
    lines: list[str],
    diff_name: str,
    chart: DifficultyChart,
) -> None:
    track_name = DIFFICULTY_TRACK_NAMES[diff_name]
    lines.append(f"[{track_name}]")
    lines.append("{")

    all_events: list[tuple[int, str]] = []

    for note in chart.notes:
        for fret in note.frets:
            all_events.append((note.tick, f"N {fret} {note.sustain_ticks}"))
        if note.is_forced:
            all_events.append((note.tick, "N 5 0"))
        if note.is_tap:
            all_events.append((note.tick, "N 6 0"))

    for sp_start, sp_dur in chart.star_power:
        all_events.append((sp_start, f"S 2 {sp_dur}"))

    for solo in chart.solo_regions:
        all_events.append((solo.start_tick, "E solo"))
        all_events.append((solo.end_tick, "E soloend"))

    all_events.sort(key=lambda e: e[0])

    for tick, event in all_events:
        lines.append(f"  {tick} = {event}")

    lines.append("}")


def _write_song_ini(path: str, song: ParsedSong, audio_offset_ms: int = 0) -> None:
    lines = [
        "[song]",
        f"name = {song.title}",
        f"artist = {song.artist}",
        f"album = {song.album}",
        f"genre = Rock",
        f"charter = chart-generator",
        f"diff_guitar = 0",
    ]
    if audio_offset_ms != 0:
        lines.append(f"delay = {audio_offset_ms}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _denominator_exponent(denominator: int) -> int:
    exp = 0
    val = 1
    while val < denominator:
        val *= 2
        exp += 1
    return exp
