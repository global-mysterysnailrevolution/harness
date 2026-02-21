#!/usr/bin/env python3
"""analyze_reel_local.py

Glue script (local-only) that:
1) Calls igfetch localhost service to download the reel MP4
2) Generates keyframe timestamps + extracts JPEGs
3) Runs local Whisper transcription via whisper.cpp wrapper
4) Writes a results JSON stub (you can later plug vision summarization into it)

This is intended as a starting point to integrate into the harness repo.

Requirements:
- igfetch server running on localhost
- ffmpeg + ffprobe installed
- whisper.cpp binary + model installed (or adjust paths)

Usage:
  python3 analyze_reel_local.py --url 'https://www.instagram.com/reel/...' --outdir /opt/harness/igfetch/results

"""

import argparse
import json
import os
import subprocess
import time
import urllib.request


def sh(cmd):
    subprocess.run(cmd, check=True)


def http_post_json(url, headers, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--igfetch", default="http://127.0.0.1:8787/fetch")
    ap.add_argument("--token", default=os.environ.get("IGFETCH_TOKEN", ""))
    ap.add_argument("--base", default="/opt/harness/igfetch")
    ap.add_argument("--mode", choices=["balanced", "deep"], default="balanced")
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--min-gap", type=float, default=0.8)
    ap.add_argument("--outdir", default="/opt/harness/igfetch/results")
    args = ap.parse_args()

    if not args.token:
        raise SystemExit("Missing token. Provide --token or set IGFETCH_TOKEN in env.")

    base = os.path.abspath(args.base)
    results_dir = os.path.abspath(args.outdir)
    os.makedirs(results_dir, exist_ok=True)

    # 1) fetch
    r = http_post_json(args.igfetch, {"X-IGFETCH-TOKEN": args.token}, {"url": args.url})
    job_id = r["jobId"]
    mp4 = r["mp4Path"]

    # 2) keyframes
    frames_manifest = os.path.join(base, "frames", f"{job_id}.json")
    frames_dir = os.path.join(base, "frames", job_id)
    os.makedirs(os.path.dirname(frames_manifest), exist_ok=True)

    max_frames = 12 if args.mode == "balanced" else 25
    sh([
        "python3",
        os.path.join(os.path.dirname(__file__), "keyframes.py"),
        mp4,
        "--threshold",
        str(args.threshold),
        "--min-gap",
        str(args.min_gap),
        "--max-frames",
        str(max_frames),
        "--out-manifest",
        frames_manifest,
    ])

    sh([
        "python3",
        os.path.join(os.path.dirname(__file__), "extract_frames.py"),
        mp4,
        frames_manifest,
        frames_dir,
    ])

    # 3) transcript
    transcript_path = os.path.join(base, "results", f"{job_id}.transcript.txt")
    os.makedirs(os.path.dirname(transcript_path), exist_ok=True)
    sh([
        "python3",
        os.path.join(os.path.dirname(__file__), "transcribe_local_whispercpp.py"),
        mp4,
        "--out",
        transcript_path,
    ])

    # 4) results JSON stub
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read().strip()

    result = {
        "jobId": job_id,
        "url": args.url,
        "mp4Path": mp4,
        "framesDir": frames_dir,
        "framesManifest": frames_manifest,
        "transcriptPath": transcript_path,
        "transcript": transcript,
        "summary": None,
        "createdAt": int(time.time()),
    }

    out_json = os.path.join(results_dir, f"{job_id}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(out_json)


if __name__ == "__main__":
    main()
