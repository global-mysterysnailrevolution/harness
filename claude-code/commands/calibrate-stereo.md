---
name: calibrate-stereo
description: >
  Calibrate two cameras for stereo vision and export calibration files
  for the manipulation-stack perception pipeline. Generates ROS CameraInfo,
  OpenCV calibration, TF transforms, and native perception config.
---

# Calibrate Stereo — Camera Calibration for Perception Pipeline

The user wants to calibrate two cameras for stereo vision. This generates
calibration files that the manipulation-stack perception pipeline can load
directly via `load_stereo_calibration()`.

## What this produces

| File | Format | Used by |
|------|--------|---------|
| `camera_left.yaml` | ROS CameraInfo YAML | camera_info_manager, ROS publishers |
| `camera_right.yaml` | ROS CameraInfo YAML | camera_info_manager, ROS publishers |
| `stereo_calibration.yaml` | OpenCV FileStorage | cv2.FileStorage, any OpenCV code |
| `tf_static.yaml` | ROS TF2 config | static_transform_publisher |
| `perception_stereo.json` | Native JSON | `perception_node.py` stereo_calibration_file param |
| `calibration_full.json` | Complete JSON | Debugging, manual inspection |
| `matches.jpg` | Image | Visual verification of feature matches |

## How to calibrate

```python
from stereorecon.scripting import calibrate_stereo
import json

result = calibrate_stereo(
    "$IMAGE1",           # Left camera image
    "$IMAGE2",           # Right camera image

    # Camera specs (optional but recommended for accuracy):
    # focal1_mm=26.0,    # Left camera focal length in mm
    # sensor1_mm=36.0,   # Left camera sensor width in mm
    # focal2_mm=26.0,    # Right camera focal length in mm
    # sensor2_mm=36.0,   # Right camera sensor width in mm

    # Scale reference — ONE of these:
    # baseline_meters=0.12,  # If you measured the camera-to-camera distance
    # OR:
    # scale_distance=1.5,    # Known distance between two scene points
    # scale_point_a=0,       # Index of first reference point
    # scale_point_b=1,       # Index of second reference point

    output_dir="./calibration_output",

    # ROS frame names (customize for your URDF):
    camera1_name="camera_left",
    camera2_name="camera_right",
    parent_frame="camera_left_optical",
    child_frame="camera_right_optical",
)

print(json.dumps(result, indent=2, default=str))
```

## Loading in the perception pipeline

Once calibration files are generated, the perception pipeline loads them via:

```yaml
# In your ROS launch params:
perception_node:
  ros__parameters:
    stereo_mode: true
    stereo_calibration_file: "/path/to/calibration_output/perception_stereo.json"
    camera_topic_rgb: "/camera_left/rgb"
    camera_topic_depth: "/camera_left/depth"
    camera_topic_rgb_right: "/camera_right/rgb"
    camera_topic_depth_right: "/camera_right/depth"
```

Or in Python:
```python
from perception_pipeline.camera_bridge import load_stereo_calibration
sc = load_stereo_calibration("./calibration_output/perception_stereo.json")
# sc.left, sc.right — CameraIntrinsics
# sc.R, sc.T — extrinsics
# sc.baseline — in metres
```

## For the manipulation stack specifically

The calibration integrates with:
- **camera_bridge.py**: `StereoCalibration` dataclass, `load_stereo_calibration()`
- **perception_node.py**: `stereo_calibration_file` param enables stereo mode
- **stereo depth**: When no depth sensor exists, computes depth from stereo disparity
- **rectification**: `rectify_stereo_pair()` aligns epipolar lines
- **TF2**: `tf_static.yaml` publishes the camera-to-camera transform

## Accuracy tips

- **Provide focal length + sensor width** for both cameras (best accuracy)
- **Measure the baseline** between cameras if possible (ruler between lens centers)
- **Take calibration photos with good overlap** (60-80% shared scene)
- **Include objects at various depths** (not just a flat wall)
- **Avoid coplanar points** (fundamental matrix becomes degenerate)
- **Check reprojection error**: <1px excellent, <3px good, >5px recalibrate

## Quick pre-flight

```python
from stereorecon.scripting import check_overlap
result = check_overlap("$IMAGE1", "$IMAGE2")
print(f"Quality: {result['quality']} ({result['good_matches']} matches)")
```
