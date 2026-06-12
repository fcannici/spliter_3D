from __future__ import annotations

import argparse
from pathlib import Path

import speech_recognition as sr
from moviepy import VideoFileClip


def transcribe_video(video_path: Path, audio_path: Path, language: str) -> str:
    if not audio_path.exists():
        print("Extracting audio...")
        video = VideoFileClip(str(video_path))
        if video.audio is None:
            raise SystemExit("El video no contiene pista de audio.")
        video.audio.write_audiofile(str(audio_path))

    print("Transcribing...")
    recognizer = sr.Recognizer()
    with sr.AudioFile(str(audio_path)) as source:
        audio_data = recognizer.record(source)
    return recognizer.recognize_google(audio_data, language=language)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae audio de un video y lo transcribe con Google Speech Recognition.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--audio", type=Path, default=Path("audio.wav"))
    parser.add_argument("--language", default="es-ES")
    args = parser.parse_args()

    try:
        print(transcribe_video(args.video, args.audio, args.language))
    except Exception as exc:
        raise SystemExit(f"No se pudo transcribir: {exc}") from exc


if __name__ == "__main__":
    main()
