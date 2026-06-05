import os
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from shared import download_progress as _dp
    _DP_OK = True
except Exception:
    _DP_OK = False


def _get_source_info(probe_data: dict) -> dict:
    info = {
        "width": None,
        "height": None,
        "fps": None,
        "duration": None,
        "video_codec": None,
        "audio_codec": None,
    }
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video" and info["width"] is None:
            info["width"] = stream.get("width")
            info["height"] = stream.get("height")
            info["video_codec"] = stream.get("codec_name")
            fps_str = stream.get("r_frame_rate", "30/1")
            try:
                num, den = fps_str.split("/")
                info["fps"] = round(float(num) / float(den), 3)
            except Exception:
                info["fps"] = None
        if stream.get("codec_type") == "audio" and info["audio_codec"] is None:
            info["audio_codec"] = stream.get("codec_name")
    try:
        info["duration"] = round(float(probe_data.get("format", {}).get("duration", 0) or 0), 2)
    except Exception:
        pass
    return info


def main():
    import json

    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No input provided — pass JSON on stdin"}))
        sys.exit(1)

    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {exc}"}))
        sys.exit(1)

    input_path = params.get("input_path", "").strip()
    if not input_path:
        print(json.dumps({"success": False, "error": "input_path is required"}))
        sys.exit(1)

    crf = params.get("crf", 23)
    preset = params.get("preset", "medium")
    dl_id = params.get("dl_id", "")

    valid_presets = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
    if preset not in valid_presets:
        print(json.dumps({"success": False, "error": f"Invalid preset '{preset}'. Choose from: {', '.join(sorted(valid_presets))}"}))
        sys.exit(1)

    try:
        crf = int(crf)
        if not (0 <= crf <= 51):
            raise ValueError
    except (TypeError, ValueError):
        print(json.dumps({"success": False, "error": "crf must be an integer between 0 and 51"}))
        sys.exit(1)

    input_file = Path(input_path)
    if not input_file.exists():
        print(json.dumps({"success": False, "error": f"File not found: {input_path}"}))
        sys.exit(1)

    output_path = params.get("output_path", "").strip()
    if not output_path:
        output_path = str(input_file.parent / (input_file.stem + "_lg.mp4"))

    try:
        import ffmpeg
    except ImportError:
        print(json.dumps({"success": False, "error": "ffmpeg-python not installed — run: pip install ffmpeg-python"}))
        sys.exit(1)

    try:
        probe = ffmpeg.probe(str(input_file))
    except ffmpeg.Error as exc:
        stderr_msg = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
        print(json.dumps({"success": False, "error": f"ffprobe failed: {stderr_msg}"}))
        sys.exit(1)

    source_info = _get_source_info(probe)
    source_fps = source_info["fps"] or 30.0
    duration_s = source_info.get("duration") or 0.0

    # Register in progress UI
    if dl_id and _DP_OK:
        try:
            _dp.update(dl_id, pid=os.getpid(), status="converting",
                       name=input_file.name, pct=0)
        except Exception:
            pass

    start_time = time.monotonic()

    try:
        stream = ffmpeg.input(str(input_file))
        video = stream.video
        audio = stream.audio

        video = (
            video
            .filter("scale",
                    w="min(iw,1920)",
                    h="min(ih,1080)",
                    force_original_aspect_ratio="decrease")
            .filter("pad", "ceil(iw/2)*2", "ceil(ih/2)*2")
        )

        if source_fps > 30.0:
            video = video.filter("fps", fps=30)

        out = ffmpeg.output(
            video, audio, output_path,
            vcodec="libx264", acodec="aac",
            crf=crf, preset=preset, movflags="+faststart",
        )

        # Build command and inject -progress pipe:1 for real-time progress
        cmd = ffmpeg.compile(out, overwrite_output=True)
        cmd = [cmd[0], "-progress", "pipe:1", "-nostats"] + cmd[1:]

        no_win = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=no_win,
        )

        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key == "out_time_ms" and duration_s > 0 and dl_id and _DP_OK:
                try:
                    pct = min(round(int(val) / 1000 / duration_s * 100, 1), 99)
                    _dp.update(dl_id, status="converting", pct=pct)
                except Exception:
                    pass

        proc.wait()

        if proc.returncode not in (0, None):
            raise RuntimeError(f"FFmpeg exited with code {proc.returncode}")

    except Exception as exc:
        if dl_id and _DP_OK:
            try:
                _dp.fail(dl_id, str(exc))
            except Exception:
                pass
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)

    elapsed = round(time.monotonic() - start_time, 1)
    output_file = Path(output_path)
    output_size = output_file.stat().st_size if output_file.exists() else 0
    input_size = input_file.stat().st_size

    if dl_id and _DP_OK:
        try:
            _dp.complete(dl_id, name=input_file.name, saved_to=str(output_file.resolve()),
                         size_mb=round(output_size / (1024 * 1024), 2))
        except Exception:
            pass

    print(json.dumps({
        "success": True,
        "data": {
            "input_path": str(input_file.resolve()),
            "output_path": str(output_file.resolve()),
            "output_format": {
                "container": "mp4",
                "video_codec": "h264",
                "audio_codec": "aac",
                "max_resolution": "1920x1080",
                "max_fps": 30,
                "crf": crf,
                "preset": preset,
            },
            "source_info": source_info,
            "input_size_bytes": input_size,
            "input_size_mb": round(input_size / (1024 * 1024), 2),
            "output_size_bytes": output_size,
            "output_size_mb": round(output_size / (1024 * 1024), 2),
            "elapsed_seconds": elapsed,
        },
    }))


if __name__ == "__main__":
    main()
