#!/bin/bash
# Fix WhatsApp context full issue in OpenClaw

echo '=== WhatsApp Context Fix Script ==='
echo ''

# Option 1: Clear session history
echo 'Option 1: Clear session history'
echo 'This will clear all chat history but keep the connection'
read -p 'Clear session history? (y/n): ' clear_sessions

if [ " \\ = \y\ ]; then
 echo 'Backing up sessions...'
 docker exec openclaw-kx9d-openclaw-1 find /data/.openclaw -name 'sessions.json' -exec cp {} {}.backup. \\;
 echo 'Clearing sessions...'
 docker exec openclaw-kx9d-openclaw-1 find /data/.openclaw -name 'sessions.json' -exec sh -c 'echo " -encodedCommand \ > {}' \\;
    echo 'âœ… Sessions cleared'
fi

# Option 2: Increase context limits
echo ''
echo 'Option 2: Check context limits in config'
docker exec openclaw-kx9d-openclaw-1 cat /data/.openclaw/openclaw.json | python3 -m json.tool | grep -i 'context\|limit\|max'

echo ''
echo 'Done!'
