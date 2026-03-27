from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum

TICKS_PER_QUARTER = 192


class Fret(IntEnum):
    GREEN = 0
    RED = 1
    YELLOW = 2
    BLUE = 3
    ORANGE = 4


DURATION_TO_TICKS = {
    "Whole": TICKS_PER_QUARTER * 4,
    "Half": TICKS_PER_QUARTER * 2,
    "Quarter": TICKS_PER_QUARTER,
    "Eighth": TICKS_PER_QUARTER // 2,
    "16th": TICKS_PER_QUARTER // 4,
    "32nd": TICKS_PER_QUARTER // 8,
    "64th": TICKS_PER_QUARTER // 16,
}


@dataclass
class TempoChange:
    bar_index: int
    bpm: float


@dataclass
class TimeSignature:
    numerator: int
    denominator: int

    @property
    def ticks_per_bar(self) -> int:
        quarters_per_bar = self.numerator * (4 / self.denominator)
        return int(quarters_per_bar * TICKS_PER_QUARTER)


@dataclass
class SongNote:
    """A note extracted from the GP file, with absolute tick position."""
    tick: int
    midi_pitches: list[int]
    duration_ticks: int
    is_tie: bool = False
    is_hammer_on: bool = False
    source_track: str = ""
    max_guitar_fret: int = 0


@dataclass
class SoloRegion:
    start_tick: int
    end_tick: int


@dataclass
class SectionMarker:
    bar_index: int
    name: str


@dataclass
class ParsedTrack:
    name: str
    instrument_type: str
    notes: list[SongNote] = field(default_factory=list)


@dataclass
class ParsedSong:
    title: str
    artist: str
    album: str
    tempo_changes: list[TempoChange] = field(default_factory=list)
    time_signatures: dict[int, TimeSignature] = field(default_factory=dict)
    sections: list[SectionMarker] = field(default_factory=list)
    tracks: list[ParsedTrack] = field(default_factory=list)
    total_bars: int = 0

    @property
    def initial_bpm(self) -> float:
        return self.tempo_changes[0].bpm if self.tempo_changes else 120.0

    def bar_start_tick(self, bar_index: int) -> int:
        tick = 0
        for i in range(bar_index):
            ts = self._time_sig_at_bar(i)
            tick += ts.ticks_per_bar
        return tick

    def _time_sig_at_bar(self, bar_index: int) -> TimeSignature:
        result = TimeSignature(4, 4)
        for bi in sorted(self.time_signatures.keys()):
            if bi <= bar_index:
                result = self.time_signatures[bi]
            else:
                break
        return result


@dataclass
class ChartNote:
    """A note in the GH chart with fret assignments."""
    tick: int
    frets: list[int]
    sustain_ticks: int = 0
    is_forced: bool = False
    is_tap: bool = False


@dataclass
class ChartEvent:
    tick: int
    event_type: str
    value: str


@dataclass
class DifficultyChart:
    notes: list[ChartNote] = field(default_factory=list)
    star_power: list[tuple[int, int]] = field(default_factory=list)
    solo_regions: list[SoloRegion] = field(default_factory=list)
