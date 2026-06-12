from __future__ import annotations

import argparse
from pathlib import Path

from extract_frames import extract_frames


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae 11 frames, de 0% a 100%, de un video.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    extract_frames(args.video, args.out, [x / 10.0 for x in range(11)])


if __name__ == "__main__":
    main()
