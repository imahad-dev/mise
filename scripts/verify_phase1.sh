#!/usr/bin/env bash
#
# Phase 1 end-to-end verification against a fresh Docker stack (mock LLM only).
#
#   LLM_PROVIDER=mock DEMO_MODE=true bash scripts/verify_phase1.sh     (or: make verify-f)
#
# Wipes the dev database volumes (make reset). Prints one PASS/FAIL line per step and the
# tail of the failing step's log, then stops at the first failure.
#
set -uo pipefail

# Never talk to a real provider, whatever .env says. LLM_PROVIDER=mock also forces the mock
# base URLs in the API itself.
export LLM_PROVIDER=mock DEMO_MODE=true
export LLM_BASE_URL=http://inference:8080/v1 VLM_BASE_URL=http://inference:8080/v1 LLM_API_KEY=

API="http://127.0.0.1:8000"
SLUG="trattoria-da-mario"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
OWNER_JAR="$TMP/owner.jar"
GUEST_JAR="$TMP/guest.jar"

run_step() {
  local name="$1"
  shift
  if "$@" >"$TMP/step.log" 2>&1; then
    echo "PASS $name"
  else
    echo "FAIL $name"
    tail -n 30 "$TMP/step.log" | sed 's/^/    /'
    exit 1
  fi
}

sql() { # sql "<query>" -> single value / rows, tab-separated
  docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$0"' "$1"
}

clear_demo_limits() { # per-IP demo limits would block repeated runs from one machine
  docker compose exec -T redis sh -c \
    "redis-cli --scan --pattern 'rate_limit:demo*' | xargs -r redis-cli DEL" >/dev/null
}

counts() { sql "SELECT (SELECT count(*) FROM orders) || ' ' || (SELECT count(*) FROM order_item)"; }

json_check() { # json_check <file> <python expression over d> <message>
  python3 - "$1" "$2" "$3" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
if not eval("(" + sys.argv[2] + ")", {"d": d}):
    print("assertion failed:", sys.argv[3]); print(json.dumps(d)[:2000]); sys.exit(1)
EOF
}

grounded() { # grounded <file> <text field>: every number in the text appears in the response
  docker compose exec -T api python -c "
import json, sys
from src.services.narrative import numbers_grounded
d = json.load(sys.stdin)
text = d['$2']
print('text:', text)
sys.exit(0 if numbers_grounded(text, {k: v for k, v in d.items() if k != '$2'}) else 1)
" <"$1"
}

# --- Steps ---------------------------------------------------------------

step_stack() {
  make reset && make up || return 1
  for _ in $(seq 1 90); do
    curl -sf --max-time 3 "$API/health" >/dev/null && return 0
    sleep 2
  done
  echo "API never became healthy"; docker compose ps; return 1
}

