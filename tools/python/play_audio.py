import sys
import os
import json
import time
from pathlib import Path

SUPPORTED_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

# Keep SDL from opening a display or audio device popup on Windows
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
# Suppress pygame's startup banner so stdout stays clean JSON
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: play_audio.py <audio_path>"}))
        sys.exit(1)

    audio_path = Path(sys.argv[1])

    if not audio_path.exists():
        print(json.dumps({"success": False, "error": f"Audio file not found: {audio_path}"}))
        sys.exit(1)

    if audio_path.suffix.lower() not in SUPPORTED_EXTS:
        print(json.dumps({
            "success": False,
            "error": f"Unsupported format {audio_path.suffix!r}. Supported: {', '.join(sorted(SUPPORTED_EXTS))}",
        }))
        sys.exit(1)

    try:
        import pygame.mixer
    except ImportError:
        print(json.dumps({"success": False, "error": "pygame not installed — run: pip install pygame"}))
        sys.exit(1)

    try:
        pygame.mixer.init()
        pygame.mixer.music.load(str(audio_path))

        start = time.monotonic()
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.05)

        elapsed = round(time.monotonic() - start, 2)
        pygame.mixer.quit()

        print(json.dumps({
            "success": True,
            "data": {
                "audio_path": str(audio_path.resolve()),
                "played_seconds": elapsed,
                "file_size_bytes": audio_path.stat().st_size,
            },
        }))

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
