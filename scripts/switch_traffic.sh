#!/usr/bin/env bash
# ==============================================================================
# switch_traffic.sh — Zero-downtime Blue/Green traffic cutover & rollback script
# Usage:
#   ./scripts/switch_traffic.sh blue
#   ./scripts/switch_traffic.sh green
# ==============================================================================

set -euo pipefail

TARGET_COLOR="${1:-}"

if [[ "$TARGET_COLOR" != "blue" && "$TARGET_COLOR" != "green" ]]; then
    echo "Usage: $0 {blue|green}"
    exit 1
fi

NGINX_DIR="${NGINX_CONF_DIR:-/etc/nginx/conf.d}"
ACTIVE_CONF="${NGINX_DIR}/upstream_active.conf"
SOURCE_CONF="$(dirname "$0")/../nginx/upstream_${TARGET_COLOR}.conf"

echo "=========================================================="
echo " [TRAFFIC SWITCH] Cutting over active traffic to: ${TARGET_COLOR^^}"
echo "=========================================================="

if [[ ! -f "$SOURCE_CONF" ]]; then
    echo "❌ Error: Upstream source file not found: $SOURCE_CONF"
    exit 1
fi

# Copy target upstream config to the active config location
if command -v sudo >/dev/null 2>&1; then
    sudo cp "$SOURCE_CONF" "$ACTIVE_CONF"
    echo "Testing Nginx configuration..."
    sudo nginx -t
    echo "Reloading Nginx (zero-downtime)..."
    sudo nginx -s reload
else
    cp "$SOURCE_CONF" "$ACTIVE_CONF"
    nginx -t
    nginx -s reload
fi

# Record current active state
echo "$TARGET_COLOR" > "$(dirname "$0")/../.active_color"

echo "✅ Traffic successfully switched to ${TARGET_COLOR^^}!"
