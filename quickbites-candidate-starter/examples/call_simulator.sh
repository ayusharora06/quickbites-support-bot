#!/usr/bin/env bash
# Minimal example: open a dev session and send one reply.
# Run after filling in .env with SIMULATOR_BASE_URL.

set -euo pipefail

BASE=${SIMULATOR_BASE_URL:-http://localhost:8000}
TOKEN=${CANDIDATE_TOKEN:-demo}

echo "== health =="
curl -s "$BASE/healthz" | jq .

echo "== start dev session (scenario 1) =="
START=$(curl -s -X POST "$BASE/v1/session/start" \
    -H 'Content-Type: application/json' \
    -H "X-Candidate-Token: $TOKEN" \
    -d '{"mode":"dev","scenario_id":1}')
echo "$START" | jq .
SID=$(echo "$START" | jq -r .session_id)

echo "== send one reply =="
curl -s -X POST "$BASE/v1/session/$SID/reply" \
    -H 'Content-Type: application/json' \
    -H "X-Candidate-Token: $TOKEN" \
    -d '{
      "bot_message":"I am sorry to hear that. Could you tell me what was wrong with the biryani?",
      "actions":[]
    }' | jq .

echo "== get transcript (dev only) =="
curl -s "$BASE/v1/session/$SID/transcript" \
    -H "X-Candidate-Token: $TOKEN" | jq .
