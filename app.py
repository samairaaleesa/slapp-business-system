from flask import Flask, render_template, request, redirect, url_for, jsonify
from orders import add_customer, create_order, cancel_order, update_order, update_order_items, get_orders_by_delivery_date, get_bake_brief, format_orders
from stock import check_low_stock, check_low_ingredients, check_low_packaging, log_dough_made, log_order_delivered, check_stock_for_order, set_cookie_stock, add_cookie_stock, set_ingredient_stock, add_ingredient_stock
from finance import calculate_order_profit, get_weekly_report, get_monthly_report, get_custom_report, get_shopping_list
from prediction import predict_all_flavours
from management import get_all_recipes, get_recipe_with_ingredients, add_recipe, delete_recipe, add_ingredient_to_recipe, remove_ingredient_from_recipe, update_ingredient_amount, get_all_pricing, update_flavour_price, get_all_combos, add_combo, deactivate_combo, get_all_customers, get_customer_orders, update_customer, delete_customer, update_ingredient_price, update_cookie_threshold, update_ingredient_threshold, get_all_delivery_zones, add_delivery_zone, update_delivery_zone, deactivate_delivery_zone, activate_delivery_zone, deactivate_packaging, activate_packaging
from datetime import date, timedelta
from cashflow import get_balance, add_transaction, get_transactions, get_spending_summary, set_initial_balance
import math
import json
from dotenv import load_dotenv
import os
load_dotenv()

app = Flask(__name__)
app.secret_key = 'slapp-secret-key-change-this-later'

@app.route('/')
def dashboard():
    low_cookies = check_low_stock()
    low_ingredients = check_low_ingredients()
    low_packaging = check_low_packaging()
    predictions = predict_all_flavours()
    
    tomorrow = date.today() + timedelta(days=1)
    bake_brief = get_bake_brief(str(tomorrow))
    
    return render_template('dashboard.html',
        low_cookies=low_cookies,
        low_ingredients=low_ingredients,
        low_packaging=low_packaging,
        predictions=predictions,
        bake_brief=bake_brief,
        tomorrow=tomorrow,
        today=date.today()
    )

@app.route('/orders')
def orders_landing():
    return render_template('orders_landing.html')

