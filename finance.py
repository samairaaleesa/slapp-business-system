from database import get_connection
import math

def best_combo_split(total_cookies, bundle_combos):
    """
    bundle_combos: list of {'id': combo_id, 'buy': buy_quantity, 'free': free_quantity}
    Returns the combination of bundles (any mix, each usable any number of times)
    that maximizes free cookies for exactly total_cookies, with the remainder as
    full-price singles. Uses dynamic programming so it's exact regardless of how
    many combo types exist.
    """
    if total_cookies <= 0:
        return {'free_cookies': 0, 'paid_cookies': 0, 'singles': 0, 'breakdown': []}

    dp = [0] * (total_cookies + 1)
    choice = [None] * (total_cookies + 1)

    for k in range(1, total_cookies + 1):
        best = dp[k - 1]
        best_choice = None
        for combo in bundle_combos:
            bundle_size = combo['buy'] + combo['free']
            if bundle_size <= k:
                candidate = dp[k - bundle_size] + combo['free']
                if candidate > best:
                    best = candidate
                    best_choice = combo['id']
        dp[k] = best
        choice[k] = best_choice

    breakdown = {}
    singles = 0
    remaining = total_cookies
    while remaining > 0:
        if choice[remaining] is not None:
            combo_id = choice[remaining]
            combo = next(c for c in bundle_combos if c['id'] == combo_id)
            breakdown[combo_id] = breakdown.get(combo_id, 0) + 1
            remaining -= (combo['buy'] + combo['free'])
        else:
            singles += 1
            remaining -= 1

    free_cookies = dp[total_cookies]
    return {
        'free_cookies': free_cookies,
        'paid_cookies': total_cookies - free_cookies,
        'singles': singles,
        'breakdown': [{'combo_id': cid, 'count': cnt} for cid, cnt in breakdown.items()]
    }

def calculate_order_cost(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    # get order items
    cursor.execute('''
        SELECT oi.flavour, oi.quantity
        FROM order_items oi
        WHERE oi.order_id = %s
    ''', (order_id,))
    
    items = cursor.fetchall()
    
    total_ingredient_cost = 0
    total_cookies = 0
    
    for flavour, quantity in items:
        total_cookies += quantity
        
        # get base yield
        cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (flavour,))
        base_yield = cursor.fetchone()[0]
        multiplier = quantity / base_yield
        
        # get ingredients and calculate cost
        cursor.execute('''
            SELECT ri.ingredient_name, ri.amount
            FROM recipe_ingredients ri
            JOIN recipes r ON ri.recipe_id = r.id
            WHERE r.name = %s
        ''', (flavour,))
        
        for ingredient_name, amount in cursor.fetchall():
            scaled_amount = amount * multiplier
            
            # get current active price
            cursor.execute('''
                SELECT packet_size, packet_price
                FROM ingredient_prices
                WHERE ingredient_name = %s AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            ''', (ingredient_name,))
            
            price_data = cursor.fetchone()
            if price_data:
                packet_size, packet_price = price_data
                cost_per_unit = packet_price / packet_size
                total_ingredient_cost += scaled_amount * cost_per_unit
    
    conn.close()
    return {
        'total_cookies': total_cookies,
        'ingredient_cost': round(total_ingredient_cost, 2)
    }

