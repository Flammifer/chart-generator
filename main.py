"""GP-to-YARG chart generator — CLI entry point.

Usage:
    python main.py <path_to_gp_file> [options]
"""
from __future__ import annotations

import argparse
import os

from pipeline import generate_chart
from config import ChartConfig


def main() -> None:
    args = _parse_args()

    if args.dump_config:
        config = ChartConfig()
        config.save(args.dump_config)
        print(f"Default config saved to: {args.dump_config}")
        return

    config = _load_config(args.config)

    if args.audio and args.audio != "song.ogg":
        config.audio_filename = args.audio

    result = generate_chart(
        gp_path=args.input,
        audio_path=None,
        config=config,
        output_dir_override=args.output,
        on_progress=lambda msg: print(f"  {msg}"),
    )

    if result.error:
        print(f"\nError: {result.error}")
        return

    print(f"\n  {result.song_artist} - {result.song_title}")
    print(f"  BPM: {result.bpm}, Bars: {result.total_bars}")
    print(f"  Expert: {result.expert_notes}, Hard: {result.hard_notes}, "
          f"Medium: {result.medium_notes}, Easy: {result.easy_notes}")
    print(f"  Solos: {result.solo_count}")
    print(f"  Output: {result.output_dir}")


def _load_config(config_path: str | None) -> ChartConfig:
    if config_path:
        return ChartConfig.load(config_path)
    default_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.isfile(default_path):
        return ChartConfig.load(default_path)
    return ChartConfig()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Guitar Pro tabs to YARG/Clone Hero charts")
    parser.add_argument("input", nargs="?", help="Path to .gp (Guitar Pro 7/8) file")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--audio", "-a", default="song.ogg", help="Audio filename (default: song.ogg)")
    parser.add_argument("--config", "-c", help="Path to JSON config file")
    parser.add_argument("--dump-config", metavar="PATH", help="Save default config to file and exit")

    args = parser.parse_args()
    if not args.dump_config and not args.input:
        parser.error("the following arguments are required: input")
    return args


if __name__ == "__main__":
    main()