@app.route('/orders/date')
def orders_page():
    delivery_date = request.args.get('date', str(date.today() + timedelta(days=1)))
    search = request.args.get('search', '').strip()
    
    if search:
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.id, c.name, c.phone, o.address, o.status, o.delivery_required,
                   oi.flavour, oi.quantity
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            JOIN order_items oi ON o.id = oi.order_id
            WHERE c.name ILIKE %s
            ORDER BY o.delivery_date ASC
        ''', (f'%{search}%',))
        rows = cursor.fetchall()
        conn.close()
        formatted = format_orders(rows)
    else:
        rows = get_orders_by_delivery_date(delivery_date)
        formatted = format_orders(rows)
    
    return render_template('orders.html',
        orders=formatted,
        delivery_date=delivery_date,
        today=date.today(),
        search=search
    )

@app.route('/orders/all')
def all_orders():
    from database import get_connection
    status_filter = request.args.get('status', 'pending')
    search = request.args.get('search', '').strip()
    search_by = request.args.get('search_by', 'name')
    order_type = request.args.get('order_type', 'regular')
    bulk_clause = 'o.bulk_discount_pct IS NOT NULL' if order_type == 'bulk' else 'o.bulk_discount_pct IS NULL'

    conn = get_connection()
    cursor = conn.cursor()

    if search:
        if search_by == 'order_id':
            try:
                cursor.execute(f'''
                    SELECT o.id, c.name, c.phone, o.address, o.status,
                           o.delivery_date, o.revenue, o.profit, o.delivery_required, o.bulk_discount_pct,
                           oi.flavour, oi.quantity
                    FROM orders o
                    JOIN customers c ON o.customer_id = c.id
                    JOIN order_items oi ON o.id = oi.order_id
                    WHERE o.id = %s AND {bulk_clause}
                    ORDER BY o.delivery_date ASC
                ''', (int(search),))
            except ValueError:
                cursor.execute('SELECT 1 WHERE false')
        elif search_by == 'phone':
            cursor.execute(f'''
               SELECT o.id, c.name, c.phone, o.address, o.status,
                       o.delivery_date, o.revenue, o.profit, o.delivery_required, o.bulk_discount_pct,
                       oi.flavour, oi.quantity
                FROM orders o
                JOIN customers c ON o.customer_id = c.id
                JOIN order_items oi ON o.id = oi.order_id
                WHERE c.phone ILIKE %s AND {bulk_clause}
                ORDER BY o.delivery_date ASC, o.id ASC
            ''', (f'%{search}%',))
        else:
            cursor.execute(f'''
                SELECT o.id, c.name, c.phone, o.address, o.status,
                       o.delivery_date, o.revenue, o.profit, o.delivery_required, o.bulk_discount_pct,
                       oi.flavour, oi.quantity
                FROM orders o
                JOIN customers c ON o.customer_id = c.id
                JOIN order_items oi ON o.id = oi.order_id
                WHERE c.name ILIKE %s AND {bulk_clause}
                ORDER BY o.delivery_date ASC, o.id ASC
            ''', (f'%{search}%',))
    else:
        cursor.execute(f'''
            SELECT o.id, c.name, c.phone, o.address, o.status,
                   o.delivery_date, o.revenue, o.profit, o.delivery_required, o.bulk_discount_pct,
                   oi.flavour, oi.quantity
             FROM orders o
            JOIN customers c ON o.customer_id = c.id
            JOIN order_items oi ON o.id = oi.order_id
            WHERE o.status = %s AND {bulk_clause}
            ORDER BY o.delivery_date ASC, o.id ASC
        ''', (status_filter,))

    rows = cursor.fetchall()

    cursor.execute(f'SELECT COUNT(*) FROM orders o WHERE status = %s AND {bulk_clause}', ('pending',))
    pending_count = cursor.fetchone()[0]
    cursor.execute(f'SELECT COUNT(*) FROM orders o WHERE status = %s AND {bulk_clause}', ('delivered',))
    delivered_count = cursor.fetchone()[0]
    cursor.execute(f'SELECT COUNT(*) FROM orders o WHERE status = %s AND {bulk_clause}', ('cancelled',))
    cancelled_count = cursor.fetchone()[0]

    conn.close()

    orders = {}
    for row in rows:
        order_id = row[0]
        if order_id not in orders:
            orders[order_id] = {
                'customer': row[1],
                'phone': row[2],
                'address': row[3],
                'status': row[4],
                'delivery_date': row[5],
                'revenue': row[6],
                'profit': row[7],
                'delivery_required': row[8],
                'bulk_discount_pct': row[9],
                'items': []
            }
        orders[order_id]['items'].append((row[10], row[11]))

    return render_template('all_orders.html',
        orders=orders,
        status_filter=status_filter,
        order_type=order_type,
        pending_count=pending_count,
        delivered_count=delivered_count,
        cancelled_count=cancelled_count,
        search=search,
        search_by=search_by
    )

@app.route('/orders/<int:order_id>/deliver')
def deliver_order(order_id):
    delivery_fee = float(request.args.get('fee', 0))
    log_order_delivered(order_id, delivery_fee)
    next_page = request.args.get('next', 'orders_page')
    if next_page == 'all_orders':
        return redirect(url_for('all_orders', order_type=request.args.get('order_type', 'regular')))
    return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/cancel')
def cancel_order_route(order_id):
    cancel_order(order_id)
    next_page = request.args.get('next', 'orders_page')
    if next_page == 'all_orders':
        return redirect(url_for('all_orders', order_type=request.args.get('order_type', 'regular')))
    return redirect(url_for('orders_page'))

@app.route('/orders/new', methods=['GET', 'POST'])
def new_order():
    if request.method == 'POST':
        name = request.form['name'].strip().title()
        phone = request.form['phone']
        address = request.form['address']
        delivery_date = request.form['delivery_date']
        notes = request.form.get('notes', '')
        delivery_required = bool(request.form.get('delivery_required'))
        delivery_zone_id = request.form.get('delivery_zone_id') or None

        items = {}
        recipes = get_all_recipes()
        for recipe in recipes:
            flavour = recipe[1]
            qty = request.form.get(f'qty_{flavour}', 0)
            if qty and int(qty) > 0:
                items[flavour] = int(qty)

        if not items:
            return redirect(url_for('new_order'))

        warnings = check_stock_for_order(items)
        if warnings:
            recipes = get_all_recipes()
            combos = get_all_combos()
            zones = get_all_delivery_zones()
            return render_template('new_order.html',
                recipes=recipes,
                combos=combos,
                zones=zones,
                warnings=warnings
            )
        # check packaging (across all active box types, matching real delivery-time allocation)
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        total_cookies = sum(items.values())
        cursor.execute('SELECT capacity, stock FROM packaging WHERE is_active = 1')
        boxes = cursor.fetchall()
        total_capacity = sum(cap * stock for cap, stock in boxes)
        conn.close()

        if total_capacity < total_cookies:
            recipes = get_all_recipes()
            combos = get_all_combos()
            zones = get_all_delivery_zones()
            return render_template('new_order.html',
                recipes=recipes,
                combos=combos,
                zones=zones,
                warnings=warnings,
                packaging_warning=f'Need to pack {total_cookies} cookies but total box capacity available is {total_capacity}'
            )

        customer_id = add_customer(name, phone, address)
        order_id = create_order(customer_id, delivery_date, address, items, notes, delivery_required, delivery_zone_id=delivery_zone_id)

        return redirect(url_for('orders_page'))

    recipes = get_all_recipes()
    combos = get_all_combos()
    zones = get_all_delivery_zones()
    return render_template('new_order.html',
        recipes=recipes,
        zones=zones,
        combos=combos,
        warnings=[],
        packaging_warning=None
    )

@app.route('/orders/bulk', methods=['GET', 'POST'])
def bulk_order():
    if request.method == 'POST':
        name = request.form['name'].strip().title()
        phone = request.form['phone']
        address = request.form['address']
        delivery_date = request.form['delivery_date']
        notes = request.form.get('notes', '')
        delivery_required = bool(request.form.get('delivery_required'))
        bulk_discount_pct = float(request.form.get('bulk_discount_pct') or 0)
        delivery_zone_id = request.form.get('delivery_zone_id') or None

        items = {}
        recipes = get_all_recipes()
        for recipe in recipes:
            flavour = recipe[1]
            qty = request.form.get(f'qty_{flavour}', 0)
            if qty and int(qty) > 0:
                items[flavour] = int(qty)

        if not items:
            return redirect(url_for('bulk_order'))

        warnings = check_stock_for_order(items)
        if warnings:
            recipes = get_all_recipes()
            zones = get_all_delivery_zones()
            return render_template('bulk_order.html', recipes=recipes, zones=zones, warnings=warnings)

        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        total_cookies = sum(items.values())
        cursor.execute('SELECT capacity, stock FROM packaging WHERE is_active = 1')
        boxes = cursor.fetchall()
        total_capacity = sum(cap * stock for cap, stock in boxes)
        conn.close()

        if total_capacity < total_cookies:
            recipes = get_all_recipes()
            zones = get_all_delivery_zones()
            return render_template('bulk_order.html',
                recipes=recipes,
                zones=zones,
                warnings=warnings,
                packaging_warning=f'Need to pack {total_cookies} cookies but total box capacity available is {total_capacity}'
            )

        customer_id = add_customer(name, phone, address)
        order_id = create_order(customer_id, delivery_date, address, items, notes, delivery_required, bulk_discount_pct, delivery_zone_id)

        return redirect(url_for('orders_page'))

    recipes = get_all_recipes()
    zones = get_all_delivery_zones()
    return render_template('bulk_order.html', recipes=recipes, zones=zones, warnings=[], packaging_warning=None)

@app.route('/stock')
def stock_page():
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT flavour, quantity, reserved, low_stock_threshold FROM cookie_stock ORDER BY flavour')
    cookie_stock = cursor.fetchall()
    cursor.execute('SELECT ingredient_name, quantity, unit, low_stock_threshold FROM ingredient_stock ORDER BY ingredient_name')
    ingredient_stock = cursor.fetchall()
    cursor.execute('SELECT box_name, capacity, cost_per_box, stock, low_stock_threshold, is_active FROM packaging ORDER BY is_active DESC, box_name')
    packaging = cursor.fetchall()
    conn.close()

    predictions = predict_all_flavours()
    
    return render_template('stock.html',
        cookie_stock=cookie_stock,
        ingredient_stock=ingredient_stock,
        packaging=packaging,
        predictions=predictions
    )

@app.route('/stock/dough', methods=['GET', 'POST'])
def log_dough():
    if request.method == 'POST':
        flavour = request.form['flavour']
        portions = int(request.form['portions'])
        log_dough_made(flavour, portions)
        return redirect(url_for('stock_page'))
    
    recipes = get_all_recipes()
    return render_template('log_dough.html', recipes=recipes)

@app.route('/stock/cookie/<flavour>/add', methods=['GET', 'POST'])
def add_cookie_stock_route(flavour):
    if request.method == 'POST':
        quantity = int(request.form['quantity'])
        add_cookie_stock(flavour, quantity)
        return redirect(url_for('stock_page'))
    return render_template('add_stock.html', flavour=flavour, action='add')

@app.route('/stock/cookie/<flavour>/set', methods=['GET', 'POST'])
def set_cookie_stock_route(flavour):
    if request.method == 'POST':
        quantity = int(request.form['quantity'])
        set_cookie_stock(flavour, quantity)
        return redirect(url_for('stock_page'))
    return render_template('add_stock.html', flavour=flavour, action='set')

@app.route('/stock/ingredients/set', methods=['GET', 'POST'])
def set_ingredients():
    from database import get_connection
    if request.method == 'POST':
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT ingredient_name FROM ingredient_stock')
        ingredients = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        for ingredient in ingredients:
            qty = request.form.get(f'qty_{ingredient}')
            if qty:
                set_ingredient_stock(ingredient, float(qty))
        
        return redirect(url_for('stock_page'))
    
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT ingredient_name, quantity, unit FROM ingredient_stock ORDER BY ingredient_name')
    ingredients = cursor.fetchall()
    conn.close()
    
    return render_template('set_ingredients.html', ingredients=ingredients)

@app.route('/finance')
def finance_landing():
    return render_template('finance_landing.html')

@app.route('/finance/weekly')
def finance_weekly():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    selected_start = request.args.get('start', str(start_of_week))
    selected_end = request.args.get('end', str(end_of_week))
    
    from datetime import datetime
    start_dt = datetime.strptime(selected_start, '%Y-%m-%d').date()
    end_dt = datetime.strptime(selected_end, '%Y-%m-%d').date()
    
    start_formatted = start_dt.strftime('%d %b')
    end_formatted = end_dt.strftime('%d %b %Y')
    
    prev_start = str(start_dt - timedelta(days=7))
    prev_end = str(end_dt - timedelta(days=7))
    next_start = str(start_dt + timedelta(days=7))
    next_end = str(end_dt + timedelta(days=7))
    
    weekly = get_weekly_report(selected_start, selected_end)
    
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.id, c.name, o.delivery_date, o.status,
               o.revenue, o.profit, o.margin
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.delivery_date BETWEEN %s AND %s
        ORDER BY o.delivery_date ASC
    ''', (selected_start, selected_end))
    all_orders = cursor.fetchall()
    conn.close()
    
    return render_template('finance_weekly.html',
        weekly=weekly,
        all_orders=all_orders,
        selected_start=selected_start,
        selected_end=selected_end,
        prev_start=prev_start,
        prev_end=prev_end,
        next_start=next_start,
        next_end=next_end,
        start_formatted=start_formatted,
        end_formatted=end_formatted
    )

