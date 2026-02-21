#!/usr/bin/env python3
"""extract_frames.py

Extract JPEG frames from a video at timestamps defined in a manifest produced by keyframes.py.

Usage:
  python3 extract_frames.py /path/to/video.mp4 frames.json /out/dir

Requires: ffmpeg.
"""

import argparse
import json
import os
import subprocess


def extract_one(video: str, t: float, out_path: str):
    # -ss before -i is faster seek for most videos; accuracy is good enough for keyframes.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(t),
        "-i",
        video,
        "-frames:v",
        "1",
        "-q:v",
        "3",
        out_path,
    ]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("manifest")
    ap.add_argument("outdir")
    args = ap.parse_args()

    video = os.path.abspath(args.video)
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    with open(args.manifest, "r", encoding="utf-8") as f:
        m = json.load(f)

    ts = m.get("timestamps") or []
    for i, t in enumerate(ts, 1):
        out_path = os.path.join(outdir, f"frame_{i:03d}_{t:.3f}.jpg")
        extract_one(video, float(t), out_path)

    print(outdir)


if __name__ == "__main__":
    main()
