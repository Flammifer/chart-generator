"""Parser for Guitar Pro 7/8 (.gp) files — ZIP archives with XML inside."""
from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from models import (
    ParsedSong, ParsedTrack, SongNote, SectionMarker,
    TempoChange, TimeSignature, DURATION_TO_TICKS,
)


def parse_gp7(filepath: str) -> ParsedSong:
    with zipfile.ZipFile(filepath) as z:
        xml_bytes = z.read("Content/score.gpif")
    root = ET.fromstring(xml_bytes.decode("utf-8"))

    song = ParsedSong(
        title=_text(root, ".//Score/Title").strip(),
        artist=_text(root, ".//Score/Artist").strip(),
        album=_text(root, ".//Score/Album").strip(),
    )

    _parse_tempo(root, song)
    _parse_master_bars(root, song)

    notes_by_id = _index_notes(root)
    rhythms_by_id = _index_rhythms(root)
    beats_by_id = _index_beats(root, notes_by_id, rhythms_by_id)
    voices_by_id = _index_voices(root, beats_by_id)
    bars_by_id = _index_bars(root, voices_by_id)

    _parse_tracks(root, song, bars_by_id)
    return song


def _text(el: ET.Element, path: str) -> str:
    node = el.find(path)
    return (node.text or "") if node is not None else ""


def _parse_tempo(root: ET.Element, song: ParsedSong) -> None:
    for auto in root.findall(".//MasterTrack/Automations/Automation"):
        if _text(auto, "Type") == "Tempo":
            bar = int(_text(auto, "Bar"))
            value_str = _text(auto, "Value")
            bpm = float(value_str.split()[0])
            song.tempo_changes.append(TempoChange(bar, bpm))
    if not song.tempo_changes:
        song.tempo_changes.append(TempoChange(0, 120.0))


def _parse_master_bars(root: ET.Element, song: ParsedSong) -> None:
    master_bars = root.findall(".//MasterBars/MasterBar")
    song.total_bars = len(master_bars)
    song._master_bar_refs = []

    for i, mb in enumerate(master_bars):
        time_str = _text(mb, "Time")
        if time_str:
            parts = time_str.split("/")
            song.time_signatures[i] = TimeSignature(int(parts[0]), int(parts[1]))

        section = mb.find("Section")
        if section is not None:
            letter = _text(section, "Letter")
            text = _text(section, "Text")
            name = text if text else letter
            song.sections.append(SectionMarker(i, name))

        bar_ids = _text(mb, "Bars").split()
        song._master_bar_refs.append(bar_ids)


# ── Index building for the reference-based GP7 structure ──


def _index_notes(root: ET.Element) -> dict:
    result = {}
    for n in root.findall(".//Notes/Note"):
        nid = n.get("id")
        info = {"id": nid, "midi": 0, "string": 0, "fret": 0,
                "is_tie": False, "is_hammer_on": False}
        props = n.find("Properties")
        if props is not None:
            for p in props.findall("Property"):
                pname = p.get("name")
                if pname == "Midi":
                    info["midi"] = int(p.findtext("Number", "0"))
                elif pname == "Fret":
                    info["fret"] = int(p.findtext("Fret", "0"))
                elif pname == "String":
                    info["string"] = int(p.findtext("String", "0"))

        tie = n.find("Tie")
        if tie is not None and tie.get("destination") == "true":
            info["is_tie"] = True

        if n.find(".//HammerOn") is not None:
            info["is_hammer_on"] = True

        result[nid] = info
    return result


def _index_rhythms(root: ET.Element) -> dict:
    result = {}
    for r in root.findall(".//Rhythms/Rhythm"):
        rid = r.get("id")
        note_value = _text(r, "NoteValue")
        is_dotted = r.find("AugmentationDot") is not None
        base_ticks = DURATION_TO_TICKS.get(note_value, 192)
        ticks = int(base_ticks * 1.5) if is_dotted else base_ticks

        tuplet = r.find("PrimaryTuplet")
        if tuplet is not None:
            num = int(tuplet.get("num", "1"))
            den = int(tuplet.get("den", "1"))
            ticks = ticks * den // num

        result[rid] = ticks
    return result


def _index_beats(root: ET.Element, notes_idx: dict, rhythms_idx: dict) -> dict:
    result = {}
    for b in root.findall(".//Beats/Beat"):
        bid = b.get("id")
        note_ids = _text(b, "Notes").split()
        rhythm_ref = b.find("Rhythm")
        duration = rhythms_idx.get(rhythm_ref.get("ref"), 192) if rhythm_ref is not None else 192

        beat_notes = [notes_idx[nid] for nid in note_ids if nid in notes_idx]
        result[bid] = {"notes": beat_notes, "duration": duration}
    return result


def _index_voices(root: ET.Element, beats_idx: dict) -> dict:
    result = {}
    for v in root.findall(".//Voices/Voice"):
        vid = v.get("id")
        beat_ids = _text(v, "Beats").split()
        result[vid] = [beats_idx[bid] for bid in beat_ids if bid in beats_idx]
    return result


def _index_bars(root: ET.Element, voices_idx: dict) -> dict:
    result = {}
    for bar in root.findall(".//Bars/Bar"):
        bid = bar.get("id")
        voice_ids = _text(bar, "Voices").split()
        all_beats = []
        for vid in voice_ids:
            if vid != "-1" and vid in voices_idx:
                all_beats.extend(voices_idx[vid])
        result[bid] = all_beats
    return result


def _parse_tracks(root: ET.Element, song: ParsedSong, bars_idx: dict) -> None:
    track_elements = root.findall(".//Tracks/Track")

    for track_idx, tel in enumerate(track_elements):
        name = _text(tel, "Name").strip()
        iset = tel.find("InstrumentSet")
        itype = _text(iset, "Type") if iset is not None else ""

        parsed_track = ParsedTrack(name=name, instrument_type=itype)

        for bar_index in range(song.total_bars):
            bar_refs = song._master_bar_refs[bar_index]
            if track_idx >= len(bar_refs):
                continue

            bar_id = bar_refs[track_idx]
            beats = bars_idx.get(bar_id, [])
            bar_start = song.bar_start_tick(bar_index)

            tick_cursor = bar_start
            for beat in beats:
                gp_notes = beat["notes"]
                duration = beat["duration"]

                if gp_notes:
                    midi_pitches = [n["midi"] for n in gp_notes]
                    is_tie = any(n["is_tie"] for n in gp_notes)
                    is_hammer = any(n["is_hammer_on"] for n in gp_notes)
                    max_fret = max((n["fret"] for n in gp_notes), default=0)

                    parsed_track.notes.append(SongNote(
                        tick=tick_cursor,
                        midi_pitches=midi_pitches,
                        duration_ticks=duration,
                        is_tie=is_tie,
                        is_hammer_on=is_hammer,
                        source_track=name,
                        max_guitar_fret=max_fret,
                    ))

                tick_cursor += duration

        song.tracks.append(parsed_track)
