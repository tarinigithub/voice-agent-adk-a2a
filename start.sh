#!/usr/bin/env bash
# Start everything:
#   Agent Registry (port 8003)
#   capstone A2A servers (ports 8001, 8002) - if the capstone project is found; they register themselves
#   FastAPI backend (port 8000) and React dev server (port 5173)
set -euo pipefail
cd "$(dirname "$0")"

# The capstone repo cloned next to this one (adk-a2a-mcp-education-capstone); override with CAPSTONE_DIR.
if [ -z "${CAPSTONE_DIR:-}" ]; then
  for d in ../adk-a2a-mcp-education-capstone ../week5oct11AgentCapstoneProject; do
    [ -d "$d" ] && CAPSTONE_DIR="$d" && break
  done
fi
CAPSTONE_DIR="${CAPSTONE_DIR:-../adk-a2a-mcp-education-capstone}"
PIDS=()
trap 'kill "${PIDS[@]}" 2>/dev/null' EXIT

backend/.venv/bin/python -W ignore -m uvicorn registry:app --app-dir registry --port 8003 &
PIDS+=($!)
until curl -sf http://localhost:8003/agents >/dev/null; do sleep 1; done
echo "Agent registry ready: http://localhost:8003/agents"

if [ -x "$CAPSTONE_DIR/start_a2a.sh" ]; then
  "$CAPSTONE_DIR/start_a2a.sh" &
  PIDS+=($!)
  echo "Starting capstone school agent (A2A) from $CAPSTONE_DIR ..."
else
  echo "Capstone not found at $CAPSTONE_DIR - school questions will be unavailable."
fi

(cd backend && .venv/bin/python -W ignore -m uvicorn main:app --port 8000) &
PIDS+=($!)

cd frontend && npm run dev
