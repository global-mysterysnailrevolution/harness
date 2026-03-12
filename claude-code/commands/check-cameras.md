---
name: check-cameras
description: >
  Check if two images are suitable for stereo reconstruction. Tests feature
  overlap and extracts camera info from EXIF. Quick pre-flight before /stereo.
---

# Check Cameras — Pre-flight for Stereo Reconstruction

Quick diagnostic: will these two images work for 3D reconstruction?

Run this script, then report the findings:

```python
from stereorecon.scripting import check_overlap, get_camera_info
import json

# Check overlap between the two images
overlap = check_overlap("$IMAGE1", "$IMAGE2")
print("=== Overlap Check ===")
print(json.dumps(overlap, indent=2))

# Camera info
for img in ["$IMAGE1", "$IMAGE2"]:
    info = get_camera_info(img)
    print(f"\n=== Camera: {img} ===")
    print(json.dumps(info, indent=2))
```

## How to report results

- **Quality: excellent/good** → "These images are great for reconstruction"
- **Quality: marginal** → "These should work but accuracy might suffer. More overlap would help."
- **Quality: poor/insufficient** → "Not enough visual overlap. Try: (1) pointing both cameras at more of the same scene, (2) moving cameras closer together, (3) ensuring good lighting"

- **EXIF intrinsics found** → "Camera focal length detected automatically — good accuracy expected"
- **No EXIF** → "No camera info in the images. For best accuracy, tell me the focal length and sensor size of each camera."

Replace `$IMAGE1` and `$IMAGE2` with the actual image paths from the user's message.
