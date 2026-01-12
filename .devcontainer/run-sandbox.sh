#!/bin/bash
# Quick script to run Claude Code in a sandboxed container
# Usage: ./run-sandbox.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# API key can come from ~/.claude/settings.json or env var
if [ -z "$ANTHROPIC_API_KEY" ] && [ ! -f "$HOME/.claude/settings.json" ]; then
    echo "WARNING: No ANTHROPIC_API_KEY env var and no ~/.claude/settings.json found"
    echo "Claude Code may not be able to authenticate."
fi

echo "Starting Claude Code sandbox..."
echo "Project directory: $PROJECT_DIR"
echo ""

cd "$SCRIPT_DIR"

# Build and run with docker-compose
docker compose up --build -d
docker compose exec claude-sandbox bash

# When done, stop the container
echo ""
echo "To stop the sandbox: docker compose -f $SCRIPT_DIR/docker-compose.yml down"
