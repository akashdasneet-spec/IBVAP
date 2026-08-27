#!/usr/bin/env bash
set -e

GATEWAY_HOST=${1:-"http://localhost:8000"}

echo "Checking Central Gateway liveness..."
curl -f -s "${GATEWAY_HOST}/health/liveness" | grep -q "ALIVE" && echo "✓ Gateway is Alive"

echo "Checking Central Gateway readiness..."
curl -f -s "${GATEWAY_HOST}/health/readiness" | grep -q "READY" && echo "✓ Gateway is Ready"
