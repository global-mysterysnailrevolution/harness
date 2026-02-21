# WhatsApp Context " Full\ Fix

## Problem

OpenClaw WhatsApp was saying \full\ when asked anything - this was due to context window being full from accumulated conversation history.

## Solution Applied

1. **Backed up all sessions** to /opt/harness/whatsapp-transcripts/
2. **Cleared session context** (the large skillsSnapshot.prompt field)
3. **Restarted OpenClaw** to apply changes

## Files Created

- /opt/harness/scripts/clear_whatsapp_context.sh - Script to clear context
- /opt/harness/whatsapp-transcripts/ - Backup location for all transcripts

## How to Use Again

If context gets full again:

`ash
ssh root@100.124.123.68
cd /opt/harness
bash scripts/clear_whatsapp_context.sh
`

This will:
- Backup current sessions
- Clear the context
- Restart OpenClaw

## Alternative: Increase Context Limits

If you want to allow more context before clearing, you can modify OpenClaw config:

`ash
# Edit config
docker exec -it openclaw-kx9d-openclaw-1 nano /data/.openclaw/openclaw.json

# Look for context/memory/limit settings and increase them
# Then restart: docker restart openclaw-kx9d-openclaw-1
`

## View Transcripts

All backed up transcripts are in:
/opt/harness/whatsapp-transcripts/

You can read them with:
`ash
cat /opt/harness/whatsapp-transcripts/sessions_backup_*.json | python3 -m json.tool
`