@app.route('/finance/monthly')
def finance_monthly():
    today = date.today()
    selected_year = int(request.args.get('year', today.year))
    selected_month = int(request.args.get('month', today.month))
    
    from datetime import datetime
    import calendar
    
    prev_month = selected_month - 1 if selected_month > 1 else 12
    prev_year = selected_year if selected_month > 1 else selected_year - 1
    next_month = selected_month + 1 if selected_month < 12 else 1
    next_year = selected_year if selected_month < 12 else selected_year + 1
    
    monthly = get_monthly_report(selected_year, selected_month)
    month_name = datetime(selected_year, selected_month, 1).strftime('%B %Y')
    
    first_day = date(selected_year, selected_month, 1)
    last_day = date(selected_year, selected_month, calendar.monthrange(selected_year, selected_month)[1])

    week_start = first_day - timedelta(days=first_day.weekday())

    weeks = []
    while week_start <= last_day:
        week_end = week_start + timedelta(days=6)
        week_report = get_weekly_report(str(week_start), str(week_end))
        weeks.append({
            'start': week_start.strftime('%d %b'),
            'end': week_end.strftime('%d %b'),
            'revenue': week_report['revenue'],
        'profit': week_report['profit'],
        'orders': week_report['total_orders'] or 0
        })
        week_start += timedelta(days=7)

    weeks_sorted = sorted(weeks, key=lambda x: x['revenue'], reverse=True)
    
    return render_template('finance_monthly.html',
        monthly=monthly,
        month_name=month_name,
        selected_year=selected_year,
        selected_month=selected_month,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year,
        weeks=weeks_sorted
    )

