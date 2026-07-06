# SLAPP Business Management System

> Built and used in production for a real business — every feature exists because I needed it.

A Flask + PostgreSQL system that runs the day-to-day operations of [SLAPP](https://instagram.com/slappverse), my cookie brand — orders, inventory, finances, and production planning, end to end.

## Why this exists

I run SLAPP alongside a full engineering course load. Spreadsheets could store data but couldn't *do* anything — every order meant manually recalculating finances, checking stock, updating cashflow, and figuring out what to bake. This system replaces all of that manual work with automated business logic.

## What it does

**Order lifecycle with stock reservation**
Orders can only be placed against available cookie stock and packaging. Placing an order reserves inventory, delivery deducts it, and cancellation releases it — stock counts stay accurate without manual intervention. Combo offers (Buy X Get Y Free, percentage discounts) apply at order time and flow through to profit calculations automatically.

**Bake briefs**
Select any delivery date and the system generates a production brief: total cookies to bake by flavour, plus a full per-order breakdown showing exactly which cookies go into each delivery. No more cross-referencing order lists the night before.

**Recipe scaling**
Enter a flavour and target quantity — the system scales the recipe and outputs exact ingredient amounts for that production run. Recipes are editable: add, remove, or adjust ingredients and the costing updates automatically.

**Ingredient intelligence**
When stock runs low, the restock planner calculates how much to make based on demand predictions and generates a combined shopping list across all low-stock flavours. Confirm the purchase and ingredient stock updates automatically — actual spend is editable before confirming so real prices override estimates.

**Automated finance**
Profit, margin, revenue, ingredient cost, and packaging cost are calculated per order at creation time. Delivering an order automatically posts revenue to cashflow. Cancelling an order excludes it from all reports.
Weekly reports show orders, revenue, profit, and flavour breakdown for any calendar week. Monthly reports rank weeks best to worst and break down delivery vs popup revenue. Custom date range reports cover any period. All reports only count delivered orders.

**Cash flow tracking**
Every financial event posts a transaction automatically: order delivered → income logged, grocery shop confirmed → expense logged, packaging purchased → expense logged, popup invested → expense logged, popup revenue → income logged. Manual transactions can be added for anything else. Balance updates in real time.

**Pop-up event logging**
Log cookies produced, sold, given free, revenue, game revenue, investment, and notes per event. Pop-up profit rolls into monthly finance reports separately from delivery revenue.

**Demand prediction**
Based on delivered order history, the system predicts how many cookies to produce per flavour to cover the next 3 weeks with a 10% buffer. Accuracy improves as order volume grows.

**Low-stock alerts**
Editable thresholds per cookie flavour, ingredient, and packaging type trigger alerts on the dashboard before I run out. Cookie and ingredient alerts show available quantity, not just total — reserved stock is excluded.

**Settings**
Cookie prices, combo offers, low-stock thresholds, and packaging costs are all configurable from the UI. Change a price and all downstream calculations follow.

## Tech stack

- **Backend:** Python, Flask
- **Database:** PostgreSQL (13 tables) via psycopg2
- **Frontend:** Server-rendered Jinja2 HTML templates (~30 views)

## Database schema

`customers` · `orders` · `order_items` · `recipes` · `recipe_ingredients` · `cookie_stock` · `ingredient_stock` · `ingredient_prices` · `packaging` · `pricing` · `combos` · `popups` · `transactions` · `balance`

## Project structure

```
slapp/
├── app.py          # Flask routes (~850 lines, 40+ routes)
├── orders.py       # Order lifecycle, bake briefs, stock reservation
├── stock.py        # Stock management, dough logging, delivery deduction
├── finance.py      # Revenue, cost, profit, reports, shopping lists
├── prediction.py   # Demand forecasting
├── management.py   # Recipes, pricing, combos, customers, settings
├── cashflow.py     # Balance tracking, transaction logging
├── database.py     # Schema creation, connection management
├── migrate.py      # Data migration from JSON seed files
└── templates/      # ~30 Jinja2 HTML templates
```

## What's next

- **AI layer** — an agent that drafts customer DM replies, suggests restocks, and flags anomalies (a Groq-based DM drafter already exists as a separate project)
- **UI polish** — function came first; design is the next pass
- **Smarter prediction** — once real order volume flows through, the demand model gets meaningful training data
- **Mobile view** — the system currently runs on desktop browser; a responsive pass would make it usable on phone during pop-ups
