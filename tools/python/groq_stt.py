import sys
import os
import json
from pathlib import Path

SUPPORTED_EXTS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}
MAX_FILE_BYTES = 25 * 1024 * 1024  # Groq limit: 25 MB


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: groq_stt.py <audio_path> [language_code] [model]",
        }))
        sys.exit(1)

    audio_path = Path(sys.argv[1])
    language_code = sys.argv[2] if len(sys.argv) > 2 else "en"
    model = sys.argv[3] if len(sys.argv) > 3 else "whisper-large-v3-turbo"

    if not audio_path.exists():
        print(json.dumps({"success": False, "error": f"Audio file not found: {audio_path}"}))
        sys.exit(1)

    if audio_path.suffix.lower() not in SUPPORTED_EXTS:
        print(json.dumps({
            "success": False,
            "error": f"Unsupported format {audio_path.suffix!r}. Supported: {', '.join(sorted(SUPPORTED_EXTS))}",
        }))
        sys.exit(1)

    file_size = audio_path.stat().st_size
    if file_size > MAX_FILE_BYTES:
        print(json.dumps({
            "success": False,
            "error": f"File too large ({file_size / 1024 / 1024:.1f} MB). Groq limit is 25 MB.",
        }))
        sys.exit(1)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print(json.dumps({"success": False, "error": "Missing required env var: GROQ_API_KEY"}))
        sys.exit(1)

    try:
        from groq import Groq
    except ImportError:
        print(json.dumps({"success": False, "error": "groq not installed — run: pip install groq"}))
        sys.exit(1)

    try:
        client = Groq(api_key=api_key)

        with audio_path.open("rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(audio_path.name, f.read()),
                model=model,
                language=language_code,
                response_format="text",
                temperature=0,
            )

        transcript = transcription if isinstance(transcription, str) else transcription.text

        print(json.dumps({
            "success": True,
            "data": {
                "transcript": transcript.strip(),
                "language_code": language_code,
                "model": model,
                "audio_path": str(audio_path.resolve()),
                "file_size_bytes": file_size,
            },
        }))

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