@app.route('/finance/custom', methods=['GET', 'POST'])
def finance_custom():
    if request.method == 'POST':
        start = request.form['start_date']
        end = request.form['end_date']

        report = get_custom_report(start, end)

        from datetime import datetime
        start_formatted = datetime.strptime(start, '%Y-%m-%d').strftime('%d %b %Y')
        end_formatted = datetime.strptime(end, '%Y-%m-%d').strftime('%d %b %Y')

        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.id, c.name, o.delivery_date, o.status,
                   o.revenue, o.profit, o.margin
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            WHERE o.delivery_date BETWEEN %s AND %s
            ORDER BY o.delivery_date ASC
        ''', (start, end))
        all_orders = cursor.fetchall()
        conn.close()

        return render_template('finance_custom.html',
            report=report,
            all_orders=all_orders,
            start=start,
            end=end,
            start_formatted=start_formatted,
            end_formatted=end_formatted,
            searched=True
        )

    return render_template('finance_custom.html', searched=False)

@app.route('/recipes')
def recipes_page():
    recipes = get_all_recipes()
    return render_template('recipes.html', recipes=recipes)

@app.route('/recipes/new', methods=['POST'])
def new_recipe():
    name = request.form['name'].lower().replace(' ', '_') + '_slapp'
    base_yield = int(request.form['base_yield'])
    add_recipe(name, base_yield)
    return redirect(url_for('recipes_page'))

@app.route('/recipes/<recipe_name>')
def recipe_detail(recipe_name):
    from management import get_all_recipes
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, base_yield FROM recipes WHERE name = %s', (recipe_name,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return redirect(url_for('recipes_page'))
    
    recipe = {
        'id': row[0],
        'name': row[1],
        'base_yield': row[2],
        'ingredients': []
    }
    
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, ingredient_name, amount, unit, stage FROM recipe_ingredients WHERE recipe_id = %s ORDER BY id', (row[0],))
    for ing in cursor.fetchall():
        recipe['ingredients'].append({'id': ing[0], 'ingredient': ing[1], 'amount': ing[2], 'unit': ing[3], 'stage': ing[4] or 'dough'})
    conn.close()

    return render_template('recipe_detail.html', recipe=recipe)

@app.route('/recipes/<recipe_name>/delete')
def delete_recipe_route(recipe_name):
    delete_recipe(recipe_name)
    return redirect(url_for('recipes_page'))

@app.route('/recipes/<recipe_name>/ingredient/<int:ingredient_id>/remove')
def remove_ingredient_route(recipe_name, ingredient_id):
    remove_ingredient_from_recipe(ingredient_id)
    return redirect(url_for('recipe_detail', recipe_name=recipe_name))
@app.route('/recipes/<recipe_name>/activate')

def activate_recipe_route(recipe_name):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE recipes SET is_active = 1 WHERE name = %s', (recipe_name,))
    conn.commit()
    conn.close()
    return redirect(url_for('recipes_page'))

@app.route('/stock/restock', methods=['GET', 'POST'])
def restock_flow():
    from database import get_connection
    
    low_cookies = check_low_stock()
    predictions = predict_all_flavours()
    
    pred_map = {p['flavour']: p for p in predictions}
    
    restock_items = []
    for flavour, qty, reserved, threshold, available in low_cookies:
        pred = pred_map.get(flavour, {})
        restock_items.append({
            'flavour': flavour,
            'available': available,
            'threshold': threshold,
            'recommended': pred.get('recommended_batch', 0),
            'has_prediction': pred.get('recommended_batch', 0) > 0
        })
    
    return render_template('restock.html', restock_items=restock_items)

@app.route('/stock/restock/shopping', methods=['POST'])
def restock_shopping():
    items_to_make = {}
    for key, value in request.form.items():
        if key.startswith('portions_') and value and int(value) > 0:
            flavour = key.replace('portions_', '')
            items_to_make[flavour] = int(value)
    
    if not items_to_make:
        return redirect(url_for('restock_flow'))
    
    from finance import get_combined_shopping_list
    shopping = get_combined_shopping_list(items_to_make)
    
    return render_template('shopping_list.html',
        shopping=shopping,
        items_to_make=items_to_make
    )

@app.route('/stock/restock/confirm', methods=['POST'])
def restock_confirm():
    for key, value in request.form.items():
        if key.startswith('packets_') and value and int(value) > 0:
            ingredient = key.replace('packets_', '')
            packets = int(value)
            
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT packet_size FROM ingredient_prices
                WHERE ingredient_name = %s AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
            ''', (ingredient,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                grams = packets * result[0]
                add_ingredient_stock(ingredient, grams)
    total_cost = float(request.form.get('total_cost', 0))
    if total_cost > 0:
        from cashflow import add_transaction
        add_transaction('expense', 'ingredients', total_cost, 'Grocery shopping')
    return redirect(url_for('stock_page'))

@app.route('/recipes/<recipe_name>/hard_delete')
def hard_delete_recipe(recipe_name):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM recipe_ingredients WHERE recipe_id = (SELECT id FROM recipes WHERE name = %s)', (recipe_name,))
    cursor.execute('DELETE FROM recipes WHERE name = %s', (recipe_name,))
    cursor.execute('DELETE FROM cookie_stock WHERE flavour = %s', (recipe_name,))
    cursor.execute('DELETE FROM pricing WHERE flavour = %s', (recipe_name,))
    conn.commit()
    conn.close()
    return redirect(url_for('recipes_page'))

@app.route('/bake')
def bake_brief_page():
    selected_date = request.args.get('date', str(date.today() + timedelta(days=1)))
    bake_brief = get_bake_brief(selected_date)
    rows = get_orders_by_delivery_date(selected_date)
    formatted = format_orders(rows)
    
    return render_template('bake.html',
        bake_brief=bake_brief,
        orders=formatted,
        selected_date=selected_date
    )

@app.route('/stock/packaging/<box_name>/set', methods=['GET', 'POST'])
def set_packaging_stock(box_name):
    if request.method == 'POST':
        quantity = int(request.form['quantity'])
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE packaging SET stock = %s WHERE box_name = %s', (quantity, box_name))
        conn.commit()
        conn.close()
        return redirect(url_for('stock_page'))
    return render_template('add_stock.html', flavour=box_name, action='set')

@app.route('/stock/packaging/<box_name>/add', methods=['GET', 'POST'])
def add_packaging_stock(box_name):
    if request.method == 'POST':
        quantity = int(request.form['quantity'])
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE packaging SET stock = stock + %s WHERE box_name = %s', (quantity, box_name))
        conn.commit()
        conn.close()
        from cashflow import add_transaction
        from database import get_connection
        conn2 = get_connection()
        cursor2 = conn2.cursor()
        cursor2.execute('SELECT cost_per_box FROM packaging WHERE box_name = %s', (box_name,))
        cost = cursor2.fetchone()[0]
        conn2.close()
        total_cost = quantity * cost
        if total_cost > 0:
            add_transaction('expense', 'packaging', total_cost, f'Bought {quantity} {box_name}')
        return redirect(url_for('stock_page'))
    return render_template('add_stock.html', flavour=box_name, action='add')

@app.route('/settings')
def settings_page():
    pricing = get_all_pricing()
    combos = get_all_combos()
    delivery_zones = get_all_delivery_zones()
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT flavour, low_stock_threshold FROM cookie_stock ORDER BY flavour')
    cookie_thresholds = cursor.fetchall()
    cursor.execute('SELECT ingredient_name, low_stock_threshold, unit FROM ingredient_stock ORDER BY ingredient_name')
    ingredient_thresholds = cursor.fetchall()
    cursor.execute('SELECT box_name, capacity, cost_per_box, stock, low_stock_threshold, is_active FROM packaging ORDER BY is_active DESC, box_name')
    packaging = cursor.fetchall()
    conn.close()

    return render_template('settings.html',
        pricing=pricing,
        combos=combos,
        delivery_zones=delivery_zones,
        cookie_thresholds=cookie_thresholds,
        ingredient_thresholds=ingredient_thresholds,
        packaging=packaging
    )

@app.route('/settings/packaging/<box_name>/deactivate')
def deactivate_packaging_route(box_name):
    deactivate_packaging(box_name)
    return redirect(url_for('settings_page'))

@app.route('/settings/packaging/<box_name>/activate')
def activate_packaging_route(box_name):
    activate_packaging(box_name)
    return redirect(url_for('settings_page'))

@app.route('/settings/zones/<int:zone_id>/deactivate')
def deactivate_zone_route(zone_id):
    deactivate_delivery_zone(zone_id)
    return redirect(url_for('settings_page'))

@app.route('/settings/zones/<int:zone_id>/activate')
def activate_zone_route(zone_id):
    activate_delivery_zone(zone_id)
    return redirect(url_for('settings_page'))

@app.route('/settings/zones/<int:zone_id>/edit', methods=['GET', 'POST'])
def edit_zone_cost(zone_id):
    if request.method == 'POST':
        cost = float(request.form['typical_porter_cost'])
        update_delivery_zone(zone_id, typical_porter_cost=cost)
        return redirect(url_for('settings_page'))
    return render_template('edit_simple.html',
        title='Edit Typical Porter Cost',
        field_label='Typical Porter Cost (₹)',
        field_name='typical_porter_cost',
        action=f'/settings/zones/{zone_id}/edit')

@app.route('/settings/zones/new', methods=['GET', 'POST'])
def new_zone():
    if request.method == 'POST':
        zone_name = request.form['zone_name'].strip()
        typical_porter_cost = float(request.form.get('typical_porter_cost', 0) or 0)
        add_delivery_zone(zone_name, typical_porter_cost)
        return redirect(url_for('settings_page'))
    return render_template('new_zone.html')

@app.route('/settings/pricing/<flavour>/edit', methods=['GET', 'POST'])
def edit_pricing(flavour):
    if request.method == 'POST':
        new_price = float(request.form['price'])
        update_flavour_price(flavour, new_price)
        return redirect(url_for('settings_page'))
    return render_template('edit_simple.html', 
        title=f"Edit Price — {flavour.replace('_slapp','').replace('_',' ').title()}",
        field_label='Price per cookie (₹)',
        field_name='price',
        current_value='',
        action=f'/settings/pricing/{flavour}/edit')

@app.route('/settings/combos/<int:combo_id>/deactivate')
def deactivate_combo_route(combo_id):
    deactivate_combo(combo_id)
    return redirect(url_for('settings_page'))

@app.route('/settings/combos/<int:combo_id>/activate')
def activate_combo_route(combo_id):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE combos SET is_active = 1 WHERE id = %s', (combo_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('settings_page'))

@app.route('/settings/combos/new', methods=['GET', 'POST'])
def new_combo():
    if request.method == 'POST':
        name = request.form['name']
        combo_type = request.form.get('combo_type', 'bogo')
        
        if combo_type == 'discount':
            discount = float(request.form.get('discount_percentage', 0))
            add_combo(name, 0, 0, discount_percentage=discount)
        else:
            buy_qty = int(request.form.get('buy_quantity', 0))
            free_qty = int(request.form.get('free_quantity', 0))
            add_combo(name, buy_qty, free_qty)
        
        return redirect(url_for('settings_page'))
    return render_template('new_combo.html')

@app.route('/settings/threshold/cookie/<flavour>/edit', methods=['GET', 'POST'])
def edit_cookie_threshold(flavour):
    if request.method == 'POST':
        threshold = int(request.form['threshold'])
        update_cookie_threshold(flavour, threshold)
        return redirect(url_for('settings_page'))
    return render_template('edit_simple.html',
        title=f"Edit Threshold — {flavour.replace('_slapp','').replace('_',' ').title()}",
        field_label='Low stock threshold (portions)',
        field_name='threshold',
        current_value='',
        action=f'/settings/threshold/cookie/{flavour}/edit')

@app.route('/settings/threshold/ingredient/<name>/edit', methods=['GET', 'POST'])
def edit_ingredient_threshold(name):
    if request.method == 'POST':
        threshold = float(request.form['threshold'])
        update_ingredient_threshold(name, threshold)
        return redirect(url_for('settings_page'))
    return render_template('edit_simple.html',
        title=f"Edit Threshold — {name.replace('_',' ').title()}",
        field_label='Low stock threshold',
        field_name='threshold',
        current_value='',
        action=f'/settings/threshold/ingredient/{name}/edit')

@app.route('/settings/packaging/<box_name>/edit', methods=['GET', 'POST'])
def edit_packaging(box_name):
    if request.method == 'POST':
        capacity = int(request.form['capacity'])
        cost = float(request.form['cost_per_box'])
        threshold = int(request.form['threshold'])
        from management import update_packaging
        update_packaging(box_name, capacity=capacity, cost_per_box=cost, low_stock_threshold=threshold)
        return redirect(url_for('settings_page'))
    
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT box_name, capacity, cost_per_box, low_stock_threshold FROM packaging WHERE box_name = %s', (box_name,))
    box = cursor.fetchone()
    conn.close()
    return render_template('edit_packaging.html', box=box)

@app.route('/settings/packaging/new', methods=['GET', 'POST'])
def new_packaging():
    if request.method == 'POST':
        box_name = request.form['box_name'].lower().replace(' ', '_')
        capacity = int(request.form['capacity'])
        cost = float(request.form['cost_per_box'])
        threshold = int(request.form['threshold'])
        from management import add_packaging
        add_packaging(box_name, capacity, cost, low_stock_threshold=threshold)
        return redirect(url_for('settings_page'))
    return render_template('new_packaging.html')

@app.route('/finance/cashflow', methods=['GET', 'POST'])
def cashflow_page():
    from cashflow import get_balance, set_initial_balance, get_transactions

    if request.method == 'POST':
        amount = request.form.get('balance', '').strip()
        if amount:
            set_initial_balance(float(amount))
        return redirect(url_for('cashflow_page'))

    balance = get_balance()
    transactions = get_transactions()

    return render_template('cashflow.html',
        balance=balance,
        transactions=transactions
    )
@app.route('/popups/<int:popup_id>')
def popup_detail(popup_id):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM popups WHERE id = %s', (popup_id,))
    popup = cursor.fetchone()
    conn.close()
    return render_template('popup_detail.html', popup=popup)

@app.route('/popups/new', methods=['GET', 'POST'])
def new_popup():
    if request.method == 'POST':
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        
        event_name = request.form['event_name']
        event_date = request.form['event_date']
        location = request.form['location']
        units_produced = int(request.form.get('units_produced', 0))
        units_sold = int(request.form.get('units_sold', 0))
        units_given_free = int(request.form.get('units_given_free', 0))
        revenue = float(request.form.get('revenue', 0))
        investment = float(request.form.get('investment', 0))
        game_players = int(request.form.get('game_players', 0))
        game_revenue = float(request.form.get('game_revenue', 0))
        notes = request.form.get('notes', '')
        
        cursor.execute('''
            INSERT INTO popups (event_name, event_date, location, units_produced,
                units_sold, units_given_free, revenue, investment,
                game_players, game_revenue, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (event_name, event_date, location, units_produced, units_sold,
              units_given_free, revenue, investment, game_players, game_revenue, notes))
        
        conn.commit()
        conn.close()
        
        from cashflow import add_transaction
        if investment > 0:
            add_transaction('expense', 'popup', investment, f'Investment — {event_name}')
        total_revenue = revenue + game_revenue
        if total_revenue > 0:
            add_transaction('income', 'popup', total_revenue, f'Revenue — {event_name}')
        
        return redirect(url_for('popups_page'))
    
    return render_template('new_popup.html')

@app.route('/popups')
def popups_page():
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM popups ORDER BY event_date DESC')
    popups = cursor.fetchall()
    conn.close()
    return render_template('popups.html', popups=popups)

@app.route('/recipes/scale', methods=['GET', 'POST'])
def scale_recipe():
    recipes = get_all_recipes()
    scaled = None
    selected_flavour = None
    portions = None
    
    if request.method == 'POST':
        selected_flavour = request.form['flavour']
        portions = int(request.form['portions'])
        
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (selected_flavour,))
        base_yield = cursor.fetchone()[0]
        multiplier = portions / base_yield
        
        cursor.execute('''
            SELECT ingredient_name, amount, unit 
            FROM recipe_ingredients 
            WHERE recipe_id = (SELECT id FROM recipes WHERE name = %s)
            ORDER BY ingredient_name
        ''', (selected_flavour,))
        
        ingredients = cursor.fetchall()
        conn.close()
        
        scaled = []
        for name, amount, unit in ingredients:
            scaled.append({
                'name': name.replace('_', ' ').title(),
                'amount': round(amount * multiplier, 1),
                'unit': unit
            })
    
    return render_template('scale_recipe.html',
        recipes=recipes,
        scaled=scaled,
        selected_flavour=selected_flavour,
        portions=portions
    )

@app.route('/recipes/<recipe_name>/ingredient/<int:ingredient_id>/edit', methods=['GET', 'POST'])
def edit_ingredient_route(recipe_name, ingredient_id):
    if request.method == 'POST':
        amount = float(request.form['amount'])
        update_ingredient_amount(ingredient_id, amount)
        return redirect(url_for('recipe_detail', recipe_name=recipe_name))

    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ingredient_name, amount, unit FROM recipe_ingredients WHERE id = %s
    ''', (ingredient_id,))
    result = cursor.fetchone()
    conn.close()

    return render_template('edit_simple.html',
        title=f"Edit {result[0].replace('_',' ').title()} in {recipe_name.replace('_slapp','').replace('_',' ').title()}",
        field_label=f'Amount ({result[2] if result else "g"})',
        field_name='amount',
        current_value=result[1] if result else '',
        action=f'/recipes/{recipe_name}/ingredient/{ingredient_id}/edit')

@app.route('/recipes/<recipe_name>/ingredient/add', methods=['POST'])
def add_ingredient_route(recipe_name):
    ingredient_name = request.form['ingredient_name'].lower().replace(' ', '_')
    amount = request.form.get('amount', '').strip()
    unit = request.form.get('unit', '').strip()
    stage = request.form.get('stage', 'dough')

    if not amount or not ingredient_name:
        return redirect(url_for('recipe_detail', recipe_name=recipe_name))

    add_ingredient_to_recipe(recipe_name, ingredient_name, float(amount), unit, stage)
    return redirect(url_for('recipe_detail', recipe_name=recipe_name))

@app.route('/settings/combos/<int:combo_id>/delete')
def delete_combo_route(combo_id):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM order_combos oc
        JOIN orders o ON oc.order_id = o.id
        WHERE oc.combo_id = %s AND o.status = 'pending'
    ''', (combo_id,))
    pending = cursor.fetchone()[0]
    if pending > 0:
        conn.close()
        return redirect(url_for('settings_page'))
    cursor.execute('DELETE FROM combos WHERE id = %s', (combo_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('settings_page'))

@app.route('/finance/cashflow/add', methods=['GET', 'POST'])
def add_transaction_manual():
    if request.method == 'POST':
        type = request.form['type']
        category = request.form['category']
        amount = float(request.form['amount'])
        description = request.form.get('description', '')
        add_transaction(type, category, amount, description)
        return redirect(url_for('cashflow_page'))
    return render_template('add_transaction.html')

@app.route('/settings/ingredient/<name>/price', methods=['GET', 'POST'])
def edit_ingredient_price(name):
    if request.method == 'POST':
        packet_size = float(request.form['packet_size'])
        packet_price = float(request.form['packet_price'])
        
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT unit FROM ingredient_stock WHERE ingredient_name = %s', (name,))
        unit = cursor.fetchone()[0]
        conn.close()
        
        update_ingredient_price(name, packet_size, unit, packet_price)
        return redirect(url_for('settings_page'))
    
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT packet_size, packet_price FROM ingredient_prices
        WHERE ingredient_name = %s AND is_active = 1
        ORDER BY created_at DESC LIMIT 1
    ''', (name,))
    current = cursor.fetchone()
    conn.close()
    
    return render_template('edit_ingredient_price.html', name=name, current=current)

