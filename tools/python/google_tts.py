import sys
import os
import json
from pathlib import Path

VALID_ENCODINGS = {"MP3", "LINEAR16", "OGG_OPUS", "MULAW", "ALAW"}


def _build_credentials():
    from google.oauth2.credentials import Credentials

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    access_token = os.environ.get("GOOGLE_ACCESS_TOKEN")

    missing = [k for k, v in {
        "GOOGLE_CLIENT_ID": client_id,
        "GOOGLE_CLIENT_SECRET": client_secret,
        "GOOGLE_REFRESH_TOKEN": refresh_token,
    }.items() if not v]
    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")

    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )


def main():
    try:
        params = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {exc}"}))
        sys.exit(1)

    text = params.get("text", "").strip()
    output_path_str = params.get("output_path", "").strip()
    voice = params.get("voice", "en-US-Neural2-A")
    language_code = params.get("language_code", "en-US")
    audio_encoding = params.get("audio_encoding", "MP3").upper()

    if not text:
        print(json.dumps({"success": False, "error": "text is required and cannot be empty"}))
        sys.exit(1)
    if not output_path_str:
        print(json.dumps({"success": False, "error": "output_path is required"}))
        sys.exit(1)
    if audio_encoding not in VALID_ENCODINGS:
        print(json.dumps({"success": False, "error": f"Invalid audio_encoding {audio_encoding!r}. Valid: {', '.join(sorted(VALID_ENCODINGS))}"}))
        sys.exit(1)

    try:
        from google.cloud import texttospeech
    except ImportError:
        print(json.dumps({"success": False, "error": "google-cloud-texttospeech not installed — run: pip install google-cloud-texttospeech"}))
        sys.exit(1)

    try:
        creds = _build_credentials()
    except (ValueError, ImportError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)

    encoding_map = {
        "MP3": texttospeech.AudioEncoding.MP3,
        "LINEAR16": texttospeech.AudioEncoding.LINEAR16,
        "OGG_OPUS": texttospeech.AudioEncoding.OGG_OPUS,
        "MULAW": texttospeech.AudioEncoding.MULAW,
        "ALAW": texttospeech.AudioEncoding.ALAW,
    }

    try:
        output_path = Path(output_path_str)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        client = texttospeech.TextToSpeechClient(credentials=creds)

        is_ssml = text.strip().startswith("<speak>")
        synthesis_input = (
            texttospeech.SynthesisInput(ssml=text)
            if is_ssml
            else texttospeech.SynthesisInput(text=text)
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice,
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=encoding_map[audio_encoding]
            ),
        )

        if not response.audio_content:
            print(json.dumps({"success": False, "error": "No audio content returned from Google TTS"}))
            sys.exit(1)

        output_path.write_bytes(response.audio_content)

        print(json.dumps({
            "success": True,
            "data": {
                "output_path": str(output_path.resolve()),
                "bytes": len(response.audio_content),
                "voice": voice,
                "language_code": language_code,
                "audio_encoding": audio_encoding,
                "char_count": len(text),
            },
        }))

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
