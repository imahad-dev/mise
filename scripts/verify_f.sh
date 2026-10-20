#!/usr/bin/env bash
#
# Phase 1 verification: real revenue copilot (analytics, forecast, what-if, simulated data)
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

info "Step 1: make ci (lint, all Python + TS tests, branding)"
make ci || fail "make ci failed"
pass "make ci"

info "Step 2: Phase 1 tests (inference dependency, analytics, forecast, what-if, simulator)"
docker compose build api-test || fail "docker compose build api-test"
docker compose run --rm api-test pytest -v \
  tests/test_inference_dependency.py \
  tests/test_analytics_pure.py \
  tests/test_analytics_api.py || fail "Phase 1 tests failed"
pass "Phase 1 tests"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PHASE 1 (F): ALL CHECKS PASSED               ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
