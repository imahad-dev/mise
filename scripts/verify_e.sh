#!/usr/bin/env bash
#
# Checkpoint E verification — Brand Theme + Demo Access
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

API="http://127.0.0.1:8000"
GUEST_WEB="http://127.0.0.1:3000"
OWNER_WEB="http://127.0.0.1:3001"

# Step 1: make ci
info "Step 1: make ci"
make ci || fail "make ci failed"
pass "make ci"

# Step 2: docker compose build of both web apps
info "Step 2: docker compose build guest-web owner-web"
docker compose build guest-web owner-web || fail "docker compose build guest-web owner-web"
pass "docker compose build guest-web owner-web"

# Step 3: ensure services are up
info "Step 3: bring stack up (with --wait)"
docker compose up -d --wait || fail "docker compose up"
pass "stack is healthy"

# Wait for API health
info "Step 4: wait for API health"
for i in $(seq 1 30); do
  if curl -sf --max-time 3 "$API/health" > /dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -sf --max-time 5 "$API/health" > /dev/null || fail "API health check"
pass "API healthy"

# Step 5: curl / (guest-web demo launcher)
info "Step 5: curl / (guest-web demo launcher)"
GUEST_STATUS=""
for i in $(seq 1 30); do
  GUEST_STATUS=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$GUEST_WEB/" || true)
  if [ "$GUEST_STATUS" = "200" ]; then break; fi
  sleep 1
done
[ "$GUEST_STATUS" = "200" ] || fail "guest-web / returned $GUEST_STATUS (expected 200)"
pass "guest-web / returns 200"

# Step 6: curl /login (owner-web login page)
info "Step 6: curl /login (owner-web login page)"
LOGIN_STATUS=""
for i in $(seq 1 30); do
  LOGIN_STATUS=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$OWNER_WEB/login" || true)
  if [ "$LOGIN_STATUS" = "200" ]; then break; fi
  sleep 1
done
[ "$LOGIN_STATUS" = "200" ] || fail "owner-web /login returned $LOGIN_STATUS (expected 200)"
pass "owner-web /login returns 200"

# Step 7: curl /api/auth/config
info "Step 7: curl /api/auth/config"
CONFIG_RESP=$(curl -sf --max-time 5 "$API/api/auth/config" 2>/dev/null) || fail "GET /api/auth/config failed"
echo "$CONFIG_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'demo_mode' in d" \
  || fail "/api/auth/config validation failed"
pass "/api/auth/config returned valid json"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  CHECKPOINT E: ALL CHECKS PASSED              ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
