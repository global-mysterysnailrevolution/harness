---
name: measure-scene
description: >
  Measure real-world distances and angles from two photos of the same scene.
  Quick path to "how far apart are these things?" from two camera angles.
---

# Measure Scene — Quick Distance Measurement from Two Photos

The user wants to measure real-world distances from photographs.

## Workflow

1. Ask the user for:
   - Two images of the same scene from different angles
   - A known reference distance (e.g., "the table is 1.5m long")
   - What they want to measure

2. Run the reconstruction:

```python
from stereorecon.scripting import reconstruct_auto
import json

result = reconstruct_auto(
    "$IMAGE1",
    "$IMAGE2",
    scale_point_a=0, scale_point_b=1,  # First two matched features
    scale_distance=$KNOWN_DISTANCE,
    unit="$UNIT",
    output_dir="./measurements",
    render_3d=False,
)

if result["success"]:
    print(f"Reconstruction quality: {result['reconstruction']['reprojection_error_px']:.2f}px error")
    print(f"Camera baseline: {result['scale']['camera_baseline']}m")
    print(f"\nDistances between matched points:")
    for d in result.get("distances", [])[:20]:
        print(f"  Point {d['from']} ↔ Point {d['to']}: {d['distance']} {result['scale']['unit']}")
else:
    for err in result["errors"]:
        print(f"Error: {err}")
```

3. Report the distances in plain language.

## If the user can identify specific features

Use `reconstruct_from_points` with labeled correspondences — see `/stereo` for the API.

## Accuracy expectations

| Condition | Expected accuracy |
|-----------|------------------|
| Known focal length + good baseline | 1-3% |
| EXIF focal length + good baseline | 3-5% |
| No focal length, estimated | 10-20% |
| Narrow baseline (cameras too close) | Poor — warn user |

Tell the user what accuracy to expect based on the warnings in the result.
