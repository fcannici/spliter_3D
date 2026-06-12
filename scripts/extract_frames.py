from __future__ import annotations

import argparse
from pathlib import Path

import cv2


def extract_frames(video_path: Path, output_dir: Path, points: list[float]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir el video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for i, p in enumerate(points):
        frame_idx = min(max(int(total_frames * p), 0), max(total_frames - 1, 0))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if ret:
            out_path = output_dir / f"frame_{i}.jpg"
            cv2.imwrite(str(out_path), frame)
            print(f"Frame {i} ({p * 100:.1f}%) guardado en {out_path}")
    cap.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae frames representativos de un video.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--points", nargs="*", type=float, default=[0.1, 0.3, 0.5, 0.7, 0.9])
    args = parser.parse_args()
    extract_frames(args.video, args.out, args.points)


if __name__ == "__main__":
    main()