def calculate_order_revenue(order_id, manual_discount_pct=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT flavour, quantity FROM order_items WHERE order_id = %s
    ''', (order_id,))
    items = cursor.fetchall()
    total_cookies = sum(quantity for _, quantity in items)

    revenue = 0
    for flavour, quantity in items:
        cursor.execute('''
            SELECT price_per_cookie FROM pricing
            WHERE is_active = 1 AND flavour = %s
            LIMIT 1
        ''', (flavour,))
        price = cursor.fetchone()[0]
        revenue += quantity * price

    if manual_discount_pct is not None:
        # bulk order: manual discount instead of auto combo detection
        free_cookies = 0
        paid_cookies = total_cookies
        revenue = revenue * (1 - manual_discount_pct / 100)
        breakdown = []
    else:
        cursor.execute('''
            SELECT id, buy_quantity, free_quantity FROM combos
            WHERE is_active = 1 AND buy_quantity > 0 AND free_quantity > 0
        ''')
        bundle_combos = [{'id': r[0], 'buy': r[1], 'free': r[2]} for r in cursor.fetchall()]

        split = best_combo_split(total_cookies, bundle_combos)
        free_cookies = split['free_cookies']
        paid_cookies = split['paid_cookies']
        breakdown = split['breakdown']

        if free_cookies > 0 and total_cookies > 0:
            avg_price = revenue / total_cookies
            revenue -= free_cookies * avg_price

    conn.close()
    return {
        'total_cookies': total_cookies,
        'free_cookies': free_cookies,
        'paid_cookies': paid_cookies,
        'revenue': round(revenue, 2),
        'combo_breakdown': breakdown
    }

def calculate_packaging_cost(total_cookies):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT capacity, cost_per_box FROM packaging
        WHERE box_name = 'standard_box'
    ''')
    
    box = cursor.fetchone()
    conn.close()
    
    if not box:
        return 0
    
    capacity, cost_per_box = box
    boxes_needed = math.ceil(total_cookies / capacity)
    return round(boxes_needed * cost_per_box, 2)

def calculate_order_profit(order_id, manual_discount_pct=None):
    cost = calculate_order_cost(order_id)
    revenue = calculate_order_revenue(order_id, manual_discount_pct)
    
    packaging_cost = calculate_packaging_cost(revenue['total_cookies'])
    total_cost = cost['ingredient_cost'] + packaging_cost
    
    profit = revenue['revenue'] - total_cost
    margin = (profit / revenue['revenue']) * 100 if revenue['revenue'] > 0 else 0
    
    return {
        'order_id': order_id,
        'total_cookies': revenue['total_cookies'],
        'free_cookies': revenue['free_cookies'],
        'paid_cookies': revenue['paid_cookies'],
        'revenue': revenue['revenue'],
        'ingredient_cost': cost['ingredient_cost'],
        'packaging_cost': packaging_cost,
        'total_cost': round(total_cost, 2),
        'profit': round(profit, 2),
        'margin': round(margin, 2),
        'combo_breakdown': revenue['combo_breakdown']
    }
