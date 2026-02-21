#!/usr/bin/env python3
"""transcribe_local_whispercpp.py

Wrapper around whisper.cpp-style binary.

Assumes:
- ffmpeg is installed
- whisper.cpp binary exists (default: /opt/harness/igfetch/bin/whisper/main)
- a ggml model exists (default: /opt/harness/igfetch/models/ggml-base.en.bin)

Usage:
  python3 transcribe_local_whispercpp.py input.mp4 --out transcript.txt

This script:
- extracts mono 16kHz WAV to a temp file
- runs whisper.cpp
- writes transcript
"""

import argparse
import os
import subprocess
import tempfile


def run(cmd):
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--whisper-bin", default="/opt/harness/igfetch/bin/whisper/main")
    ap.add_argument("--model", default="/opt/harness/igfetch/models/ggml-base.en.bin")
    ap.add_argument("--language", default="en")
    ap.add_argument("--out", default="transcript.txt")
    args = ap.parse_args()

    video = os.path.abspath(args.video)
    out = os.path.abspath(args.out)

    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "audio.wav")
        # Extract audio
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])

        # whisper.cpp emits output files based on -of prefix. We'll use a temp prefix and read .txt.
        prefix = os.path.join(td, "whisper_out")
        cmd = [
            args.whisper_bin,
            "-m",
            args.model,
            "-f",
            wav,
            "-l",
            args.language,
            "-of",
            prefix,
            "-otxt",
        ]
        run(cmd)
        txt_path = prefix + ".txt"
        if not os.path.exists(txt_path):
            raise RuntimeError(f"Expected transcript at {txt_path} but not found")

        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)

    print(out)


if __name__ == "__main__":
    main()