@app.route('/api/stock', methods=['GET'])
def api_stock():
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT flavour, quantity - reserved as available FROM cookie_stock')
    stock = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return jsonify(stock)

@app.route('/api/combos', methods=['GET'])
def api_combos():
    combos = get_all_combos()
    result = []
    for combo in combos:
        if combo[5]:  # is_active
            result.append({
                'id': combo[0],
                'name': combo[1],
                'buy_quantity': combo[2],
                'free_quantity': combo[3],
                'discount_percentage': combo[4]
            })
    return jsonify(result)

@app.route('/api/packaging', methods=['GET'])
def api_packaging():
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT box_name, capacity, stock FROM packaging')
    packaging = [{'box_name': r[0], 'capacity': r[1], 'stock': r[2]} for r in cursor.fetchall()]
    conn.close()
    return jsonify(packaging)

@app.route('/api/orders', methods=['POST'])
def api_create_order():
    data = request.get_json()
    
    name = data['name']
    phone = data['phone']
    address = data['address']
    delivery_date = data['delivery_date']
    items = data['items']
    notes = data.get('notes', '')

    warnings = check_stock_for_order(items)
    if warnings:
        return jsonify({'success': False, 'warnings': warnings}), 400

    customer_id = add_customer(name, phone, address)
    order_id = create_order(customer_id, delivery_date, address, items, notes)
    
    return jsonify({'success': True, 'order_id': order_id})

