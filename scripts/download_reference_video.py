"""Download a public reference video and extract preview frames.

Usage:
    python scripts/download_reference_video.py "https://www.instagram.com/..." --out "C:/Users/nerovikingo/agent_google/para ver"

Requires:
    pip install yt-dlp
Optional for frame extraction:
    ffmpeg available in PATH
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    print("RUN:", " ".join(cmd))
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def ensure_ytdlp() -> None:
    result = run([sys.executable, "-m", "yt_dlp", "--version"])
    if result.returncode == 0:
        print(result.stdout.strip())
        return
    print("yt-dlp no encontrado. Instalando...")
    install = run([sys.executable, "-m", "pip", "install", "yt-dlp"])
    print(install.stdout)
    if install.returncode != 0:
        raise SystemExit("No se pudo instalar yt-dlp")


def download(url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    template = str(out_dir / "split3r_reference_%(id)s.%(ext)s")
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--restrict-filenames",
        "--merge-output-format",
        "mp4",
        "-o",
        template,
    ]
    if getattr(download, "cookies_from_browser", None):
        cmd.extend(["--cookies-from-browser", download.cookies_from_browser])
    if getattr(download, "cookies_file", None):
        cmd.extend(["--cookies", download.cookies_file])
    cmd.append(url)
    result = run(cmd)
    print(result.stdout)
    if result.returncode != 0:
        raise SystemExit("Fallo la descarga. Si Instagram pide login, descargalo logueado o pasá cookies a yt-dlp.")

    candidates = sorted(out_dir.glob("split3r_reference_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        # yt-dlp may keep original extension if merge was not needed.
        candidates = sorted(out_dir.glob("split3r_reference_*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise SystemExit("No encuentro el archivo descargado")
    return candidates[0]


def extract_frames(video: Path, out_dir: Path, fps: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg no esta en PATH; salteo extraccion de frames.")
        return
    frames_dir = out_dir / f"{video.stem}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "frame_%04d.jpg")
    result = run([ffmpeg, "-y", "-i", str(video), "-vf", f"fps={fps}", "-q:v", "2", pattern])
    print(result.stdout)
    if result.returncode != 0:
        raise SystemExit("Fallo ffmpeg al extraer frames")
    print(f"Frames guardados en: {frames_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--out", default=r"C:/Users/nerovikingo/agent_google/para ver")
    parser.add_argument("--fps", type=float, default=1.0, help="Frames por segundo a extraer")
    parser.add_argument("--cookies-from-browser", choices=["brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi"], help="Usar cookies de un navegador logueado, por ejemplo: chrome")
    parser.add_argument("--cookies", help="Archivo cookies.txt exportado para yt-dlp")
    args = parser.parse_args()

    ensure_ytdlp()
    out_dir = Path(args.out)
    download.cookies_from_browser = args.cookies_from_browser
    download.cookies_file = args.cookies
    video = download(args.url, out_dir)
    print(f"VIDEO={video}")
    extract_frames(video, out_dir, args.fps)


if __name__ == "__main__":
    main()
