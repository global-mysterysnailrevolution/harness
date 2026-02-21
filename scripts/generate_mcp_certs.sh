#!/bin/bash
# Generate self-signed TLS certs and Bearer token for MCP bridges
# Run once: ./generate_mcp_certs.sh
# Output: /opt/harness/.mcp/certs/ and MCP_BEARER_TOKEN in .env

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="$(dirname "$SCRIPT_DIR")"
CERT_DIR="${HARNESS_DIR}/.mcp/certs"
ENV_FILE="${HARNESS_DIR}/.env"

mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

# Generate self-signed cert (valid 365 days)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -subj "/CN=mcp-harness-local/O=Harness" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:172.17.0.1"

# Generate Bearer token (32 random bytes, hex)
TOKEN=$(openssl rand -hex 32)

echo "Generated certs in $CERT_DIR"
echo "Generated Bearer token (add to .env)"

# Append to .env (or create)
touch "$ENV_FILE"
if grep -q "MCP_BEARER_TOKEN" "$ENV_FILE"; then
  echo "MCP_BEARER_TOKEN already in .env - not overwriting"
else
  echo "" >> "$ENV_FILE"
  echo "# MCP bridge security (from generate_mcp_certs.sh)" >> "$ENV_FILE"
  echo "MCP_BEARER_TOKEN=$TOKEN" >> "$ENV_FILE"
  echo "MCP_HTTPS_KEY=$CERT_DIR/key.pem" >> "$ENV_FILE"
  echo "MCP_HTTPS_CERT=$CERT_DIR/cert.pem" >> "$ENV_FILE"
  echo "MCP_ALLOW_LOCAL=1" >> "$ENV_FILE"
  echo "MCP_BIND=0.0.0.0" >> "$ENV_FILE"
  echo "Added MCP_* to $ENV_FILE"
fi

echo ""
echo "=== Add to OpenClaw MCP config (use HTTPS URLs): ==="
echo "  filesystem: https://172.17.0.1:8101/mcp"
echo "  fetch:      https://172.17.0.1:8102/mcp"
echo "  github:     https://172.17.0.1:8103/mcp"
echo "  time:       https://172.17.0.1:8104/mcp"
echo ""
echo "Bearer token (for manual config): $TOKEN"
echo ".mcp/certs/ and .env should be in .gitignore"