step_migrations() {
  local tables
  tables=$(sql "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
  [ "$tables" = "0" ] || { echo "database not empty: $tables tables"; return 1; }
  docker compose exec -T api alembic upgrade head &&
    docker compose exec -T api alembic downgrade -1 &&
    docker compose exec -T api alembic upgrade head &&
    docker compose exec -T api alembic check
}

step_seed_twice() {
  local q="SELECT (SELECT count(*) FROM restaurant) || ' ' || (SELECT count(*) FROM dining_table)
    || ' ' || (SELECT count(*) FROM menu_item) || ' ' || (SELECT count(*) FROM menu_translation)"
  make seed || return 1
  local first; first=$(sql "$q")
  make seed || return 1
  local second; second=$(sql "$q")
  echo "after seed 1: $first / after seed 2: $second"
  [ "$first" = "$second" ] && [ "${first%% *}" = "1" ]
}

simulate() { # simulate <outfile>
  curl -sf --max-time 120 -b "$OWNER_JAR" -H "Content-Type: application/json" \
    -X POST "$API/api/restaurants/$SLUG/demo/simulate-orders" -d '{"days": 56}' -o "$1"
}

step_simulate() {
  curl -sf -c "$OWNER_JAR" -H "Content-Type: application/json" \
    -X POST "$API/api/auth/demo-login" -d '{"role": "owner"}' >/dev/null || return 1
  clear_demo_limits
  simulate "$TMP/sim1.json" || return 1
  local one; one=$(counts)
  clear_demo_limits
  simulate "$TMP/sim2.json" || return 1
  local two; two=$(counts)
  clear_demo_limits
  simulate "$TMP/sim3.json" & local p1=$!
  simulate "$TMP/sim4.json" & local p2=$!
  wait "$p1" || return 1
  wait "$p2" || return 1
  local par; par=$(counts)
  local live; live=$(sql "SELECT count(*) FROM orders WHERE source <> 'simulated'")
  echo "orders/items: run1=$one run2=$two parallel=$par non-simulated=$live"
  [ "$one" = "$two" ] && [ "$one" = "$par" ] && [ "$live" = "0" ] && [ "${one%% *}" -gt 500 ]
}

step_brief_whatif() {
  curl -sf --max-time 60 -b "$OWNER_JAR" "$API/api/restaurants/$SLUG/ai/brief" \
    -o "$TMP/brief.json" || return 1
  json_check "$TMP/brief.json" \
    "d['kpis']['orders'] > 0 and d['data_sources']['simulated'] > 0 and d['menu_engineering']
     and 3 <= len(d['actions']) <= 5 and d['summary_source'] in ('llm', 'template')
     and not d['forecast']['low_confidence'] and d['forecast']['history_days'] == 56
     and {b['method'] for b in d['forecast']['backtest']} >= {'seasonal_naive', 'trailing_4w_mean'}
     and len({p['date'] for p in d['forecast']['points']}) == 7" "brief structure" || return 1
  grounded "$TMP/brief.json" summary || return 1
  local stored
  stored=$(sql "SELECT count(*) FROM forecast_run
    WHERE metrics->'backtest'->'methods' ? 'seasonal_naive'
      AND (metrics->'backtest'->'methods'->'seasonal_naive'->>'wape') IS NOT NULL")
  [ "$stored" -ge 1 ] || { echo "no stored forecast_run with backtest metrics"; return 1; }

  curl -sf -b "$OWNER_JAR" -H "Content-Type: application/json" \
    -X POST "$API/api/restaurants/$SLUG/ai/simulate" \
    -d '{"scenario": "demand_surge", "multiplier": 1.2}' -o "$TMP/surge.json" || return 1
  json_check "$TMP/surge.json" \
    "abs(d['delta']['revenue_eur'] - 0.2 * d['baseline']['revenue_eur']) < 0.02
     and abs(d['delta']['margin_eur'] - 0.2 * d['baseline']['margin_eur']) < 0.02
     and d['assumptions']" "demand surge arithmetic" || return 1
  grounded "$TMP/surge.json" explanation || return 1

  local item
  item=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['menu_engineering'][0]['item_id'])" "$TMP/brief.json")
  curl -sf -b "$OWNER_JAR" -H "Content-Type: application/json" \
    -X POST "$API/api/restaurants/$SLUG/ai/simulate" \
    -d "{\"scenario\": \"price_change\", \"item_id\": \"$item\", \"change_pct\": 5}" \
    -o "$TMP/price.json" || return 1
  json_check "$TMP/price.json" "d['item'] and d['result'] and d['assumptions']" "price change" ||
    return 1
  grounded "$TMP/price.json" explanation
}

step_live_order_survives() {
  local token
  token=$(curl -sf -b "$OWNER_JAR" "$API/api/restaurants/$SLUG/tables" |
    python3 -c "import json,sys; print(json.load(sys.stdin)[0]['qr_token'])") || return 1
  curl -sf -c "$GUEST_JAR" -H "Content-Type: application/json" -X POST "$API/api/guest/sessions" \
    -d "{\"qr_token\": \"$token\", \"language\": \"en\"}" >/dev/null || return 1
  local item
  item=$(curl -sf -b "$GUEST_JAR" "$API/api/guest/menu" |
    python3 -c "import json,sys; print(json.load(sys.stdin)['items'][0]['id'])") || return 1
  curl -sf -b "$GUEST_JAR" -H "Content-Type: application/json" -X POST "$API/api/orders" \
    -d "{\"idempotency_key\": \"verify-$(date +%s)\", \"acknowledge_allergen_risk\": true,
         \"items\": [{\"menu_item_id\": \"$item\", \"quantity\": 2}]}" -o "$TMP/order.json" ||
    return 1
  local order_id
  order_id=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['id'])" "$TMP/order.json")
  local before; before=$(sql "SELECT count(*) FROM orders WHERE source = 'simulated'")

  clear_demo_limits
  simulate "$TMP/sim5.json" || return 1

  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" -b "$GUEST_JAR" "$API/api/orders/$order_id")
  local live
  live=$(sql "SELECT count(*) || ' ' || (SELECT count(*) FROM order_item WHERE order_id = '$order_id')
    || ' ' || (SELECT count(*) FROM guest_session gs JOIN orders o ON o.guest_session_id = gs.id
               WHERE o.id = '$order_id')
    FROM orders WHERE id = '$order_id' AND source = 'live'")
  local after; after=$(sql "SELECT count(*) FROM orders WHERE source = 'simulated'")
  echo "live order $order_id: GET=$status live/items/session=$live simulated before=$before after=$after"
  [ "$status" = "200" ] && [ "$live" = "1 1 1" ] && [ "$before" = "$after" ]
}

step_edge_proxy() { # Caddy (edge profile) must replace a client-sent X-Forwarded-For
  docker compose --profile edge up -d --wait caddy || return 1
  docker compose exec -T redis sh -c     "redis-cli --scan --pattern 'rate_limit:demo_login:*' | xargs -r redis-cli DEL" >/dev/null
  curl -sf --max-time 10 -H "X-Forwarded-For: 203.0.113.77" -H "Content-Type: application/json"     -X POST "http://127.0.0.1:8081/api/auth/demo-login" -d '{"role": "owner"}' >/dev/null ||
    return 1
  local keys
  keys=$(docker compose exec -T redis redis-cli --scan --pattern 'rate_limit:demo_login:*')
  echo "demo_login buckets after spoofed request via Caddy: $keys"
  [ -n "$keys" ] && ! grep -q "203.0.113.77" <<<"$keys"
}

step_ci() { make ci; }

run_step "stack: make reset, make up, API healthy" step_stack
run_step "migrations: upgrade head, downgrade -1, upgrade head, alembic check" step_migrations
run_step "seed twice: identical counts" step_seed_twice
run_step "simulate-orders: sequential and parallel runs give identical counts" step_simulate
run_step "brief and what-if: structure, grounded numbers, stored backtest" step_brief_whatif
run_step "live order survives demo data regeneration" step_live_order_survives
run_step "edge proxy (Caddy) ignores spoofed X-Forwarded-For" step_edge_proxy
run_step "make ci" step_ci
echo "PASS verify-f: all steps"
