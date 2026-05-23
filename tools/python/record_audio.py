import sys
import json
import numpy as np
from pathlib import Path

SAMPLE_RATE = 16000   # 16 kHz mono — native Whisper format, avoids resampling in groq_stt
CHUNK_MS = 30         # 30 ms chunks — responsive without excess CPU
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_MS / 1000)

# Calibration: sample this many chunks of ambient noise before listening
CALIBRATION_CHUNKS = 17   # ≈ 0.5 s

# State machine
_WAITING  = "waiting"   # haven't heard speech yet
_SPEAKING = "speaking"  # actively hearing speech
_DONE     = "done"      # silence detected after speech → stop


def _rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: record_audio.py <output_path> [max_seconds] [silence_duration]",
        }))
        sys.exit(1)

    output_path = Path(sys.argv[1])

    try:
        max_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    except ValueError:
        print(json.dumps({"success": False, "error": "max_seconds must be a number"}))
        sys.exit(1)

    try:
        # silence_duration: consecutive seconds of quiet after speech that triggers stop
        silence_duration = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
    except ValueError:
        print(json.dumps({"success": False, "error": "silence_duration must be a number"}))
        sys.exit(1)

    if not (1.0 <= max_seconds <= 120.0):
        print(json.dumps({"success": False, "error": "max_seconds must be between 1 and 120"}))
        sys.exit(1)

    if not (0.3 <= silence_duration <= 10.0):
        print(json.dumps({"success": False, "error": "silence_duration must be between 0.3 and 10"}))
        sys.exit(1)

    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        print(json.dumps({"success": False, "error": f"Missing dependency: {exc}. Run: pip install sounddevice soundfile"}))
        sys.exit(1)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # ── Phase 1: calibrate ambient noise ────────────────────────────────
        print("[record_audio] Calibrating ambient noise...", file=sys.stderr)
        cal_frames = []
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=CHUNK_FRAMES) as stream:
            for _ in range(CALIBRATION_CHUNKS):
                chunk, _ = stream.read(CHUNK_FRAMES)
                cal_frames.append(chunk.copy())

        ambient_rms = _rms(np.concatenate(cal_frames))

        # Speech threshold: must be clearly louder than ambient noise
        speech_rms   = max(ambient_rms * 8, 50.0)
        # Silence threshold: back down near ambient after speaking
        silence_rms  = ambient_rms * 3

        print(f"[record_audio] Ambient RMS: {ambient_rms:.1f} | "
              f"Speech threshold: {speech_rms:.1f} | "
              f"Silence threshold: {silence_rms:.1f}", file=sys.stderr)
        print(f"[record_audio] Listening (max {max_seconds}s, "
              f"stops after {silence_duration}s of silence)...", file=sys.stderr)

        # ── Phase 2: record with VAD state machine ───────────────────────────
        silence_chunks_needed = int(silence_duration * 1000 / CHUNK_MS)
        max_chunks = int(max_seconds * 1000 / CHUNK_MS)

        frames = []
        state = _WAITING
        silent_chunks = 0

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=CHUNK_FRAMES) as stream:
            for _ in range(max_chunks):
                chunk, _ = stream.read(CHUNK_FRAMES)
                rms = _rms(chunk)

                if state == _WAITING:
                    if rms > speech_rms:
                        state = _SPEAKING
                        print(f"[record_audio] Speech detected (RMS={rms:.1f})", file=sys.stderr)
                    # Don't record pre-speech silence — start capturing only once speech begins
                    frames.append(chunk.copy())

                elif state == _SPEAKING:
                    frames.append(chunk.copy())
                    if rms <= silence_rms:
                        silent_chunks += 1
                        if silent_chunks >= silence_chunks_needed:
                            print("[record_audio] Silence detected — stopping.", file=sys.stderr)
                            state = _DONE
                            break
                    else:
                        silent_chunks = 0

        if state == _WAITING:
            print("[record_audio] No speech detected within time limit.", file=sys.stderr)

        recording = np.concatenate(frames, axis=0) if frames else np.zeros((0, 1), dtype="int16")
        actual_seconds = round(len(recording) / SAMPLE_RATE, 2)

        sf.write(str(output_path), recording, SAMPLE_RATE, subtype="PCM_16")

        print(json.dumps({
            "success": True,
            "data": {
                "output_path": str(output_path.resolve()),
                "duration_seconds": actual_seconds,
                "max_seconds": max_seconds,
                "silence_duration": silence_duration,
                "ambient_rms": round(ambient_rms, 1),
                "sample_rate": SAMPLE_RATE,
                "file_size_bytes": output_path.stat().st_size,
            },
        }))

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
