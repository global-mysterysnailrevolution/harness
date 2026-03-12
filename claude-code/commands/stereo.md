---
name: stereo
description: >
  3D scene reconstruction from two camera images. Matches features or uses
  manual correspondences to compute geometry, triangulate points, and measure
  real-world distances. Use when the user wants to reconstruct, measure, or
  analyze a scene from two photos.
---

# StereoRecon — Two-Camera 3D Reconstruction

The user wants to do stereo 3D reconstruction. You have a full toolkit at
`~/stereo-3d-recon/` (package: `stereorecon`, already pip-installed).

## What you can do

1. **Reconstruct a 3D scene** from two images (auto feature matching or manual points)
2. **Measure real-world distances** between identified points
3. **Check image overlap** to see if two images will work
4. **Extract camera info** from EXIF metadata
5. **Export** point clouds (PLY) and scene data (JSON)

## How to use it

Write and execute a short Python script using the `stereorecon.scripting` API.
Do NOT use the CLI — use the scripting API so you can read and report the results.

### Automatic reconstruction (most common)

```python
from stereorecon.scripting import reconstruct_auto
import json

result = reconstruct_auto(
    "path/to/image1.jpg",
    "path/to/image2.jpg",
    # Optional — provide if known for better accuracy:
    # focal1_mm=26, sensor1_mm=36,
    # focal2_mm=26, sensor2_mm=36,
    # Scale reference — pick two auto-matched points with known distance:
    # scale_point_a=0, scale_point_b=1, scale_distance=1.5, unit="meters",
    output_dir="./stereo_output",
    render_3d=False,  # Set True if user wants to see the 3D plot
)
print(json.dumps(result, indent=2))
```

### Manual point correspondences (when user specifies points)

```python
from stereorecon.scripting import reconstruct_from_points
import json

result = reconstruct_from_points(
    "path/to/image1.jpg",
    "path/to/image2.jpg",
    correspondences=[
        # (x1, y1, x2, y2) — pixel coordinates in each image
        (100, 200, 150, 210),  # table corner A
        (300, 200, 340, 195),  # table corner B
        # ... at least 8 pairs needed
    ],
    labels=["corner_A", "corner_B"],  # optional
    scale_point_a=0, scale_point_b=1,
    scale_distance=1.2,  # known distance between corner_A and corner_B
    unit="meters",
    output_dir="./stereo_output",
    render_3d=False,
)
print(json.dumps(result, indent=2))
```

### Check if two images have enough overlap

```python
from stereorecon.scripting import check_overlap
import json
result = check_overlap("image1.jpg", "image2.jpg")
print(json.dumps(result, indent=2))
```

### Get camera info from EXIF

```python
from stereorecon.scripting import get_camera_info
import json
result = get_camera_info("photo.jpg")
print(json.dumps(result, indent=2))
```

## Key parameters

| Parameter | What it does | When to use |
|-----------|-------------|-------------|
| `focal1_mm` / `focal2_mm` | Camera focal length in mm | When user knows their camera specs |
| `sensor1_mm` / `sensor2_mm` | Sensor width in mm | Paired with focal length |
| `scale_point_a/b` | Indices of two matched points | When user wants real measurements |
| `scale_distance` | Known distance between those points | Required for metric output |
| `unit` | meters, millimeters, inches, feet | User preference |
| `method` | SIFT or ORB | ORB is faster, SIFT more accurate |
| `render_3d` | Show matplotlib 3D plot | When user wants visual output |

## Workflow guidance

1. **User provides two images** → run `check_overlap` first, then `reconstruct_auto`
2. **User wants measurements** → they need to specify a known distance for scale
3. **User specifies point pairs** → use `reconstruct_from_points`
4. **User asks about camera** → use `get_camera_info`
5. **Poor results?** → suggest: more overlap, provide focal length, pick better scale reference

## Reading the results

The result dict always has:
- `success`: bool
- `errors`: list of error strings
- `warnings`: list of warning strings
- `reconstruction.reprojection_error_px`: lower is better, <1.0 is excellent
- `reconstruction.inlier_ratio`: higher is better, >0.7 is good
- `distances`: list of pairwise distances (when scale is applied)

Report the key metrics and any warnings/errors to the user in plain language.

## Calibration for perception pipeline

If the user wants to calibrate cameras for the manipulation stack / perception
pipeline, use `/calibrate-stereo` instead — it exports in all the right formats
(ROS CameraInfo, TF transforms, perception_stereo.json).

```python
from stereorecon.scripting import calibrate_stereo
result = calibrate_stereo("left.jpg", "right.jpg", output_dir="./calibration_output")
# result["perception_config"] → path to load in perception_node
```

## Important notes

- The tool is at `~/stereo-3d-recon/` and is pip-installed as `stereorecon`
- Minimum 8 point correspondences needed (5 if intrinsics are known)
- Without a known reference distance, reconstruction is only up-to-scale
- EXIF focal length is auto-extracted when available
- Output files go to `output_dir`: scene.ply, scene.json, matches.jpg
- Calibration files integrate with `manipulation-stack/src/perception_pipeline/`