def get_financial_report(start_date, end_date):
    """Core Step-2 report: correct, cross-checked revenue/cost/profit for a date
    range, plus breakdowns by flavour, delivery zone, and order size/type, plus
    cancellations and cash reconciliation. All figures for delivered orders only
    unless stated otherwise (cancellations look at cancelled orders separately).

    Formula (matches orders.py/stock.py exactly, no double counting):
      revenue        = cookie revenue (after combo/bulk discount) + delivery_fee_charged
      total_cost     = ingredient_cost + packaging_cost + delivery_cost_actual
      profit         = revenue - total_cost
      margin         = profit / revenue * 100
    delivery_fee_charged and delivery_cost_actual are tracked as their own line
    items — delivery_fee_charged is revenue collected from the customer,
    delivery_cost_actual is the real Porter cost paid out.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT o.id, o.revenue, o.ingredient_cost, o.packaging_cost, o.delivery_fee_charged,
               o.delivery_cost_actual, o.profit, o.bulk_discount_pct, dz.zone_name
        FROM orders o
        LEFT JOIN delivery_zones dz ON o.delivery_zone_id = dz.id
        WHERE o.status = 'delivered' AND o.delivery_date BETWEEN %s AND %s
    ''', (start_date, end_date))
    delivered = cursor.fetchall()
    order_ids = [row[0] for row in delivered]

    items_by_order = {}
    combos_by_order = {}
    if order_ids:
        cursor.execute('SELECT order_id, flavour, quantity FROM order_items WHERE order_id = ANY(%s)', (order_ids,))
        for oid, flavour, qty in cursor.fetchall():
            items_by_order.setdefault(oid, []).append((flavour, qty))

        cursor.execute('''
            SELECT oc.order_id, cb.name FROM order_combos oc
            JOIN combos cb ON oc.combo_id = cb.id
            WHERE oc.order_id = ANY(%s)
        ''', (order_ids,))
        for oid, name in cursor.fetchall():
            combos_by_order.setdefault(oid, []).append(name)

    total_revenue = total_ingredient_cost = total_packaging_cost = 0.0
    total_delivery_fee_charged = total_delivery_cost_actual = total_profit = 0.0
    total_cookies = 0

    flavour_stats = {}
    zone_stats = {}
    size_stats = {}

    for (oid, revenue, ingredient_cost, packaging_cost, delivery_fee_charged,
         delivery_cost_actual, profit, bulk_discount_pct, zone_name) in delivered:

        revenue = float(revenue or 0)
        ingredient_cost = float(ingredient_cost or 0)
        packaging_cost = float(packaging_cost or 0)
        delivery_fee_charged = float(delivery_fee_charged or 0)
        delivery_cost_actual = float(delivery_cost_actual or 0)
        profit = float(profit or 0)

        total_revenue += revenue
        total_ingredient_cost += ingredient_cost
        total_packaging_cost += packaging_cost
        total_delivery_fee_charged += delivery_fee_charged
        total_delivery_cost_actual += delivery_cost_actual
        total_profit += profit

        items = items_by_order.get(oid, [])
        order_cookies = sum(q for _, q in items)
        total_cookies += order_cookies

        for flavour, qty in items:
            share = (qty / order_cookies) if order_cookies else 0
            f = flavour_stats.setdefault(flavour, {'cookies': 0, 'revenue': 0.0, 'ingredient_cost': 0.0, 'packaging_cost': 0.0, 'delivery_cost': 0.0})
            f['cookies'] += qty
            f['revenue'] += revenue * share
            f['ingredient_cost'] += ingredient_cost * share
            f['packaging_cost'] += packaging_cost * share
            f['delivery_cost'] += delivery_cost_actual * share

        zkey = zone_name or 'No Zone / Pickup'
        z = zone_stats.setdefault(zkey, {'orders': 0, 'revenue': 0.0, 'ingredient_cost': 0.0, 'packaging_cost': 0.0,
                                          'delivery_fee_charged': 0.0, 'delivery_cost_actual': 0.0, 'profit': 0.0})
        z['orders'] += 1
        z['revenue'] += revenue
        z['ingredient_cost'] += ingredient_cost
        z['packaging_cost'] += packaging_cost
        z['delivery_fee_charged'] += delivery_fee_charged
        z['delivery_cost_actual'] += delivery_cost_actual
        z['profit'] += profit

        if bulk_discount_pct is not None:
            category = 'Bulk / Custom Discount'
        else:
            names = combos_by_order.get(oid, [])
            category = ' + '.join(sorted(set(names))) if names else 'Single / No Combo'
        s = size_stats.setdefault(category, {'orders': 0, 'cookies': 0, 'revenue': 0.0, 'profit': 0.0})
        s['orders'] += 1
        s['cookies'] += order_cookies
        s['revenue'] += revenue
        s['profit'] += profit

    for f in flavour_stats.values():
        f['profit'] = f['revenue'] - f['ingredient_cost'] - f['packaging_cost'] - f['delivery_cost']
        f['margin'] = round(f['profit'] / f['revenue'] * 100, 2) if f['revenue'] else 0
        for k in ('revenue', 'ingredient_cost', 'packaging_cost', 'delivery_cost', 'profit'):
            f[k] = round(f[k], 2)

    for z in zone_stats.values():
        z['margin'] = round(z['profit'] / z['revenue'] * 100, 2) if z['revenue'] else 0
        for k in ('revenue', 'ingredient_cost', 'packaging_cost', 'delivery_fee_charged', 'delivery_cost_actual', 'profit'):
            z[k] = round(z[k], 2)

    for s in size_stats.values():
        s['margin'] = round(s['profit'] / s['revenue'] * 100, 2) if s['revenue'] else 0
        s['revenue'] = round(s['revenue'], 2)
        s['profit'] = round(s['profit'], 2)

    # -- cancellations --
    cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(revenue), 0) FROM orders
        WHERE status = 'cancelled' AND delivery_date BETWEEN %s AND %s
    ''', (start_date, end_date))
    cancelled_count, cancelled_lost_revenue = cursor.fetchone()
    cursor.execute('SELECT COUNT(*) FROM orders WHERE delivery_date BETWEEN %s AND %s', (start_date, end_date))
    all_orders_count = cursor.fetchone()[0]
    cancellation_rate = round(cancelled_count / all_orders_count * 100, 2) if all_orders_count else 0

    # -- cash reconciliation (cash basis: by transaction date, cross-checked against
    #    the transactions table's own ledger — note this can differ slightly from the
    #    order-basis P&L above if an order was delivered/marked outside this exact
    #    date window, since transactions are dated when logged, not by delivery_date) --
    def signed_txn_sum(where_clause, params):
        cursor.execute(f"SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE -amount END),0) FROM transactions WHERE {where_clause}", params)
        return float(cursor.fetchone()[0] or 0)

    cursor.execute('SELECT current_balance FROM balance ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    current_balance = float(row[0]) if row else 0.0

    net_after_end = signed_txn_sum('created_at > %s', (end_date,))
    net_during_period = signed_txn_sum('created_at BETWEEN %s AND %s', (start_date, end_date))
    ending_balance = current_balance - net_after_end
    starting_balance = ending_balance - net_during_period

    cursor.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='income' AND created_at BETWEEN %s AND %s", (start_date, end_date))
    cash_income = float(cursor.fetchone()[0] or 0)
    cursor.execute("SELECT category, COALESCE(SUM(amount),0) FROM transactions WHERE type='expense' AND created_at BETWEEN %s AND %s GROUP BY category ORDER BY 2 DESC", (start_date, end_date))
    expense_by_category = [(cat, round(float(amt), 2)) for cat, amt in cursor.fetchall()]
    cash_expenses = sum(amt for _, amt in expense_by_category)
    reconciles = abs((starting_balance + cash_income - cash_expenses) - ending_balance) < 0.01

    conn.close()

    margin = round(total_profit / total_revenue * 100, 2) if total_revenue else 0

    return {
        'period': f"{start_date} to {end_date}",
        'total_orders': len(delivered),
        'total_cookies': total_cookies,
        'revenue': round(total_revenue, 2),
        'ingredient_cost': round(total_ingredient_cost, 2),
        'packaging_cost': round(total_packaging_cost, 2),
        'delivery_fee_charged': round(total_delivery_fee_charged, 2),
        'delivery_cost_actual': round(total_delivery_cost_actual, 2),
        'total_cost': round(total_ingredient_cost + total_packaging_cost + total_delivery_cost_actual, 2),
        'profit': round(total_profit, 2),
        'margin': margin,
        'flavour_breakdown': dict(sorted(flavour_stats.items(), key=lambda kv: kv[1]['revenue'], reverse=True)),
        'zone_breakdown': dict(sorted(zone_stats.items(), key=lambda kv: kv[1]['revenue'], reverse=True)),
        'size_breakdown': dict(sorted(size_stats.items(), key=lambda kv: kv[1]['revenue'], reverse=True)),
        'best_seller': max(flavour_stats.items(), key=lambda kv: kv[1]['cookies']) if flavour_stats else None,
        'cancelled_count': cancelled_count,
        'cancellation_rate': cancellation_rate,
        'cancelled_lost_revenue': round(float(cancelled_lost_revenue or 0), 2),
        'cash_reconciliation': {
            'starting_balance': round(starting_balance, 2),
            'income': round(cash_income, 2),
            'expenses': round(cash_expenses, 2),
            'expense_by_category': expense_by_category,
            'ending_balance': round(ending_balance, 2),
            'reconciles': reconciles
        }
    }

def get_customer_insights(start_date, end_date):
    """Step-3 customer insights — repeat vs first-time, reorder rate, top
    customers, and each repeat customer's favourite flavour. Delivered orders
    only. Intended for the monthly report."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT c.id, c.name, COUNT(o.id) as orders, COALESCE(SUM(o.revenue),0) as spend
        FROM orders o JOIN customers c ON o.customer_id = c.id
        WHERE o.status = 'delivered' AND o.delivery_date BETWEEN %s AND %s
        GROUP BY c.id, c.name
    ''', (start_date, end_date))
    customer_rows = cursor.fetchall()

    repeat_customers = []
    first_time_count = 0
    for cid, name, order_count, spend in customer_rows:
        cursor.execute('''
            SELECT COUNT(*) FROM orders
            WHERE customer_id = %s AND status = 'delivered' AND delivery_date < %s
        ''', (cid, start_date))
        prior_orders = cursor.fetchone()[0]
        if prior_orders > 0:
            cursor.execute('''
                SELECT oi.flavour, SUM(oi.quantity) as total
                FROM order_items oi JOIN orders o ON oi.order_id = o.id
                WHERE o.customer_id = %s AND o.status != 'cancelled'
                GROUP BY oi.flavour ORDER BY total DESC LIMIT 1
            ''', (cid,))
            fav = cursor.fetchone()
            repeat_customers.append({
                'name': name, 'orders_this_period': order_count, 'spend': round(float(spend), 2),
                'favourite_flavour': fav[0] if fav else None
            })
        else:
            first_time_count += 1

    conn.close()

    total_customers = len(customer_rows)
    reorder_rate = round(len(repeat_customers) / total_customers * 100, 2) if total_customers else 0
    top_by_spend = sorted(
        [{'name': r[1], 'orders': r[2], 'spend': round(float(r[3]), 2)} for r in customer_rows],
        key=lambda c: c['spend'], reverse=True)[:5]
    top_by_orders = sorted(
        [{'name': r[1], 'orders': r[2], 'spend': round(float(r[3]), 2)} for r in customer_rows],
        key=lambda c: c['orders'], reverse=True)[:5]

    return {
        'total_customers': total_customers,
        'repeat_count': len(repeat_customers),
        'first_time_count': first_time_count,
        'reorder_rate': reorder_rate,
        'top_by_spend': top_by_spend,
        'top_by_orders': top_by_orders,
        'repeat_customers': repeat_customers
    }

def get_daily_timeseries(start_date, end_date):
    """Daily revenue/profit + per-flavour cookie counts for line-graph charts.
    Zero-fills days with no delivered orders so the chart has one point per day."""
    from datetime import datetime, timedelta as _td

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT delivery_date, SUM(revenue), SUM(profit)
        FROM orders WHERE status = 'delivered' AND delivery_date BETWEEN %s AND %s
        GROUP BY delivery_date
    ''', (start_date, end_date))
    by_day = {str(d): (float(rev or 0), float(prof or 0)) for d, rev, prof in cursor.fetchall()}

    cursor.execute('''
        SELECT o.delivery_date, oi.flavour, SUM(oi.quantity)
        FROM orders o JOIN order_items oi ON o.id = oi.order_id
        WHERE o.status = 'delivered' AND o.delivery_date BETWEEN %s AND %s
        GROUP BY o.delivery_date, oi.flavour
    ''', (start_date, end_date))
    flavour_rows = cursor.fetchall()
    conn.close()

    def as_date(d):
        return d if not isinstance(d, str) else datetime.strptime(d, '%Y-%m-%d').date()

    start_dt, end_dt = as_date(start_date), as_date(end_date)
    dates = []
    d = start_dt
    while d <= end_dt:
        dates.append(str(d))
        d += _td(days=1)

    flavour_series = {}
    for day, flavour, qty in flavour_rows:
        flavour_series.setdefault(flavour, {dt: 0 for dt in dates})
        flavour_series[flavour][str(day)] = int(qty)

    return {
        'dates': dates,
        'revenue': [by_day.get(dt, (0, 0))[0] for dt in dates],
        'profit': [by_day.get(dt, (0, 0))[1] for dt in dates],
        'flavour_series': {f: [vals[dt] for dt in dates] for f, vals in flavour_series.items()}
    }

