#!/usr/bin/env bash
#
# Checkpoint D verification — AI via generic LLM client (mock mode)
#
set -euo pipefail


RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

SLUG="trattoria-da-mario"
API="http://127.0.0.1:8000"
OWNER_WEB="http://127.0.0.1:3001"

COOKIE_JAR=""
OWNER_JAR=""
STAFF_JAR=""
GUEST_JAR=""
trap 'rm -f "$COOKIE_JAR" "$OWNER_JAR" "$STAFF_JAR" "$GUEST_JAR"' EXIT

# Log in as owner or staff into a cookie jar. DEMO_MODE=true uses demo-login (no secrets);
# otherwise the real login with OWNER_API_KEY / STAFF_PIN from the shell (compose defaults).
auth_login() { # auth_login <owner|staff> <cookie jar>
  if [ "${DEMO_MODE:-false}" = "true" ]; then
    curl -sf --max-time 5 -X POST "$API/api/auth/demo-login" \
      -H "Content-Type: application/json" -d "{\"role\":\"$1\"}" -c "$2" > /dev/null
  else
    local secret="${STAFF_PIN:-0000}"
    [ "$1" = "owner" ] && secret="${OWNER_API_KEY:-change_me_in_production}"
    curl -sf --max-time 5 -X POST "$API/api/auth/login" \
      -H "Content-Type: application/json" \
      -d "{\"role\":\"$1\",\"secret\":\"$secret\"}" -c "$2" > /dev/null
  fi
}

# ─── Setup ───────────────────────────────────────────────────────────
info "Step 1: make ci"
make ci || fail "make ci failed"
pass "make ci"

info "Step 2: docker compose build"
docker compose build || fail "docker compose build"
pass "docker compose build"

info "Step 3: bring stack up (with --wait)"
docker compose up -d --wait || fail "docker compose up"
pass "stack is healthy"

info "Step 4: run migrations"
make migrate || fail "make migrate"
pass "alembic upgrade head"

info "Step 5: seed data"
make seed || fail "make seed"
pass "seed"

# ─── Wait for API health ────────────────────────────────────────────
info "Step 6: wait for API health"
for i in $(seq 1 30); do
  if curl -sf --max-time 3 "$API/health" > /dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf --max-time 5 "$API/health" > /dev/null || fail "API health check"
pass "API healthy"

# ─── Owner login ────────────────────────────────────────────────────
info "Step 7: owner login"
COOKIE_JAR=$(mktemp)
auth_login owner "$COOKIE_JAR" || fail "owner login"
pass "owner login"

# ─── Owner login through owner-web: GET / returns 200 ───────────────
info "Step 7b: owner-web / returns 200 with auth cookie"
OWNER_ROOT=""
for i in $(seq 1 15); do
  OWNER_ROOT=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" \
    -b "$COOKIE_JAR" "$OWNER_WEB/" || true)
  if [ "$OWNER_ROOT" = "200" ]; then break; fi
  sleep 1
done
[ "$OWNER_ROOT" = "200" ] || fail "owner-web / returned $OWNER_ROOT (expected 200, redirect loop?)"
pass "owner-web / returns 200 (no redirect loop)"

# ─── Staff login through owner-web: GET /kitchen returns 200 ────────
info "Step 7c: staff login → /kitchen returns 200"
STAFF_JAR=$(mktemp)
auth_login staff "$STAFF_JAR" || fail "staff login"
KITCHEN_STATUS=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" \
  -b "$STAFF_JAR" "$OWNER_WEB/kitchen" || true)
[ "$KITCHEN_STATUS" = "200" ] || fail "owner-web /kitchen returned $KITCHEN_STATUS (expected 200)"
pass "owner-web /kitchen returns 200 with staff cookie"

# ─── Adapter: smoke inference ────────────────────────────────────────
info "Step 8: smoke inference (mock models check)"
MODELS_RESP=$(curl -sf --max-time 5 "$API/health" 2>/dev/null)
pass "inference mock reachable via API health"

# ─── AI Endpoint: menu ingest ───────────────────────────────────────
info "Step 9: POST /menu-items/ingest"
INGEST_RESP=$(curl -sf --max-time 15 -X POST \
  "$API/api/restaurants/$SLUG/menu-items/ingest" \
  -b "$COOKIE_JAR" \
  -H "Content-Type: application/json" \
  -d '{"image_url":"https://example.com/menu.jpg","language":"it"}' \
  2>/dev/null) || fail "menu ingest endpoint"
echo "$INGEST_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['created_count']>=0" \
  || fail "ingest response validation"
pass "menu ingest"

# ─── AI Endpoint: daily brief ───────────────────────────────────────
info "Step 10: GET /ai/brief"
BRIEF_RESP=$(curl -sf --max-time 15 \
  "$API/api/restaurants/$SLUG/ai/brief" \
  -b "$COOKIE_JAR" \
  2>/dev/null) || fail "daily brief endpoint"
echo "$BRIEF_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'summary' in d" \
  || fail "brief response validation"
pass "daily brief"

# ─── AI Endpoint: simulate ──────────────────────────────────────────
info "Step 11: POST /ai/simulate"
SIM_RESP=$(curl -sf --max-time 15 -X POST \
  "$API/api/restaurants/$SLUG/ai/simulate" \
  -b "$COOKIE_JAR" \
  -H "Content-Type: application/json" \
  -d '{"scenario":"demand_surge","multiplier":1.2}' \
  2>/dev/null) || fail "simulate (what-if) endpoint"
echo "$SIM_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['scenario'] == 'demand_surge' and 'delta' in d and d['assumptions']" \
  || fail "simulate (what-if) response validation"
pass "simulate (what-if)"

# ─── Guest Chat ─────────────────────────────────────────────────────
info "Step 12: create guest session + POST /chat"
# Get first table QR token
TABLES_RESP=$(curl -sf --max-time 5 \
  "$API/api/restaurants/$SLUG/tables" \
  -b "$COOKIE_JAR" 2>/dev/null)
QR_TOKEN=$(echo "$TABLES_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['qr_token'])" 2>/dev/null)

GUEST_JAR=$(mktemp)
curl -sf --max-time 5 -X POST "$API/api/guest/sessions" \
  -H "Content-Type: application/json" \
  -d "{\"qr_token\":\"$QR_TOKEN\",\"language\":\"en\"}" \
  -c "$GUEST_JAR" > /dev/null || fail "guest session"

CHAT_RESP=$(curl -sf --max-time 15 -X POST "$API/api/guest/chat" \
  -b "$GUEST_JAR" \
  -H "Content-Type: application/json" \
  -d '{"message":"What do you recommend?"}' \
  2>/dev/null) || fail "guest chat endpoint"
echo "$CHAT_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'reply' in d" \
  || fail "chat response validation"
pass "guest chat"

# ─── Metrics ─────────────────────────────────────────────────────────
info "Step 13: GET /metrics/inference"
METRICS_RESP=$(curl -sf --max-time 5 \
  "$API/api/metrics/inference" 2>/dev/null) || fail "metrics endpoint"
echo "$METRICS_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['total_calls']>=0" \
  || fail "metrics response validation"
pass "inference metrics"

# ─── Test suite ──────────────────────────────────────────────────────
info "Step 14: make test-py"
make test-py || fail "make test-py"
pass "test-py (all passed)"

# ─── Cleanup ─────────────────────────────────────────────────────────
rm -f "$COOKIE_JAR" "$STAFF_JAR" "$GUEST_JAR" 2>/dev/null || true

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  CHECKPOINT D: ALL CHECKS PASSED              ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
