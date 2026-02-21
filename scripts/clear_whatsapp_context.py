#!/usr/bin/env python3
"""Clear WhatsApp/OpenClaw context to fix 'full' issue"""
import json
import sys
from pathlib import Path
from datetime import datetime
import subprocess

BACKUP_DIR = Path('/opt/harness/whatsapp-transcripts')
BACKUP_DIR.mkdir(exist_ok=True)

sessions_file = '/data/.openclaw/agents/main/sessions/sessions.json'

print('=== Clearing OpenClaw WhatsApp Context ===')
print('')

# Backup
print('1. Backing up current sessions...')
try:
    result = subprocess.run(
        ['docker', 'exec', 'openclaw-kx9d-openclaw-1', 'cat', sessions_file],
        capture_output=True,
        text=True,
        check=True
    )
    
    backup_file = BACKUP_DIR / f'sessions_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    backup_file.write_text(result.stdout)
    print(f'   ✅ Saved to: {backup_file}')
    
    # Clear context
    print('')
    print('2. Clearing session context...')
    data = json.loads(result.stdout)
    
    for session_id in data:
        if 'skillsSnapshot' in data[session_id]:
            data[session_id]['skillsSnapshot']['prompt'] = ''
    
    # Write back
    cleared_json = json.dumps(data, indent=2)
    subprocess.run(
        ['docker', 'exec', '-i', 'openclaw-kx9d-openclaw-1', 'sh', '-c', f'cat > {sessions_file}'],
        input=cleared_json,
        text=True,
        check=True
    )
    
    print('   ✅ Session context cleared')
    
    # Restart
    print('')
    print('3. Restarting OpenClaw...')
    subprocess.run(['docker', 'restart', 'openclaw-kx9d-openclaw-1'], check=True)
    
    print('')
    print('✅ Done! WhatsApp context has been cleared.')
    print('   OpenClaw should now respond without "full" errors.')
    print('')
    print(f'📁 Transcripts saved to: {BACKUP_DIR}/')
    
except Exception as e:
    print(f'❌ Error: {e}', file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