@app.route('/orders/dm', methods=['GET', 'POST'])
def dm_order():
    from dm_agent import extract_order_from_dm
    from database import get_connection
    
    extracted = None
    error = None
    
    if request.method == 'POST' and 'dm_text' in request.form:
        dm_text = request.form['dm_text']
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT flavour, quantity - reserved as available FROM cookie_stock')
        stock = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        
        combos = get_all_combos()
        active_combos = [{'id': c[0], 'name': c[1], 'buy': c[2], 'free': c[3], 'discount': c[4]} for c in combos if c[5]]
        
        try:
            extracted = extract_order_from_dm(dm_text, stock, active_combos)
        except Exception as e:
            error = str(e)
    
    elif request.method == 'POST' and 'confirm' in request.form:
        name = request.form['name']
        phone = request.form['phone']
        address = request.form['address']
        delivery_date = request.form['delivery_date']
        notes = request.form.get('notes', '')
        delivery_required = bool(request.form.get('delivery_required'))
        delivery_zone_id = request.form.get('delivery_zone_id') or None

        items = {}
        for key, value in request.form.items():
            if key.startswith('item_') and value and int(value) > 0:
                flavour = key.replace('item_', '')
                items[flavour] = int(value)

        warnings = check_stock_for_order(items)

        if warnings:
            extracted = {
                'name': name,
                'phone': phone,
                'address': address,
                'delivery_date': delivery_date,
                'items': items,
                'notes': notes,
                'delivery_required': delivery_required,
                'missing': [],
                'address_validated': None
            }
            return render_template('dm_order.html',
                extracted=extracted,
                error=None,
                today=date.today(),
                stock_warnings=warnings,
                combos=get_all_combos(),
                zones=get_all_delivery_zones(),
                recipes=get_all_recipes()
            )

        if items:
            customer_id = add_customer(name, phone, address)
            order_id = create_order(customer_id, delivery_date, address, items, notes, delivery_required, delivery_zone_id=delivery_zone_id)
            return redirect(url_for('all_orders'))

    return render_template('dm_order.html',
        extracted=extracted,
        error=error,
        today=date.today(),
        stock_warnings=None,
        combos=get_all_combos(),
        zones=get_all_delivery_zones(),
        recipes=get_all_recipes()
    )

