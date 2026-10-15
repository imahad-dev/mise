#!/usr/bin/env bash
set -eo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
OWNER_API_KEY="${OWNER_API_KEY:-change_me_in_production}"
STAFF_PIN="${STAFF_PIN:-0000}"

OWNER_JAR=$(mktemp /tmp/owner_jar_XXXXXX 2>/dev/null || mktemp)
STAFF_JAR=$(mktemp /tmp/staff_jar_XXXXXX 2>/dev/null || mktemp)
GUEST_JAR=$(mktemp /tmp/guest_jar_XXXXXX 2>/dev/null || mktemp)

trap 'rm -f "$OWNER_JAR" "$STAFF_JAR" "$GUEST_JAR"' EXIT

echo "=== E2E Smoke Test starting against $API_BASE_URL ==="

HEALTHY=0
for i in $(seq 1 30); do
    if curl -s -f "$API_BASE_URL/health" > /dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 1
done

if [ "$HEALTHY" -ne 1 ]; then
    echo "ERROR: API failed to become healthy at $API_BASE_URL within 30 seconds" >&2
    exit 1
fi

# 1. Owner Login
echo "-> 1. Owner Login"
curl -s -f -c "$OWNER_JAR" \
    -H "Content-Type: application/json" \
    -d "{\"role\":\"owner\",\"secret\":\"$OWNER_API_KEY\"}" \
    "$API_BASE_URL/api/auth/login" > /dev/null

# 2. Staff Login
echo "-> 2. Staff Login"
curl -s -f -c "$STAFF_JAR" \
    -H "Content-Type: application/json" \
    -d "{\"role\":\"staff\",\"secret\":\"$STAFF_PIN\"}" \
    "$API_BASE_URL/api/auth/login" > /dev/null

# 3. Owner lists tables to get valid QR token
echo "-> 3. Fetching Dining Tables"
TABLES_JSON=$(curl -s -f -b "$OWNER_JAR" "$API_BASE_URL/api/restaurants/trattoria-da-mario/tables")
QR_TOKEN=$(python3 -c "import sys, json; print(json.load(sys.stdin)[0]['qr_token'])" <<< "$TABLES_JSON")

# 4. Guest creates session
echo "-> 4. Creating Guest Session with token: $QR_TOKEN"
SESS_JSON=$(curl -s -f -c "$GUEST_JAR" \
    -H "Content-Type: application/json" \
    -d "{\"qr_token\":\"$QR_TOKEN\",\"language\":\"it\"}" \
    "$API_BASE_URL/api/guest/sessions")

# 5. Guest fetches menu (verify NO unit_cost)
echo "-> 5. Fetching Guest Menu"
MENU_JSON=$(curl -s -f -b "$GUEST_JAR" "$API_BASE_URL/api/guest/menu")
python3 -c "import sys, json; data=json.load(sys.stdin); assert 'unit_cost' not in str(data), 'unit_cost leaked!'" <<< "$MENU_JSON"
ITEM_ID=$(python3 -c "import sys, json; print(json.load(sys.stdin)['items'][0]['id'])" <<< "$MENU_JSON")

# 6. Guest places order
echo "-> 6. Placing Order for Item: $ITEM_ID"
IDEM_KEY="e2e-order-$(date +%s)-$RANDOM"
ORDER_JSON=$(curl -s -f -b "$GUEST_JAR" \
    -H "Content-Type: application/json" \
    -d "{\"idempotency_key\":\"$IDEM_KEY\",\"items\":[{\"menu_item_id\":\"$ITEM_ID\",\"quantity\":1}],\"acknowledge_allergen_risk\":true}" \
    "$API_BASE_URL/api/orders")
ORDER_ID=$(python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" <<< "$ORDER_JSON")
echo "   Order placed: $ORDER_ID"

# 7. Kitchen lists orders
echo "-> 7. Kitchen List Orders"
KITCHEN_JSON=$(curl -s -f -b "$STAFF_JAR" "$API_BASE_URL/api/restaurants/trattoria-da-mario/kitchen/orders")
python3 -c "import sys, json; orders=json.load(sys.stdin)['orders']; assert any(o['id'] == '$ORDER_ID' for o in orders), 'Order not in kitchen!'" <<< "$KITCHEN_JSON"

# 8. Kitchen bumps order
echo "-> 8. Kitchen Bumps Order"
BUMP_JSON=$(curl -s -f -b "$STAFF_JAR" -X POST "$API_BASE_URL/api/restaurants/trattoria-da-mario/kitchen/orders/$ORDER_ID/bump")
python3 -c "import sys, json; assert json.load(sys.stdin)['status'] == 'bumped'" <<< "$BUMP_JSON"

# 9. Kitchen recalls order (within 60s)
echo "-> 9. Kitchen Recalls Order"
RECALL_JSON=$(curl -s -f -b "$STAFF_JAR" -X POST "$API_BASE_URL/api/restaurants/trattoria-da-mario/kitchen/orders/$ORDER_ID/recall")
python3 -c "import sys, json; assert json.load(sys.stdin)['status'] == 'placed'" <<< "$RECALL_JSON"

# 10. Owner PATCH menu item
echo "-> 10. Owner PATCH Menu Item"
curl -s -f -b "$OWNER_JAR" -X PATCH \
    -H "Content-Type: application/json" \
    -d '{"available":true}' \
    "$API_BASE_URL/api/restaurants/trattoria-da-mario/menu-items/$ITEM_ID" > /dev/null

# 11. SSE Stream Check
echo "-> 11. Checking Order SSE Stream"
STREAM_OUT=$(curl -s -m 2 -b "$GUEST_JAR" "$API_BASE_URL/api/orders/$ORDER_ID/stream" || true)
if echo "$STREAM_OUT" | grep -q "connected"; then
    echo "   SSE stream connected successfully."
else
    echo "ERROR: SSE stream check failed; expected 'connected', got: $STREAM_OUT" >&2
    exit 1
fi

echo "=== E2E Smoke Test PASSED ==="
