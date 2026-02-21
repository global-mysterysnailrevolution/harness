#!/usr/bin/env python3
"""keyframes.py

Keyframe timestamp selection using ffmpeg scene-change detection + optional uniform sampling.

Outputs a manifest JSON:
{
  "video": "/path/to/video.mp4",
  "threshold": 0.35,
  "min_gap": 0.8,
  "max_frames": 25,
  "uniform_fps": 0.5,
  "timestamps": [0.0, 1.2, 5.6, ...]
}

Requires: ffmpeg in PATH.
"""

import argparse
import json
import os
import re
import subprocess
from typing import List

PTS_RE = re.compile(r"pts_time:([0-9]+\.?[0-9]*)")


def run_scene_detect(video: str, threshold: float) -> List[float]:
    # We only need stderr where showinfo logs land.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        video,
        "-vf",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    # ffmpeg returns nonzero sometimes even on success; parse output anyway.
    ts = []
    for line in p.stderr.splitlines():
        m = PTS_RE.search(line)
        if m:
            try:
                ts.append(float(m.group(1)))
            except ValueError:
                pass
    return ts


def dedupe_and_cap(timestamps: List[float], min_gap: float, max_frames: int) -> List[float]:
    timestamps = sorted(set(round(t, 3) for t in timestamps if t >= 0))
    out: List[float] = []
    for t in timestamps:
        if not out or (t - out[-1]) >= min_gap:
            out.append(t)
        if len(out) >= max_frames:
            break
    return out


def uniform_samples(duration: float, fps: float, max_frames: int) -> List[float]:
    if fps <= 0:
        return []
    step = 1.0 / fps
    ts = []
    t = 0.0
    while t <= duration and len(ts) < max_frames:
        ts.append(round(t, 3))
        t += step
    return ts


def get_duration(video: str) -> float:
    # use ffprobe
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    try:
        return float(p.stdout.strip())
    except Exception:
        raise RuntimeError(f"Could not determine duration via ffprobe: {p.stderr[:300]}")


def merge_lists(a: List[float], b: List[float]) -> List[float]:
    return sorted(set(round(x, 3) for x in (a + b)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--min-gap", type=float, default=0.8)
    ap.add_argument("--max-frames", type=int, default=25)
    ap.add_argument("--uniform-fps", type=float, default=0.5, help="Fallback sampling rate (frames per second). 0.5 = 1 frame every 2s")
    ap.add_argument("--out-manifest", default="frames.json")
    args = ap.parse_args()

    video = os.path.abspath(args.video)
    dur = get_duration(video)

    scene_ts = run_scene_detect(video, args.threshold)
    scene_ts = dedupe_and_cap(scene_ts, args.min_gap, args.max_frames)

    # If scene detection yields too few points (common for static talking-head), add uniform samples.
    if len(scene_ts) < max(5, args.max_frames // 4):
        uni = uniform_samples(dur, args.uniform_fps, args.max_frames)
        merged = dedupe_and_cap(merge_lists(scene_ts, uni), args.min_gap, args.max_frames)
    else:
        merged = scene_ts

    manifest = {
        "video": video,
        "duration": dur,
        "threshold": args.threshold,
        "min_gap": args.min_gap,
        "max_frames": args.max_frames,
        "uniform_fps": args.uniform_fps,
        "timestamps": merged,
    }

    with open(args.out_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(args.out_manifest)


if __name__ == "__main__":
    main()
