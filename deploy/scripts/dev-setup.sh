#!/usr/bin/env bash
set -e

echo "=== Initializing IBVAP Local Development Environment ==="

# 1. Check Python and Node/pnpm
python3 --version || echo "Python 3 required"
node --version || echo "Node 20+ required"
pnpm --version || echo "pnpm required"

# 2. Install TypeScript dependencies
echo "Installing monorepo JavaScript/TypeScript dependencies..."
pnpm install

# 3. Install Python package dependencies in editable mode
echo "Installing core data contracts..."
pip install -e packages/core-types
pip install -e apps/central-gateway
pip install -e apps/edge-engine

echo "=== IBVAP Environment Ready ==="
