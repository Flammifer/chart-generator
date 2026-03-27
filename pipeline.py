"""Core generation pipeline — used by both CLI and GUI."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

from gp7_parser import parse_gp7
from track_merger import merge_tracks
from phrase_splitter import split_into_phrases
from pitch_mapper import map_phrase_to_chart_notes
from difficulty_reducer import generate_all_difficulties
from section_detector import detect_sections
from star_power import place_star_power
from solo_detector import detect_solo_regions, mark_tap_notes_in_solo
from chart_exporter import export_chart
from config import ChartConfig
import re

from models import ChartNote, ParsedSong, DifficultyChart, ChartEvent, SoloRegion

_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*]')


def _safe_filename(name: str) -> str:
    return _ILLEGAL_CHARS.sub("", name).strip(". ")


@dataclass
class GenerationResult:
    output_dir: str = ""
    song_title: str = ""
    song_artist: str = ""
    bpm: float = 0
    total_bars: int = 0
    tracks: list[str] = field(default_factory=list)
    expert_notes: int = 0
    hard_notes: int = 0
    medium_notes: int = 0
    easy_notes: int = 0
    solo_count: int = 0
    sections: list[str] = field(default_factory=list)
    error: str = ""

    _song: ParsedSong | None = field(default=None, repr=False)
    _expert_chart_notes: list[ChartNote] = field(default_factory=list, repr=False)
    _difficulties: dict[str, DifficultyChart] = field(default_factory=dict, repr=False)
    _section_events: list[ChartEvent] = field(default_factory=list, repr=False)
    _solo_regions: list[SoloRegion] = field(default_factory=list, repr=False)
    _audio_filename: str = field(default="song.mp3", repr=False)


def generate_chart(
    gp_path: str,
    audio_path: str | None = None,
    config: ChartConfig | None = None,
    output_dir_override: str | None = None,
    on_progress: callable = None,
) -> GenerationResult:
    result = GenerationResult()
    if config is None:
        config = ChartConfig()

    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    try:
        log("Parsing GP file...")
        song = parse_gp7(gp_path)
        result.song_title = song.title
        result.song_artist = song.artist
        result.bpm = song.initial_bpm
        result.total_bars = song.total_bars
        result.tracks = [t.name for t in song.tracks]

        log("Detecting solos...")
        solo_regions = detect_solo_regions(song, threshold=config.solo_sensitivity)
        result.solo_count = len(solo_regions)

        log("Merging guitar tracks...")
        merged_notes = merge_tracks(song, bar_window=config.merge_bar_window,
                                    solo_regions=solo_regions)

        log("Splitting into phrases...")
        phrases = split_into_phrases(merged_notes, song)

        log("Mapping pitches to frets...")
        expert_notes: list[ChartNote] = []
        for phrase in phrases:
            expert_notes.extend(map_phrase_to_chart_notes(phrase))
        expert_notes.sort(key=lambda n: n.tick)

        if solo_regions:
            mark_tap_notes_in_solo(merged_notes, expert_notes, solo_regions)

        log("Detecting sections...")
        sections = detect_sections(merged_notes, song)
        result.sections = [s.value for s in sections]

        log("Placing star power...")
        sp_phrases = place_star_power(expert_notes, song)

        log("Generating difficulty levels...")
        difficulties = generate_all_difficulties(expert_notes, config)
        for chart in difficulties.values():
            chart.star_power = sp_phrases
            chart.solo_regions = solo_regions

        result.expert_notes = len(difficulties["Expert"].notes)
        result.hard_notes = len(difficulties["Hard"].notes)
        result.medium_notes = len(difficulties["Medium"].notes)
        result.easy_notes = len(difficulties["Easy"].notes)

        result._song = song
        result._expert_chart_notes = expert_notes
        result._difficulties = difficulties
        result._section_events = sections
        result._solo_regions = solo_regions

        song_folder = _safe_filename(f"{song.artist} - {song.title}".strip(" -"))
        if not song_folder:
            song_folder = _safe_filename(os.path.splitext(os.path.basename(gp_path))[0])

        if output_dir_override:
            output_dir = output_dir_override
        elif config.output_dir:
            output_dir = os.path.join(config.output_dir, song_folder)
        else:
            output_dir = os.path.join(os.path.dirname(gp_path), song_folder)

        audio_filename = config.audio_filename or "song.mp3"
        result._audio_filename = audio_filename

        log(f"Exporting to {output_dir}...")
        export_chart(song, difficulties, sections, output_dir, audio_filename,
                     audio_offset_ms=config.audio_offset_ms)

        if audio_path and os.path.isfile(audio_path):
            dest = os.path.join(output_dir, audio_filename)
            log("Copying audio file...")
            shutil.copy2(audio_path, dest)

        result.output_dir = output_dir
        log("Done!")

    except Exception as e:
        result.error = str(e)
        log(f"Error: {e}")

    return result


def re_export_with_offset(
    prev_result: GenerationResult,
    audio_offset_ms: int,
    audio_path: str | None = None,
) -> None:
    """Quick re-export: only rewrites chart/ini with new offset, no re-parsing."""
    if not prev_result._song or not prev_result._difficulties:
        raise ValueError("No generation data to re-export")

    export_chart(
        prev_result._song,
        prev_result._difficulties,
        prev_result._section_events,
        prev_result.output_dir,
        prev_result._audio_filename,
        audio_offset_ms=audio_offset_ms,
    )

    if audio_path and os.path.isfile(audio_path):
        dest = os.path.join(prev_result.output_dir, prev_result._audio_filename)
        shutil.copy2(audio_path, dest)
