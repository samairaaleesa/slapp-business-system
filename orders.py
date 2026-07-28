from database import get_connection

def save_order_combos(order_id, breakdown):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM order_combos WHERE order_id = %s', (order_id,))
    for entry in breakdown:
        cursor.execute('''
            INSERT INTO order_combos (order_id, combo_id, count)
            VALUES (%s, %s, %s)
        ''', (order_id, entry['combo_id'], entry['count']))
    conn.commit()
    conn.close()

def generate_placeholder_phone():
    """Real phone numbers here always start with 6-9, so a leading-zero
    number is always a placeholder. Each one gets a unique number so
    different no-phone customers never collide into the same record."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT phone FROM customers WHERE phone LIKE '0%' ORDER BY phone DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    next_num = int(row[0]) + 1 if row else 1
    return f"{next_num:010d}"

def add_customer(name, phone, address):
    conn = get_connection()
    cursor = conn.cursor()

    if not phone:
        phone = generate_placeholder_phone()

    cursor.execute('''
        INSERT INTO customers (name, phone, address)
        VALUES (%s, %s, %s)
        ON CONFLICT (phone) DO NOTHING
    ''', (name, phone, address))

    cursor.execute('SELECT id FROM customers WHERE phone = %s', (phone,))
    customer = cursor.fetchone()

    conn.commit()
    conn.close()

    return customer[0]

def recalculate_order_finance(order_id):
    """Single source of truth for order finance: reads the order's current
    delivery_required/bulk_discount_pct/items, recomputes revenue/cost/profit/
    margin and the combo breakdown, and writes the snapshot back. Called after
    any change that affects the numbers (items, delivery_required, discount).

    revenue is always GROSS (cookie revenue + delivery fee charged to customer).
    delivery_cost_actual (the real Porter cost) is NOT known yet at this point —
    it only gets applied to profit/margin later, at delivery time (stock.py)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT delivery_required, bulk_discount_pct FROM orders WHERE id = %s', (order_id,))
    delivery_required, bulk_discount_pct = cursor.fetchone()
    conn.close()

    from finance import calculate_order_profit
    profit_data = calculate_order_profit(order_id, bulk_discount_pct)
    save_order_combos(order_id, profit_data['combo_breakdown'])

    cookie_revenue = profit_data['revenue']
    delivery_fee_charged = 50 if (delivery_required and cookie_revenue < 500) else 0
    revenue = cookie_revenue + delivery_fee_charged
    profit = revenue - profit_data['total_cost']
    margin = round(profit / revenue * 100, 1) if revenue > 0 else 0

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE orders
        SET revenue = %s, ingredient_cost = %s, packaging_cost = %s,
            total_cost = %s, profit = %s, margin = %s, delivery_fee_charged = %s
        WHERE id = %s
    ''', (revenue, profit_data['ingredient_cost'],
          profit_data['packaging_cost'], profit_data['total_cost'],
          profit, margin, delivery_fee_charged, order_id))
    conn.commit()
    conn.close()

def create_order(customer_id, delivery_date, address, items,notes=None,delivery_required=False,bulk_discount_pct=None,delivery_zone_id=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO orders (customer_id, delivery_date, address,notes,delivery_required,bulk_discount_pct,delivery_zone_id)
        VALUES (%s, %s, %s,%s,%s,%s,%s)
        RETURNING id
    ''', (customer_id, delivery_date, address,notes,delivery_required,bulk_discount_pct,delivery_zone_id))

    order_id = cursor.fetchone()[0]

    for flavour, quantity in items.items():
        cursor.execute('''
            INSERT INTO order_items (order_id, flavour, quantity)
            VALUES (%s, %s, %s)
        ''', (order_id, flavour, quantity))
    conn.commit()
    conn.close()

    recalculate_order_finance(order_id)

    from stock import reserve_stock
    reserve_stock(order_id)

    return order_id

def update_order(order_id, delivery_date=None, address=None, notes=None, delivery_required=None, bulk_discount_pct=-1, delivery_zone_id=-1):
    conn = get_connection()
    cursor = conn.cursor()

    if delivery_date:
        cursor.execute('''
            UPDATE orders SET delivery_date = %s WHERE id = %s
        ''', (delivery_date, order_id))

    if address:
        cursor.execute('''
            UPDATE orders SET address = %s WHERE id = %s
        ''', (address, order_id))

    if notes:
        cursor.execute('''
            UPDATE orders SET notes = %s WHERE id = %s
        ''', (notes, order_id))

    if delivery_required is not None:
        cursor.execute('''
            UPDATE orders SET delivery_required = %s WHERE id = %s
        ''', (delivery_required, order_id))

    # -1 sentinel = "not provided, leave unchanged"; None is a valid value (clear it)
    if bulk_discount_pct != -1:
        cursor.execute('''
            UPDATE orders SET bulk_discount_pct = %s WHERE id = %s
        ''', (bulk_discount_pct, order_id))

    if delivery_zone_id != -1:
        cursor.execute('''
            UPDATE orders SET delivery_zone_id = %s WHERE id = %s
        ''', (delivery_zone_id, order_id))

    conn.commit()
    conn.close()

    if delivery_required is not None or bulk_discount_pct != -1:
        recalculate_order_finance(order_id)
    print(f"Order #{order_id} updated!")

def update_order_items(order_id, new_items):
    from stock import release_reservation, reserve_stock, check_stock_for_order
    
    # temporarily release current reservation to get accurate available stock
    release_reservation(order_id)
    
    # check if new items are available
    warnings = check_stock_for_order(new_items)
    
    if warnings:
        # re-reserve old items since we're not updating
        reserve_stock(order_id)
        return {
            'success': False,
            'warnings': warnings
        }
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM order_items WHERE order_id = %s', (order_id,))
    
    for flavour, quantity in new_items.items():
        cursor.execute('''
            INSERT INTO order_items (order_id, flavour, quantity)
            VALUES (%s, %s, %s)
        ''', (order_id, flavour, quantity))
    
    conn.commit()
    conn.close()
    
    reserve_stock(order_id)

    recalculate_order_finance(order_id)

    return {'success': True}

def get_orders_by_delivery_date(delivery_date):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.id, c.name, c.phone, o.address, o.status, o.delivery_required,
               oi.flavour, oi.quantity
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.delivery_date = %s
        ORDER BY o.id
    ''', (delivery_date,))
    
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_bake_brief(delivery_date):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT oi.flavour, SUM(oi.quantity) as total
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE o.delivery_date = %s
        AND o.status !='cancelled'
        GROUP BY oi.flavour
        ORDER BY total DESC
    ''', (delivery_date,))
    
    rows = cursor.fetchall()
    conn.close()
    return rows
def format_orders(rows):
    orders = {}
    
    for row in rows:
        order_id, name, phone, address, status, delivery_required, flavour, quantity = row

        if order_id not in orders:
            orders[order_id] = {
                'customer': name,
                'phone': phone,
                'address': address,
                'status': status,
                'delivery_required': delivery_required,
                'items': []
            }
        
        orders[order_id]['items'].append((flavour, quantity))
    
    return orders

def cancel_order(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE orders SET status = 'cancelled'
        WHERE id = %s
    ''', (order_id,))
    
    conn.commit()
    conn.close()
    
    from stock import release_reservation
    release_reservation(order_id)
    print(f"Order #{order_id} cancelled. Stock released.")


        