def get_weekly_report(start_date, end_date):
    report = get_financial_report(start_date, end_date)
    report['timeseries'] = get_daily_timeseries(start_date, end_date)
    return report

def get_monthly_report(year, month):
    import calendar as _cal
    first_day = f"{year}-{month:02d}-01"
    last_day = f"{year}-{month:02d}-{_cal.monthrange(year, month)[1]}"

    report = get_financial_report(first_day, last_day)
    report['period'] = f"{month}/{year}"
    report['timeseries'] = get_daily_timeseries(first_day, last_day)
    report['customer_insights'] = get_customer_insights(first_day, last_day)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COALESCE(SUM(revenue),0), COALESCE(SUM(investment),0), COALESCE(SUM(revenue - investment),0)
        FROM popups
        WHERE EXTRACT(MONTH FROM event_date) = %s AND EXTRACT(YEAR FROM event_date) = %s
    ''', (month, year))
    popup_revenue, popup_investment, popup_profit = cursor.fetchone()
    conn.close()

    report['popup_revenue'] = round(float(popup_revenue), 2)
    report['popup_investment'] = round(float(popup_investment), 2)
    report['popup_profit'] = round(float(popup_profit), 2)
    report['grand_total_revenue'] = round(report['revenue'] + float(popup_revenue), 2)
    report['grand_total_profit'] = round(report['profit'] + float(popup_profit), 2)
    return report

def get_custom_report(start_date, end_date):
    return get_weekly_report(start_date, end_date)

def get_shopping_list(flavour, portions_to_make):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (flavour,))
    base_yield = cursor.fetchone()[0]
    multiplier = portions_to_make / base_yield
    
    cursor.execute('''
        SELECT ri.ingredient_name, ri.amount, ri.unit,
               ist.quantity as in_stock
        FROM recipe_ingredients ri
        LEFT JOIN ingredient_stock ist 
        ON ri.ingredient_name = ist.ingredient_name
        WHERE ri.recipe_id = (SELECT id FROM recipes WHERE name = %s)
    ''', (flavour,))
    
    ingredients = cursor.fetchall()
    shopping_list = []
    
    for ingredient_name, amount, unit, in_stock in ingredients:
        needed = amount * multiplier
        in_stock = in_stock or 0
        shortfall = max(0, needed - in_stock)
        
        if shortfall > 0:
            cursor.execute('''
                SELECT packet_size, packet_price 
                FROM ingredient_prices
                WHERE ingredient_name = %s AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            ''', (ingredient_name,))
            
            price_data = cursor.fetchone()
            if price_data:
                packet_size, packet_price = price_data
                packets_needed = math.ceil(shortfall / packet_size)
                estimated_cost = packets_needed * packet_price
                
                shopping_list.append({
                    'ingredient': ingredient_name,
                    'needed': round(needed, 2),
                    'in_stock': round(in_stock, 2),
                    'shortfall': round(shortfall, 2),
                    'packets_to_buy': packets_needed,
                    'estimated_cost': estimated_cost,
                    'packet_price': packet_price,
                    'unit': unit
                })
    
    total_cost = sum(item['estimated_cost'] for item in shopping_list)
    conn.close()
    
    return {
        'flavour': flavour,
        'portions_to_make': portions_to_make,
        'shopping_list': shopping_list,
        'total_estimated_cost': round(total_cost, 2)
    }

def get_combined_shopping_list(items_to_make):
    total_needed = {}
    
    from database import get_connection
    import math
    
    for flavour, portions in items_to_make.items():
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (flavour,))
        base_yield = cursor.fetchone()[0]
        multiplier = portions / base_yield
        
        cursor.execute('''
            SELECT ingredient_name, amount, unit FROM recipe_ingredients
            WHERE recipe_id = (SELECT id FROM recipes WHERE name = %s)
        ''', (flavour,))
        
        for ingredient_name, amount, unit in cursor.fetchall():
            scaled = amount * multiplier
            if ingredient_name in total_needed:
                total_needed[ingredient_name]['needed'] += scaled
            else:
                total_needed[ingredient_name] = {
                    'ingredient': ingredient_name,
                    'needed': scaled,
                    'unit': unit
                }
        conn.close()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    total_cost = 0
    shopping_list = []
    
    for ingredient_name, data in total_needed.items():
        cursor.execute('SELECT quantity FROM ingredient_stock WHERE ingredient_name = %s', (ingredient_name,))
        result = cursor.fetchone()
        in_stock = result[0] if result else 0
        shortfall = max(0, data['needed'] - in_stock)
        
        if shortfall > 0:
            cursor.execute('''
                SELECT packet_size, packet_price FROM ingredient_prices
                WHERE ingredient_name = %s AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
            ''', (ingredient_name,))
            price_data = cursor.fetchone()
            if price_data:
                packet_size, packet_price = price_data
                packets = math.ceil(shortfall / packet_size)
                cost = packets * packet_price
                total_cost += cost
                shopping_list.append({
                    'ingredient': ingredient_name,
                    'needed': round(data['needed'], 2),
                    'in_stock': round(in_stock, 2),
                    'shortfall': round(shortfall, 2),
                    'packets_to_buy': packets,
                    'estimated_cost': cost,
                    'packet_price': packet_price,
                    'unit': data['unit']
                })
    
    conn.close()
    return {
        'shopping_list': shopping_list,
        'total_estimated_cost': round(total_cost, 2)
    }