@app.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
def edit_order(order_id):
    from database import get_connection
    
    if request.method == 'POST':
        name = request.form['name'].strip().title()
        phone = request.form['phone']
        delivery_date = request.form['delivery_date']
        address = request.form['address']
        notes = request.form.get('notes', '')
        delivery_required = bool(request.form.get('delivery_required'))
        is_bulk = bool(request.form.get('is_bulk'))
        bulk_discount_pct = float(request.form.get('bulk_discount_pct') or 0) if is_bulk else None
        delivery_zone_id = request.form.get('delivery_zone_id') or None
        # update customer details (leave phone untouched if cleared - blanking
        # it here has no "assign a new placeholder" semantic, unlike creation)
        conn = get_connection()
        cursor = conn.cursor()
        if phone:
            cursor.execute('''
                UPDATE customers SET name = %s, phone = %s
                WHERE id = (SELECT customer_id FROM orders WHERE id = %s)
            ''', (name, phone, order_id))
        else:
            cursor.execute('''
                UPDATE customers SET name = %s
                WHERE id = (SELECT customer_id FROM orders WHERE id = %s)
            ''', (name, order_id))
        conn.commit()
        conn.close()
        items = {}
        for key, value in request.form.items():
            if key.startswith('item_') and value and int(value) > 0:
                flavour = key.replace('item_', '')
                items[flavour] = int(value)

        total_cookies = sum(items.values())
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT capacity, stock FROM packaging WHERE is_active = 1')
        boxes = cursor.fetchall()
        total_capacity = sum(cap * stock for cap, stock in boxes)
        conn.close()

        if total_capacity < total_cookies:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT o.id, c.name, c.phone, o.address, o.delivery_date, o.notes,
                       o.delivery_required, o.bulk_discount_pct, o.delivery_zone_id
                FROM orders o JOIN customers c ON o.customer_id = c.id
                WHERE o.id = %s
            ''', (order_id,))
            order = cursor.fetchone()
            conn.close()
            return render_template('edit_order.html',
                order=order,
                items=items,
                zones=get_all_delivery_zones(),
                recipes=get_all_recipes(),
                warnings=[],
                packaging_warning=f'Need to pack {total_cookies} cookies but total box capacity available is {total_capacity}')

        update_order(order_id, delivery_date=delivery_date, address=address, notes=notes,
                     delivery_required=delivery_required, bulk_discount_pct=bulk_discount_pct,
                     delivery_zone_id=delivery_zone_id)

        result = update_order_items(order_id, items)

        if isinstance(result, dict) and not result.get('success'):
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT o.id, c.name, c.phone, o.address, o.delivery_date, o.notes,
                       o.delivery_required, o.bulk_discount_pct, o.delivery_zone_id
                FROM orders o JOIN customers c ON o.customer_id = c.id
                WHERE o.id = %s
            ''', (order_id,))
            order = cursor.fetchone()
            conn.close()
            return render_template('edit_order.html',
                order=order,
                items=items,
                zones=get_all_delivery_zones(),
                recipes=get_all_recipes(),
                warnings=result['warnings'])

        return redirect(url_for('all_orders'))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.id, c.name, c.phone, o.address, o.delivery_date, o.notes,
               o.delivery_required, o.bulk_discount_pct, o.delivery_zone_id
        FROM orders o JOIN customers c ON o.customer_id = c.id
        WHERE o.id = %s
    ''', (order_id,))
    order = cursor.fetchone()

    cursor.execute('SELECT flavour, quantity FROM order_items WHERE order_id = %s', (order_id,))
    items = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    return render_template('edit_order.html', order=order, items=items, zones=get_all_delivery_zones(), recipes=get_all_recipes(), warnings=[])

@app.route('/agent/orders', methods=['GET', 'POST'])
def order_agent_page():
    from order_agent import run_agent
    from flask import session
    
    if 'agent_chat' not in session:
        session['agent_chat'] = []
    
    if request.method == 'POST':
        user_message = request.form['message'].strip()
        
        if user_message:
            chat_history = session['agent_chat']
            
            try:
                result = run_agent(user_message, chat_history)
            except Exception as e:
                result = {'type': 'message', 'content': f'Error: {str(e)}'}
            
            # save to history
            chat_history.append({'role': 'user', 'content': user_message})
            
            if result['type'] == 'navigate':
                chat_history.append({'role': 'assistant', 'content': f"Taking you to {result['url']}"})
                session['agent_chat'] = chat_history
                session.modified = True
                return redirect(result['url'])
            else:
                chat_history.append({'role': 'assistant', 'content': result['content']})
                session['agent_chat'] = chat_history
                session.modified = True
        
        return redirect(url_for('order_agent_page'))
    
    return render_template('agent_orders.html', chat=session['agent_chat'])

@app.route('/agent/orders/clear')
def clear_agent_chat():
    from flask import session
    session['agent_chat'] = []
    return redirect(url_for('order_agent_page'))

if __name__ == '__main__':
    port = int(os.environ.get('SLAPP_PORT', 8080))
    app.run(debug=True, host='127.0.0.1', port=port)

