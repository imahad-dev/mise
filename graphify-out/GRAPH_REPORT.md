# Graph Report - Mise  (2026-10-20)

## Corpus Check
- 162 files · ~86,408 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 23 file(s) not represented in the graph (top: (none) 14, .ico 2, .css 2)

## Summary
- 1199 nodes · 2431 edges · 83 communities (57 shown, 26 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 227 edges (avg confidence: 0.92)
- Token cost: 173,418 input · 0 output

## Community Hubs (Navigation)
- Order Path Tests
- Owner Menu & Ingest API
- Auth & Signed Cookies
- Schema Constraint Tests
- Guest Web Dependencies
- Owner Web Dependencies
- API Client Package
- Kitchen Orders API
- Guest Session API
- Order Creation & Idempotency
- Database Models
- Next.js Layouts & Middleware
- Test DB Fixtures
- Inference Client Tests
- Seed & Inference Smoke
- FastAPI App & Metrics
- Guest Menu & Cart
- Alembic Migrations
- Guest Chat & Rate Limits
- Guest SSE Manager
- Guest Web TS Config
- Owner Web TS Config
- Health & Debug SSE
- Inference Payload Tests
- Allergen Chip UI
- Mock Inference Server
- Kitchen Display Frontend
- Settings & Secret Guards
- Demo Mode Tests
- Allergen Engine
- LLM Smoke Script
- Inference Client Core
- ESLint Config
- Guest Order & Chat UI
- AI Privacy Tests
- Response Validation
- Inference Client Startup
- i18n Dictionaries
- Compose Stack & Seed
- Backend Architecture Docs
- API Client TS Config
- Health Tests
- Brand Assets
- Home & Tables Pages
- Root Workspace Package
- Daily Cap Tests
- PWA Manifest
- Product Feature Docs
- Inference Dependency
- Order Data Model Docs
- Provider Presets
- Health & Metrics Schemas
- CI & Workspace Config
- Allergen Safety Docs
- Alembic Env
- Config Isolation Tests
- Metrics Tests
- Generated OpenAPI Schema
- PostCSS Config
- AI Simulator Page
- Daily Brief Page
- Allergen Test Vectors
- Proxy & Auth ADRs
- Owner Copilot Features
- verify_d Script
- verify_e Script
- verify_a Script
- verify_b Script
- verify_c Script
- Scaffold Icon: file
- Scaffold Icon: globe
- Scaffold Icon: next
- Scaffold Icon: vercel
- Scaffold Icon: window
- Branding Check Script
- E2E Smoke Script
- Client Generation Script
- mise-api Package
- Inference Mock Package
- Roadmap

## God Nodes (most connected - your core abstractions)
1. `InferenceClient` - 35 edges
2. `Restaurant` - 32 edges
3. `MenuItem` - 29 edges
4. `GuestSession` - 26 edges
5. `assert_violates()` - 23 edges
6. `_create_test_restaurant()` - 21 edges
7. `DiningTable` - 20 edges
8. `Base` - 19 edges
9. `seed_data()` - 18 edges
10. `sign_value()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `Running Mise (stub)` --conceptually_related_to--> `Mise Restaurant Revenue Copilot Platform`  [AMBIGUOUS]
  docs/running.md → README.md
- `owner-web Next.js create-next-app README` --conceptually_related_to--> `Owner Revenue Copilot`  [INFERRED]
  apps/owner-web/README.md → README.md
- `Daily Request Safeguards (LLM_DAILY_REQUEST_CAP, 503 ai_unavailable)` --semantically_similar_to--> `Free-Only Policy & Redis Daily Cap Rate Limits`  [INFERRED] [semantically similar]
  README.md → docs/architecture.md
- `GitHub Actions CI test job` --semantically_similar_to--> `api-test compose service (test profile)`  [INFERRED] [semantically similar]
  .github/workflows/ci.yml → docker-compose.yml
- `seed_data()` --uses--> `DiningTable`  [INFERRED]
  scripts/seed.py → services/api/src/models/dining_table.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Order placement safety: allergen precedence + idempotency + immutable snapshots** — docs_architecture_deterministic_allergen_engine, docs_architecture_order_idempotency, docs_architecture_table_orders, docs_architecture_table_order_item, docs_decisions_adr_005_allergen_precedence, docs_decisions_adr_004_server_payload_hash [INFERRED 0.85]
- **SSE delivery path through same-origin proxy with Caddy fallback** — docs_architecture_sse_streaming, docs_architecture_redis, docs_decisions_adr_001_same_origin_proxy, docs_decisions_adr_003_caddy_fallback, docs_architecture_debug_sse_endpoint, readme_kitchen_display_system [INFERRED 0.85]
- **LLM usage governance: free-only, daily cap, privacy, presets** — readme_free_only_policy, readme_daily_request_safeguards, readme_air_gapped_privacy_design, readme_llm_provider_presets, readme_generic_llm_client, docs_architecture_free_only_rate_limits [INFERRED 0.85]
- **Mise Brand Asset Set (guest-web)** — apps_guest_web_public_brand_cover_cover_image, apps_guest_web_public_brand_og_cover_og_cover_image, apps_guest_web_public_brand_logo_mark_logo_mark, apps_guest_web_src_app_icon_app_favicon, apps_guest_web_public_brand_cover_mise_restaurant_revenue_copilot [INFERRED 0.85]
- **Next.js Scaffold Default Icons** — apps_guest_web_public_file_file_icon, apps_guest_web_public_globe_globe_icon, apps_guest_web_public_next_next_js_logo, apps_guest_web_public_vercel_vercel_logo, apps_guest_web_public_window_window_icon, apps_owner_web_public_file_file_icon, apps_owner_web_public_globe_globe_icon, apps_owner_web_public_next_next_js_logo, apps_owner_web_public_vercel_vercel_logo, apps_owner_web_public_window_window_icon [INFERRED 0.95]
- **Mise Brand Asset Set (owner-web)** — apps_owner_web_public_brand_cover_cover_image, apps_owner_web_public_brand_og_cover_og_cover_image, apps_owner_web_public_brand_logo_mark_logo_mark, apps_owner_web_src_app_icon_app_favicon, apps_guest_web_public_brand_cover_mise_restaurant_revenue_copilot [INFERRED 0.85]

## Communities (83 total, 26 thin omitted)

### Community 0 - "Order Path Tests"
Cohesion: 0.08
Nodes (26): seed_data(), sign_value(), get_db(), MenuItem, Restaurant, GuestSession, assert_no_unit_cost(), concurrent_order_env() (+18 more)

### Community 1 - "Owner Menu & Ingest API"
Cohesion: 0.08
Nodes (28): extract_content(), parse_json_content(), _build_owner_item_response(), daily_brief(), delete_menu_item(), _get_restaurant(), ingest_menu(), list_owner_menu_items() (+20 more)

### Community 2 - "Auth & Signed Cookies"
Cohesion: 0.06
Nodes (22): clear_auth_cookie(), get_current_guest_session(), get_current_role(), require_owner(), require_staff_or_owner(), set_auth_cookie(), set_guest_cookie(), unsign_value() (+14 more)

### Community 3 - "Schema Constraint Tests"
Cohesion: 0.12
Nodes (24): assert_violates(), _create_test_menu_item(), _create_test_order(), _create_test_restaurant(), _create_test_session(), test_guest_session_bad_dietary_preference_rejected(), test_menu_item_bad_allergen_code(), test_menu_item_gluten_free_with_gluten_rejected() (+16 more)

### Community 4 - "Guest Web Dependencies"
Cohesion: 0.04
Nodes (47): dependencies, api-client, @fontsource-variable/inter, next, qrcode, react, react-dom, devDependencies (+39 more)

### Community 5 - "Owner Web Dependencies"
Cohesion: 0.04
Nodes (47): dependencies, api-client, @fontsource-variable/inter, next, qrcode, react, react-dom, devDependencies (+39 more)

### Community 6 - "API Client Package"
Cohesion: 0.07
Nodes (25): dependencies, openapi-fetch, devDependencies, openapi-typescript, typescript, exports, ./schema, typescript (+17 more)

### Community 7 - "Kitchen Orders API"
Cohesion: 0.16
Nodes (13): AuditLog, DiningTable, Order, publish_event(), _build_kitchen_order_response(), bump_order(), get_kitchen_orders(), _get_restaurant() (+5 more)

### Community 8 - "Guest Session API"
Cohesion: 0.13
Nodes (14): create_guest_session(), get_guest_menu(), get_guest_session(), guest_chat(), patch_guest_session(), AIChatResult, ChatMessageRequest, ChatMessageResponse (+6 more)

### Community 9 - "Order Creation & Idempotency"
Cohesion: 0.11
Nodes (9): compute_payload_hash(), create_order(), get_order(), is_idempotency_unique_violation(), stream_order(), CreateOrderRequest, OrderItemRequest, OrderItemResponse (+1 more)

### Community 10 - "Database Models"
Cohesion: 0.19
Nodes (3): Base, MenuTranslation, OrderItem

### Community 11 - "Next.js Layouts & Middleware"
Cohesion: 0.08
Nodes (10): nextConfig, metadata, viewport, nextConfig, DashboardLayout(), metadata, LoginPage(), config (+2 more)

### Community 12 - "Test DB Fixtures"
Cohesion: 0.12
Nodes (7): client(), db_session(), _drop_test_database(), _ensure_test_database_exists(), _get_maintenance_connection(), _run_alembic_migrations(), test_engine()

### Community 13 - "Inference Client Tests"
Cohesion: 0.14
Nodes (9): test_error_response_never_contains_api_key(), _make_fake_response(), test_inference_client_chat_success(), handler(), test_inference_client_error_raises(), test_inference_client_validation_fallback(), test_inference_client_vision_success(), test_inference_client_with_pydantic_validation() (+1 more)

### Community 14 - "Seed & Inference Smoke"
Cohesion: 0.16
Nodes (5): async_main(), load_seed_data(), main(), main(), run_streaming_test()

### Community 15 - "FastAPI App & Metrics"
Cohesion: 0.14
Nodes (3): lifespan(), MetricsSample, inference_metrics()

### Community 16 - "Guest Menu & Cart"
Cohesion: 0.26
Nodes (17): GuestMenuPage(), MenuItem, MenuResponse, addToCart(), calculateCartTotal(), CartItem, CartState, clearCart() (+9 more)

### Community 17 - "Alembic Migrations"
Cohesion: 0.17
Nodes (8): upgrade(), upgrade(), upgrade(), downgrade(), upgrade(), upgrade(), downgrade(), upgrade()

### Community 18 - "Guest Chat & Rate Limits"
Cohesion: 0.13
Nodes (5): record_metrics(), check_global_rate_limit(), check_guest_chat_limit(), _build_menu_context(), handle_guest_chat()

### Community 19 - "Guest SSE Manager"
Cohesion: 0.17
Nodes (6): SseManager, SseManagerOptions, FakeEventSource, useSse(), UseSseOptions, UseSseReturn

### Community 20 - "Guest Web TS Config"
Cohesion: 0.11
Nodes (18): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+10 more)

### Community 21 - "Owner Web TS Config"
Cohesion: 0.11
Nodes (18): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+10 more)

### Community 22 - "Health & Debug SSE"
Cohesion: 0.14
Nodes (4): check_redis(), debug_sse(), _debug_sse_generator(), health_check()

### Community 23 - "Inference Payload Tests"
Cohesion: 0.12
Nodes (8): _filter_payload(), MockChatResponse, test_enforce_system_message_adds_default(), test_enforce_system_message_deduplicates(), test_enforce_system_message_moves_to_front(), test_enforce_system_message_replaces_developer_role(), test_filter_payload_converts_json_schema_to_json_object(), test_filter_payload_strips_unsupported_params()

### Community 24 - "Allergen Chip UI"
Cohesion: 0.13
Nodes (7): AllergenChip(), AllergenChipProps, IngestedItem, IngestedTranslation, MenuTranslation, OwnerMenuItem, KitchenLayout()

### Community 25 - "Mock Inference Server"
Cohesion: 0.15
Nodes (5): get_canned_response(), chat_completions(), ChatRequest, list_models(), Message

### Community 26 - "Kitchen Display Frontend"
Cohesion: 0.16
Nodes (11): DashboardOrdersPage(), KitchenOrder, KitchenOrderItem, OrdersResponse, KitchenDisplayPage(), KitchenOrder, KitchenOrderItem, OrdersResponse (+3 more)

### Community 27 - "Settings & Secret Guards"
Cohesion: 0.14
Nodes (3): Settings, test_config_strips_whitespace_from_api_key(), test_openrouter_free_model_guard()

### Community 28 - "Demo Mode Tests"
Cohesion: 0.21
Nodes (6): test_auth_config_endpoint(), test_demo_info_200_when_demo_mode_true(), test_demo_info_404_when_demo_mode_false(), test_demo_login_404_when_demo_mode_false(), test_demo_login_rate_limit_429(), test_demo_login_sets_cookie_when_demo_mode_true()

### Community 29 - "Allergen Engine"
Cohesion: 0.17
Nodes (4): compute_allergen_status(), find_test_vectors_path(), load_test_vectors(), test_allergen_service_vectors()

### Community 30 - "LLM Smoke Script"
Cohesion: 0.21
Nodes (4): _get_daily_cap_remaining(), main(), _make_tiny_png(), _print_ratelimit_headers()

### Community 32 - "ESLint Config"
Cohesion: 0.18
Nodes (8): compat, __dirname, eslintConfig, __filename, compat, __dirname, eslintConfig, __filename

### Community 33 - "Guest Order & Chat UI"
Cohesion: 0.23
Nodes (10): OrderDetails, OrderItem, OrderStatusPage(), DIETS, EU14_ALLERGENS, QrPickerPage(), ChatMessage, ChatPanel() (+2 more)

### Community 34 - "AI Privacy Tests"
Cohesion: 0.19
Nodes (5): _build_headers(), _sanitize_error(), test_build_headers_empty_when_no_key(), test_build_headers_uses_bearer_format(), test_sanitize_error_redacts_auth_header()

### Community 36 - "Inference Client Startup"
Cohesion: 0.18
Nodes (3): InferenceClient, mock_inference_app(), _attach_mock()

### Community 37 - "i18n Dictionaries"
Cohesion: 0.38
Nodes (6): en, dictionaries, getNestedValue(), translate(), it, TranslationDict

### Community 38 - "Compose Stack & Seed"
Cohesion: 0.20
Nodes (10): Seed Data (dev/demo only), trattoria_da_mario.json seed restaurant, api compose service, Docker Compose Dev Overrides (hot reload, published ports), guest-web compose service (:3000), owner-web compose service (:3001), postgres compose service, redis compose service (+2 more)

### Community 39 - "Backend Architecture Docs"
Cohesion: 0.20
Nodes (7): services/api FastAPI Backend (:8000), services/inference OpenAI-Compatible Engine / Mock (:8080), PostgreSQL 16, Redis 7 (Pub/Sub, Cache, Quotas), metrics_sample table, Generic LLM Client (Presets, Semaphore, Daily Cap), LLM Provider Presets (gemini, groq, openrouter, ollama, custom)

### Community 40 - "API Client TS Config"
Cohesion: 0.18
Nodes (10): compilerOptions, declaration, esModuleInterop, module, moduleResolution, outDir, skipLibCheck, strict (+2 more)

### Community 41 - "Health Tests"
Cohesion: 0.25
Nodes (3): test_debug_sse_endpoint_headers(), test_debug_sse_generator_direct(), test_health_returns_ok()

### Community 42 - "Brand Assets"
Cohesion: 0.40
Nodes (10): AMD Developer Hackathon, Mise Cover Image, Mise: Restaurant Revenue Copilot (brand), Mise Logo Mark, Mise Open Graph Cover, App Favicon (icon.svg), Mise Cover Image [owner-web], Mise Logo Mark [owner-web] (+2 more)

### Community 43 - "Home & Tables Pages"
Cohesion: 0.20
Nodes (5): AuthConfig, DemoInfo, HomePage(), TableItem, TablesPage()

### Community 44 - "Root Workspace Package"
Cohesion: 0.20
Nodes (9): engines, node, name, packageManager, private, scripts, build, lint (+1 more)

### Community 45 - "Daily Cap Tests"
Cohesion: 0.22
Nodes (4): mock_redis_for_client(), fake_expire(), fake_incr(), test_daily_request_cap_guard()

### Community 46 - "PWA Manifest"
Cohesion: 0.22
Nodes (8): background_color, description, display, icons, name, short_name, start_url, theme_color

### Community 47 - "Product Feature Docs"
Cohesion: 0.25
Nodes (7): Guest Ordering API Endpoints (/api/guest, /api/orders), Kitchen Display API Endpoints (/kitchen/orders, stream, bump, recall), Mise System Architecture, Running Mise (stub), Guest Mobile Web Ordering (guest-web), Kitchen Display System (KDS), Mise Restaurant Revenue Copilot Platform

### Community 49 - "Order Data Model Docs"
Cohesion: 0.29
Nodes (6): seed.py --rotate-qr QR token rotation, audit_log table, dining_table table, guest_session table, orders table, restaurant table

### Community 50 - "Provider Presets"
Cohesion: 0.29
Nodes (3): get_preset(), ProviderPreset, get_daily_cap_remaining()

### Community 52 - "CI & Workspace Config"
Cohesion: 0.29
Nodes (7): GitHub Actions CI test job, guest-web Next.js create-next-app README, owner-web Next.js create-next-app README, api-test compose service (test profile), inference mock compose service, pnpm Workspace (apps/*, packages/*), scripts/check_branding.sh Hygiene Audit

### Community 53 - "Allergen Safety Docs"
Cohesion: 0.33
Nodes (4): EU-14 Mandatory Allergens Catalog, menu_item table, menu_translation table, order_item table (immutable allergen snapshot)

### Community 57 - "Generated OpenAPI Schema"
Cohesion: 0.33
Nodes (5): components, $defs, operations, paths, webhooks

### Community 60 - "AI Simulator Page"
Cohesion: 0.40
Nodes (3): AiSimulatorPage(), SimulationRecommendation, SimulationResult

### Community 61 - "Daily Brief Page"
Cohesion: 0.40
Nodes (3): ActionItem, DailyBrief, DailyBriefPage()

### Community 62 - "Allergen Test Vectors"
Cohesion: 0.40
Nodes (4): description, note, $schema, vectors

### Community 64 - "Owner Copilot Features"
Cohesion: 0.50
Nodes (5): Owner Dashboard API Endpoints (menu, tables, ai/brief, ai/simulate, ingest), AI Daily Operations Brief, Owner Revenue Copilot, Scenario Simulator, Visual Menu Ingestion (VLM)

### Community 65 - "verify_d Script"
Cohesion: 0.70
Nodes (4): fail(), info(), pass(), verify_d.sh script

### Community 66 - "verify_e Script"
Cohesion: 0.70
Nodes (4): fail(), info(), pass(), verify_e.sh script

## Ambiguous Edges - Review These
- `Mise Restaurant Revenue Copilot Platform` → `Running Mise (stub)`  [AMBIGUOUS]
  docs/running.md · relation: conceptually_related_to

## Knowledge Gaps
- **67 isolated node(s):** `@fontsource-variable/inter`, `api-client`, `next`, `qrcode`, `react` (+62 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 597 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `InferenceClient` connect `Inference Client Startup` to `Owner Menu & Ingest API`, `AI Privacy Tests`, `Response Validation`, `Guest Session API`, `Inference Client Tests`, `FastAPI App & Metrics`, `Inference Dependency`, `Guest Chat & Rate Limits`, `Inference Payload Tests`, `Inference Client Core`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `InferenceClient` (e.g. with `lifespan()` and `guest_chat()`) actually correct?**
  _`InferenceClient` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `@fontsource-variable/inter`, `api-client`, `next` to the rest of the system?**
  _67 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Order Path Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.0819252432155658 - nodes in this community are weakly interconnected._
- **Why does `Settings` connect `Settings & Secret Guards` to `AI Privacy Tests`, `Inference Payload Tests`, `Config Isolation Tests`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `Restaurant` (e.g. with `seed_data()` and `get_demo_info()`) actually correct?**
  _`Restaurant` has 22 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Mise Restaurant Revenue Copilot Platform` and `Running Mise (stub)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._