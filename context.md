# SLAPP Business System — Technical & Business Context

SLAPP is a homemade cookie brand in Bangalore run by Aleesa (engineering student). Flask + PostgreSQL system managing the entire operation. Instagram: @slappverse. Pre-order model: customers DM orders, cookies baked from frozen dough, delivered via Porter.

## Products & Pricing
- Flavours (DB keys): the_classic_slapp (Classic, choco chip), the_brownie_slapp (Brownie), comfort_slapp (Comfort, cinnamon), red_velvet_slapp (Velvety, red velvet)
- Single cookie ₹99. Combos: buy4get1free (5 for ₹396), buy9get3free (12 for ₹891). Percentage-discount combos also supported.
- Combo math: free_cookies = floor(total/(buy+free)) × free, deducted at average price. Percentage: revenue × (1 − pct/100). Partial bundles price correctly (7 cookies w/ buy4get1 = 1 free = ₹594).
- Business rule: bundle sizes are policy, enforced by the human, NOT the system — any quantity is accepted; anomaly checks flag non-conforming combos for review.

## Stack
- Flask (app.py, ~45 routes), PostgreSQL db `slapp_db` via psycopg2, Jinja2 templates (~35), runs at 127.0.0.1:8080 via `python3 app.py`
- .env holds GROQ_API_KEY (DM agent) and ANTHROPIC_API_KEY (order agent)

## Database (14 tables)
- **customers**: phone is the unique identity (ON CONFLICT phone). One customer, many orders.
- **orders**: status pending/delivered/cancelled; stores finance SNAPSHOTS (revenue, ingredient_cost, packaging_cost, total_cost, profit, margin) calculated at creation/edit, NOT live. combo_id nullable. Reports count delivered only.
- **order_items**: flavour + quantity lines per order.
- **cookie_stock**: quantity (total) and reserved (held by pending orders). Available = quantity − reserved. Order placement reserves; delivery deducts both; cancellation releases reserved only.
- **ingredient_stock**: grams/pieces; deducted when dough is logged (log_dough_made), NOT at order time.
- **ingredient_prices**: price history. cost_per_unit = packet_price/packet_size. Only is_active=1 rows used.
- **recipes + recipe_ingredients**: base_yield = cookies per standard batch. Scaling = (target/base_yield) × amount.
- **pricing**: price per cookie per flavour (unique constraint on flavour — updates are simple UPDATE).
- **combos**: buy_quantity/free_quantity OR discount_percentage; is_active flag.
- **packaging**: box types with capacity, cost_per_box, stock. Checked at order placement (blocks orders); deducted at delivery via greedy algorithm (largest boxes first).
- **transactions + balance**: auto cashflow. Delivery→income, shopping confirm→expense, packaging Add→expense, popup→investment expense + revenue income. balance = single-row running total, auto-inits if empty.
- **popups**: popup event log (produced, sold, given free, revenue, investment, game data). Rolls into monthly reports separately.

## Key modules
- **orders.py**: add_customer (upsert on phone), create_order (insert→finance calc→reserve), cancel_order (release reservation), update_order, update_order_items (release→check→swap→re-reserve→recalc finance; FULL REPLACEMENT of items), get_bake_brief, get_orders_by_delivery_date
- **stock.py**: log_dough_made (scales recipe, deducts ingredients, adds cookie stock), log_order_delivered (deducts stock+packaging, marks delivered, logs income), reserve/release, check_stock_for_order, threshold checks
- **finance.py**: calculate_order_revenue/cost/profit, weekly/monthly/custom reports (delivered only, calendar weeks Mon-Sun), get_combined_shopping_list (total needs across ALL flavours, checked against stock ONCE)
- **cashflow.py**: add_transaction (updates balance), get_balance, spending summaries
- **prediction.py**: demand forecast from delivered history (avg weekly × weeks + buffer)
- **management.py**: recipes/pricing/combos/customers/thresholds CRUD
- **dm_agent.py**: Groq/llama — extracts structured orders from pasted Instagram DMs (page /orders/dm; two-form flow: extract → editable confirm with calendar + auto combo detection)
- **order_agent.py**: Claude (claude-haiku-4-5, native tool calling) — conversational agent at /agent/orders. Tools: get_orders, get_order_details, get_customer_insights, get_order_stats, run_anomaly_checks, cancel_order, edit_order_items (repacks combo+finance, packaging check, drafts customer message on failure), edit_order_details, mark_delivered, navigate. Rules: destructive actions ALWAYS confirmed first (School B); anomalies presented, never auto-fixed; chat-first, navigate only on explicit request. Chat history in Flask session.

## Conventions & gotchas
- Finance verified correct against hand calculations (68.8% margin typical on standard orders)
- Route order matters in app.py: /orders/all, /orders/new, /orders/dm before /orders/<int:id>
- pip3 with --break-system-packages; Flask restart needed after crashes
- Prices: butter 500g/₹286, flour 500g/₹50, cocoa 1000g/₹1480, eggs 30/₹210 (full table in ingredient_prices)
- Cookie thresholds: Comfort 5, Velvety 10, Brownie 20, Classic 15; box threshold 20