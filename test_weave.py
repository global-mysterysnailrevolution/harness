#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Load .env file
env_file = Path('.env')
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value

# Now test Weave
sys.path.insert(0, 'scripts/observability')
from weave_tracing import init_weave
if init_weave():
    print('âœ… Weave initialized with .env file!')
else:
    print('âŒ Weave init failed')
