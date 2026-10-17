#!/usr/bin/env bash
set -eo pipefail

LOG_DIR=$(mktemp -d /tmp/verify_c_XXXXXX 2>/dev/null || mktemp -d)
trap 'rm -rf "$LOG_DIR"' EXIT

fail_step() {
    local step_name="$1"
    local log_file="$2"
    echo "FAIL: $step_name"
    if [ -f "$log_file" ]; then
        echo "--- Last 40 lines of $log_file ---" >&2
        tail -n 40 "$log_file" >&2
    fi
    exit 1
}

# Step 1: make ci
CI_LOG="$LOG_DIR/ci.log"
if make ci > "$CI_LOG" 2>&1; then
    echo "PASS: make ci"
else
    fail_step "make ci" "$CI_LOG"
fi

# Step 2: docker compose build of both web apps
BUILD_LOG="$LOG_DIR/build_web.log"
if docker compose build guest-web owner-web > "$BUILD_LOG" 2>&1; then
    echo "PASS: docker compose build guest-web owner-web"
else
    fail_step "docker compose build guest-web owner-web" "$BUILD_LOG"
fi

# Step 3: ensure services are up
UP_LOG="$LOG_DIR/up.log"
if docker compose up -d --wait guest-web owner-web api postgres redis > "$UP_LOG" 2>&1; then
    echo "PASS: docker compose up running stack"
else
    fail_step "docker compose up running stack" "$UP_LOG"
fi

# Step 4: Ensure schema is migrated and seeded
MIGRATE_LOG="$LOG_DIR/migrate.log"
if docker compose exec -T api alembic upgrade head > "$MIGRATE_LOG" 2>&1; then
    echo "PASS: make migrate"
else
    fail_step "make migrate" "$MIGRATE_LOG"
fi

SEED_LOG="$LOG_DIR/seed.log"
if docker compose exec -T api python scripts/seed.py > "$SEED_LOG" 2>&1; then
    echo "PASS: make seed"
else
    fail_step "make seed" "$SEED_LOG"
fi

# Retrieve valid table QR token using container's effective environment
QR_TOKEN=$(docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -c "SELECT qr_token FROM dining_table LIMIT 1;"' | tr -d '\r\n')

if [ -z "$QR_TOKEN" ]; then
    echo "FAIL: could not retrieve table QR token from database" >&2
    exit 1
fi

# Step 5: curl /q/<token> on guest-web returns 200 (with bounded retries and max-time)
GUEST_URL="http://127.0.0.1:3000/q/${QR_TOKEN}"
GUEST_STATUS=""
for i in $(seq 1 15); do
    GUEST_STATUS=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$GUEST_URL" || true)
    if [ "$GUEST_STATUS" = "200" ]; then
        break
    fi
    sleep 1
done

if [ "$GUEST_STATUS" = "200" ]; then
    echo "PASS: guest-web /q/$QR_TOKEN returns 200"
else
    echo "FAIL: guest-web /q/$QR_TOKEN returned HTTP $GUEST_STATUS (expected 200)" >&2
    exit 1
fi

# Step 6: curl /login on owner-web returns 200 (with bounded retries and max-time)
OWNER_URL="http://127.0.0.1:3001/login"
OWNER_STATUS=""
for i in $(seq 1 15); do
    OWNER_STATUS=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$OWNER_URL" || true)
    if [ "$OWNER_STATUS" = "200" ]; then
        break
    fi
    sleep 1
done

if [ "$OWNER_STATUS" = "200" ]; then
    echo "PASS: owner-web /login returns 200"
else
    echo "FAIL: owner-web /login returned HTTP $OWNER_STATUS (expected 200)" >&2
    exit 1
fi

echo "=== CHECKPOINT C VERIFIED ==="
