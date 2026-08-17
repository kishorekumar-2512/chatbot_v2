#!/usr/bin/env bash
# ==============================================================================
# health_check.sh — Smoke test & verify health of a target stack before cutover
# Usage:
#   ./scripts/health_check.sh blue
#   ./scripts/health_check.sh green
# ==============================================================================

set -euo pipefail

COLOR="${1:-}"
MAX_ATTEMPTS="${2:-12}"
SLEEP_INTERVAL="${3:-5}"

if [[ "$COLOR" == "blue" ]]; then
    BACKEND_PORT=8001
    WEB_PORT=8081
elif [[ "$COLOR" == "green" ]]; then
    BACKEND_PORT=8002
    WEB_PORT=8082
else
    echo "Usage: $0 {blue|green} [max_attempts] [sleep_interval]"
    exit 1
fi

echo "=========================================================="
echo " [HEALTH CHECK] Verifying ${COLOR^^} stack on internal ports:"
echo "   Backend: http://127.0.0.1:${BACKEND_PORT}/health"
echo "   Web SPA: http://127.0.0.1:${WEB_PORT}/"
echo "=========================================================="

# 1. Backend /health smoke test
echo "--> Checking Backend health..."
backend_ok=false
for i in $(seq 1 "$MAX_ATTEMPTS"); do
    status=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${BACKEND_PORT}/health" || true)
    if [[ "$status" == "200" ]]; then
        echo "✅ Backend (${COLOR^^}) is HEALTHY (attempt $i/$MAX_ATTEMPTS)"
        backend_ok=true
        break
    fi
    echo "   [Waiting] Backend returned HTTP $status. Retrying in ${SLEEP_INTERVAL}s... ($i/$MAX_ATTEMPTS)"
    sleep "$SLEEP_INTERVAL"
done

if [[ "$backend_ok" != "true" ]]; then
    echo "❌ Error: Backend (${COLOR^^}) failed health check after $MAX_ATTEMPTS attempts."
    exit 1
fi

# 2. Web UI smoke test
echo "--> Checking Web SPA health..."
web_ok=false
for i in $(seq 1 "$MAX_ATTEMPTS"); do
    status=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${WEB_PORT}/" || true)
    if [[ "$status" == "200" ]]; then
        echo "✅ Web SPA (${COLOR^^}) is HEALTHY (attempt $i/$MAX_ATTEMPTS)"
        web_ok=true
        break
    fi
    echo "   [Waiting] Web SPA returned HTTP $status. Retrying in ${SLEEP_INTERVAL}s... ($i/$MAX_ATTEMPTS)"
    sleep "$SLEEP_INTERVAL"
done

if [[ "$web_ok" != "true" ]]; then
    echo "❌ Error: Web SPA (${COLOR^^}) failed health check after $MAX_ATTEMPTS attempts."
    exit 1
fi

# 3. Settings Provider catalog verification (RAG & Model integrity)
echo "--> Checking API Provider catalog (/settings/providers)..."
providers_status=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${BACKEND_PORT}/settings/providers" || true)
if [[ "$providers_status" == "200" ]]; then
    echo "✅ Provider catalog verified (HTTP 200)"
else
    echo "⚠️ Warning: Provider catalog returned HTTP $providers_status"
fi

echo "=========================================================="
echo "✅ All smoke tests PASSED for ${COLOR^^} stack!"
echo "=========================================================="
