#!/usr/bin/env bash
# DeepNIDS launcher — bulletproof one-command start for presentations.
# Frees port 8000 first (so "address already in use" can never happen),
# activates the virtualenv, starts the server, and opens the browser.

set -e
cd "$(dirname "$0")"

echo "🧹  Freeing port 8000 (stopping any old server)…"
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 1

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "🛡️  Starting DeepNIDS → http://localhost:8000"
echo "    (wait for '✅ Models ready', then the page will go Live)"
echo "    Press Ctrl+C to stop."

# Open the browser a few seconds after launch (after model warm-up).
( sleep 5 && (open http://localhost:8000 2>/dev/null || true) ) &

exec python main.py
