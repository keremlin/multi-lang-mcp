import sys
import json
import time
import collections
import numpy as np
from pathlib import Path

SAMPLE_RATE = 16000   # 16 kHz mono — native Whisper format, avoids resampling in groq_stt
CHUNK_MS = 50         # process audio in 50 ms chunks
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_MS / 1000)


def _rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: record_audio.py <output_path> [max_seconds] [silence_threshold]",
        }))
        sys.exit(1)

    output_path = Path(sys.argv[1])

    try:
        max_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    except ValueError:
        print(json.dumps({"success": False, "error": "max_seconds must be a number"}))
        sys.exit(1)

    try:
        # silence_threshold: RMS amplitude below which audio is considered silence (0–32767 scale)
        silence_threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
    except ValueError:
        print(json.dumps({"success": False, "error": "silence_threshold must be a number"}))
        sys.exit(1)

    if not (1.0 <= max_seconds <= 120.0):
        print(json.dumps({"success": False, "error": "max_seconds must be between 1 and 120"}))
        sys.exit(1)

    # Silence window: stop after this many consecutive seconds below threshold
    SILENCE_WINDOW_SEC = 1.5
    silence_chunks_needed = int(SILENCE_WINDOW_SEC * 1000 / CHUNK_MS)

    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        print(json.dumps({"success": False, "error": f"Missing dependency: {exc}. Run: pip install sounddevice soundfile"}))
        sys.exit(1)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        frames: list[np.ndarray] = []
        silent_chunks = 0
        max_chunks = int(max_seconds * 1000 / CHUNK_MS)
        speech_detected = False

        print(f"[record_audio] Listening (max {max_seconds}s, silence threshold {silence_threshold})...", file=sys.stderr)

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK_FRAMES) as stream:
            for _ in range(max_chunks):
                chunk, _ = stream.read(CHUNK_FRAMES)
                frames.append(chunk.copy())
                rms = _rms(chunk)

                if rms > silence_threshold:
                    speech_detected = True
                    silent_chunks = 0
                else:
                    if speech_detected:
                        silent_chunks += 1
                        if silent_chunks >= silence_chunks_needed:
                            print("[record_audio] Silence detected — stopping.", file=sys.stderr)
                            break

        recording = np.concatenate(frames, axis=0)
        actual_seconds = round(len(recording) / SAMPLE_RATE, 2)

        sf.write(str(output_path), recording, SAMPLE_RATE, subtype="PCM_16")

        print(json.dumps({
            "success": True,
            "data": {
                "output_path": str(output_path.resolve()),
                "duration_seconds": actual_seconds,
                "max_seconds": max_seconds,
                "silence_threshold": silence_threshold,
                "sample_rate": SAMPLE_RATE,
                "file_size_bytes": output_path.stat().st_size,
            },
        }))

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
