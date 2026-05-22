import sys
import json
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: record_audio.py <output_path> [duration_seconds]",
        }))
        sys.exit(1)

    output_path = Path(sys.argv[1])

    try:
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    except ValueError:
        print(json.dumps({"success": False, "error": "duration_seconds must be an integer"}))
        sys.exit(1)

    if not (1 <= duration <= 120):
        print(json.dumps({"success": False, "error": "duration_seconds must be between 1 and 120"}))
        sys.exit(1)

    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        print(json.dumps({"success": False, "error": f"Missing dependency: {exc}. Run: pip install sounddevice soundfile"}))
        sys.exit(1)

    try:
        # 16 kHz mono is the native rate for Whisper — avoids resampling in groq_stt
        SAMPLE_RATE = 16000

        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"[record_audio] Recording {duration}s from microphone...", file=sys.stderr)
        recording = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
        )
        sd.wait()
        print("[record_audio] Done.", file=sys.stderr)

        sf.write(str(output_path), recording, SAMPLE_RATE, subtype="PCM_16")

        file_size = output_path.stat().st_size

        print(json.dumps({
            "success": True,
            "data": {
                "output_path": str(output_path.resolve()),
                "duration_seconds": duration,
                "sample_rate": SAMPLE_RATE,
                "file_size_bytes": file_size,
            },
        }))

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
