#!/usr/bin/env bash
set -eo pipefail

LOG_DIR=$(mktemp -d /tmp/verify_a_XXXXXX 2>/dev/null || mktemp -d)
trap 'rm -rf "$LOG_DIR"' EXIT

print_logs() {
    for f in "$@"; do
        if [ -f "$f" ]; then
            cat "$f" >&2
        fi
    done
}

# Step 0: make up
if make up > "$LOG_DIR/up.log" 2>&1; then
    echo "PASS: make up"
else
    echo "FAIL: make up"
    print_logs "$LOG_DIR/up.log"
    exit 1
fi

# Wait for services to become ready before migration
for i in $(seq 1 30); do
    if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Step 1: make migrate
if make migrate > "$LOG_DIR/migrate.log" 2>&1; then
    echo "PASS: make migrate"
    # Print current alembic version
    docker compose exec -T api alembic current 2>/dev/null || true
else
    echo "FAIL: make migrate"
    print_logs "$LOG_DIR/migrate.log"
    exit 1
fi

# Step 2: alembic check
if docker compose exec -T api alembic check > "$LOG_DIR/alembic_check.log" 2>&1; then
    echo "PASS: alembic check"
else
    echo "FAIL: alembic check"
    print_logs "$LOG_DIR/alembic_check.log"
    exit 1
fi

# Step 3: make seed twice
if make seed > "$LOG_DIR/seed1.log" 2>&1 && make seed > "$LOG_DIR/seed2.log" 2>&1; then
    echo "PASS: make seed twice"
else
    echo "FAIL: make seed twice"
    print_logs "$LOG_DIR/seed1.log" "$LOG_DIR/seed2.log"
    exit 1
fi

# Step 4: the row-count query
ROW_COUNT_SQL="SELECT 'restaurant' as tbl, count(*) FROM restaurant UNION ALL SELECT 'dining_table', count(*) FROM dining_table UNION ALL SELECT 'menu_item', count(*) FROM menu_item UNION ALL SELECT 'menu_translation', count(*) FROM menu_translation UNION ALL SELECT 'unverified_item', count(*) FROM menu_item WHERE allergen_verified IS FALSE;"
if ROW_OUTPUT=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-mise}" -d "${POSTGRES_DB:-mise}" -t -A -c "$ROW_COUNT_SQL" 2>"$LOG_DIR/row_count.log") && \
   echo "$ROW_OUTPUT" | grep -Fxq "restaurant|1" && \
   echo "$ROW_OUTPUT" | grep -Fxq "dining_table|6" && \
   echo "$ROW_OUTPUT" | grep -Fxq "menu_item|25" && \
   echo "$ROW_OUTPUT" | grep -Fxq "menu_translation|50" && \
   echo "$ROW_OUTPUT" | grep -Fxq "unverified_item|1"; then
    echo "PASS: row-count query"
else
    echo "FAIL: row-count query"
    print_logs "$LOG_DIR/row_count.log"
    echo "Actual output:" >&2
    echo "$ROW_OUTPUT" >&2
    exit 1
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
    print_logs "$TEST_LOG"
    exit 1
fi
