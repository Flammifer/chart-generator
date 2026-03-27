"""Place Star Power phrases on the chart.

Star Power is placed on musically prominent sections:
  - High note density areas (solos, fills)
  - Phrase boundaries where the music peaks
  
Roughly every 8-16 bars, lasting 2-4 bars each.
"""
from __future__ import annotations

from models import ChartNote, ParsedSong, TICKS_PER_QUARTER


SP_MIN_NOTES = 6
SP_INTERVAL_BARS = 12
SP_DURATION_BARS = 3


def place_star_power(
    notes: list[ChartNote],
    song: ParsedSong,
) -> list[tuple[int, int]]:
    """Return list of (start_tick, duration_ticks) for star power phrases."""
    if not notes:
        return []

    ts = song._time_sig_at_bar(0)
    bar_ticks = ts.ticks_per_bar
    sp_interval = SP_INTERVAL_BARS * bar_ticks
    sp_duration = SP_DURATION_BARS * bar_ticks

    density_by_bar = _note_density_by_bar(notes, song)
    sorted_bars = sorted(density_by_bar.keys(), key=lambda b: density_by_bar[b], reverse=True)

    star_power: list[tuple[int, int]] = []
    used_ticks: set[int] = set()

    for bar_idx in sorted_bars:
        tick = song.bar_start_tick(bar_idx)

        too_close = any(abs(tick - sp_tick) < sp_interval for sp_tick, _ in star_power)
        if too_close:
            continue

        notes_in_range = [n for n in notes if tick <= n.tick < tick + sp_duration]
        if len(notes_in_range) < SP_MIN_NOTES:
            continue

        start = notes_in_range[0].tick
        end = notes_in_range[-1].tick
        star_power.append((start, end - start))

    star_power.sort(key=lambda sp: sp[0])
    return star_power


def _note_density_by_bar(notes: list[ChartNote], song: ParsedSong) -> dict[int, int]:
    density: dict[int, int] = {}
    for bar_idx in range(song.total_bars):
        start = song.bar_start_tick(bar_idx)
        end = start + song._time_sig_at_bar(bar_idx).ticks_per_bar
        count = sum(1 for n in notes if start <= n.tick < end)
        if count > 0:
            density[bar_idx] = count
    return density
