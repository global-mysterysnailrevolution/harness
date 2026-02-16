#!/bin/bash
set -e
TOKEN="${1:-zcFgheV07W4MmJvlXPa68AIBkisnQ25t}"
echo "IGFETCH_TOKEN=$TOKEN" > /opt/harness/igfetch/.env
chown igfetch:igfetch /opt/harness/igfetch/.env
chmod 600 /opt/harness/igfetch/.env
cp /tmp/igfetch.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable igfetch
systemctl start igfetch
systemctl status igfetch --no-pager
echo ""
echo "Token: $TOKEN"
echo "Server: 127.0.0.1:8787"
