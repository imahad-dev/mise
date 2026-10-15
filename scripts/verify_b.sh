#!/usr/bin/env bash
set -eo pipefail

LOG_DIR=$(mktemp -d /tmp/verify_b_XXXXXX 2>/dev/null || mktemp -d)
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

# Step 1: make up
if make up > "$LOG_DIR/up.log" 2>&1; then
    echo "PASS: make up"
else
    fail_step "make up" "$LOG_DIR/up.log"
fi

# Wait for services to become ready before migration
for i in $(seq 1 30); do
    if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Step 2: make migrate
if make migrate > "$LOG_DIR/migrate.log" 2>&1; then
    echo "PASS: make migrate"
else
    fail_step "make migrate" "$LOG_DIR/migrate.log"
fi

# Step 3: alembic check
if docker compose exec -T api alembic check > "$LOG_DIR/alembic_check.log" 2>&1; then
    echo "PASS: alembic check"
else
    fail_step "alembic check" "$LOG_DIR/alembic_check.log"
fi

# Step 4: make seed
if make seed > "$LOG_DIR/seed.log" 2>&1; then
    echo "PASS: make seed"
else
    fail_step "make seed" "$LOG_DIR/seed.log"
fi

# Step 5: make test-py
TEST_LOG="$LOG_DIR/test_py.log"
if make test-py > "$TEST_LOG" 2>&1; then
    echo "PASS: make test-py"
    SUMMARY_LINE=$(grep -E '^=+ .* in .* =+$' "$TEST_LOG" | tail -n 1 || true)
    if [ -z "$SUMMARY_LINE" ]; then
        SUMMARY_LINE=$(grep -E 'passed in' "$TEST_LOG" | tail -n 1 || true)
    fi
    if [ -n "$SUMMARY_LINE" ]; then
        echo "$SUMMARY_LINE"
    fi
else
    echo "FAIL: make test-py"
    SUMMARY_LINE=$(grep -E '^=+ .* in .* =+$' "$TEST_LOG" | tail -n 1 || true)
    if [ -n "$SUMMARY_LINE" ]; then
        echo "$SUMMARY_LINE"
    fi
    if [ -f "$TEST_LOG" ]; then
        echo "--- Last 40 lines of $TEST_LOG ---" >&2
        tail -n 40 "$TEST_LOG" >&2
    fi
    exit 1
fi

# Step 6: bash scripts/e2e_smoke.sh
if bash scripts/e2e_smoke.sh > "$LOG_DIR/e2e_smoke.log" 2>&1; then
    echo "PASS: bash scripts/e2e_smoke.sh"
else
    fail_step "bash scripts/e2e_smoke.sh" "$LOG_DIR/e2e_smoke.log"
fi
