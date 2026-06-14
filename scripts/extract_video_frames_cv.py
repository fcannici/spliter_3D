from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def ensure_cv2():
    try:
        import cv2  # noqa: F401
        return
    except Exception:
        print("opencv-python no encontrado. Instalando...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "opencv-python"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--out")
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--max-frames", type=int, default=80)
    args = parser.parse_args()

    ensure_cv2()
    import cv2

    video = Path(args.video)
    out = Path(args.out) if args.out else video.with_name(video.stem + "_frames")
    out.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"No pude abrir video: {video}")
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / source_fps if source_fps else 0
    every = max(1, round(source_fps / args.fps))
    print(f"VIDEO={video}")
    print(f"FPS={source_fps:.3f} FRAMES={frame_count} DURATION={duration:.2f}s EVERY={every}")

    saved = 0
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            t = idx / source_fps
            name = out / f"frame_{saved:04d}_{t:06.2f}s.jpg"
            cv2.imwrite(str(name), frame)
            print(name)
            saved += 1
            if saved >= args.max_frames:
                break
        idx += 1
    cap.release()
    print(f"SAVED={saved} OUT={out}")


if __name__ == "__main__":
    main()
