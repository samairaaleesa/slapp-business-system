from database import get_connection

def add_customer(name, phone, address):
    conn = get_connection()
    cursor = conn.cursor()
    
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

def create_order(customer_id, delivery_date, address, items,combo_id=None,notes=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO orders (customer_id, delivery_date, address,combo_id,notes)
        VALUES (%s, %s, %s,%s,%s)
        RETURNING id
    ''', (customer_id, delivery_date, address,combo_id,notes))
    
    order_id = cursor.fetchone()[0]
    
    for flavour, quantity in items.items():
        cursor.execute('''
            INSERT INTO order_items (order_id, flavour, quantity)
            VALUES (%s, %s, %s)
        ''', (order_id, flavour, quantity))
    conn.commit()
    conn.close()
    from finance import calculate_order_profit
    profit_data = calculate_order_profit(order_id)
    conn2 = get_connection()
    cursor2 = conn2.cursor()
    cursor2.execute('''
    UPDATE orders 
    SET revenue = %s, ingredient_cost = %s, packaging_cost = %s,
        total_cost = %s, profit = %s, margin = %s
    WHERE id = %s
''', (profit_data['revenue'], profit_data['ingredient_cost'],
      profit_data['packaging_cost'], profit_data['total_cost'],
      profit_data['profit'], profit_data['margin'], order_id))
    
    conn2.commit()
    conn2.close()

    from stock import reserve_stock
    reserve_stock(order_id)
    
    return order_id

def update_order(order_id, delivery_date=None, address=None, notes=None):
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
    
    conn.commit()
    conn.close()
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
    
    from finance import calculate_order_profit
    profit_data = calculate_order_profit(order_id)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE orders 
        SET revenue = %s, ingredient_cost = %s, packaging_cost = %s,
            total_cost = %s, profit = %s, margin = %s
        WHERE id = %s
    ''', (profit_data['revenue'], profit_data['ingredient_cost'],
          profit_data['packaging_cost'], profit_data['total_cost'],
          profit_data['profit'], profit_data['margin'], order_id))
    
    conn.commit()
    conn.close()
    
    return {'success': True}

def get_orders_by_delivery_date(delivery_date):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.id, c.name, c.phone, o.address, o.status,
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
        order_id, name, phone, address, status, flavour, quantity = row
        
        if order_id not in orders:
            orders[order_id] = {
                'customer': name,
                'phone': phone,
                'address': address,
                'status': status,
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

if __name__ == '__main__':
    customer_id = add_customer('Priya', '9876543210', 'HSR Layout, Bangalore')
    print(f"Customer id: {customer_id}")
    
    order_id = create_order(
        customer_id,
        '2026-05-16',
        'HSR Layout, Bangalore',
        {
            'the_classic_slapp': 2,
            'the_brownie_slapp': 3
        }
    )
    customer_id = add_customer('Ms.Sharma', '9876548210', 'HBR Layout, Bangalore')
    print(f"Customer id: {customer_id}")
    
    order_id = create_order(
        customer_id,
        '2026-05-16',
        'HBR Layout, Bangalore',
        {
            'the_classic_slapp': 3,
            'the_brownie_slapp': 2
        },
        1
    )
    customer_id = add_customer('Katie', '9836543210', ' Richmond Town, Bangalore')
    print(f"Customer id: {customer_id}")
    
    order_id = create_order(
        customer_id,
        '2026-05-16',
        'Richmond Town, Bangalore',
        {
            'the_classic_slapp': 2,
            'the_brownie_slapp': 3,
            'red_velvet_slapp':5
        },
        1
    )
    customer_id = add_customer('Simon', '8876543210', 'Benson Town, Bangalore')
    print(f"Customer id: {customer_id}")
    
    order_id = create_order(
        customer_id,
        '2026-05-16',
        'Benson Town, Bangalore',
        {
            'the_classic_slapp': 4,
            'comfort_slapp': 4
        },
        1
    )
    
    print("\nBake brief for May 16:")
    for flavour, total in get_bake_brief('2026-05-16'):
         print(f"  {flavour}: {total} cookies to bake")
    print("\nOrders for tomorrow:")
    rows = get_orders_by_delivery_date('2026-05-16')
    formatted = format_orders(rows)
    
    for order_id, details in formatted.items():
        print(f"\nOrder #{order_id} — {details['customer']}, {details['phone']}")
        print(f"Address: {details['address']}")
        print(f"Status: {details['status']}")
        for flavour, quantity in details['items']:
            print(f"  {flavour}: {quantity} cookies")



        