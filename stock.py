from database import get_connection
import math  

def log_dough_made(flavour, portions):
    conn = get_connection()
    cursor = conn.cursor()
    
    # get base yield and calculate multiplier
    cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (flavour,))
    base_yield = cursor.fetchone()[0]
    multiplier = portions / base_yield
    
    # deduct ingredients
    cursor.execute('''
        SELECT ingredient_name, amount FROM recipe_ingredients
        WHERE recipe_id = (SELECT id FROM recipes WHERE name = %s)
    ''', (flavour,))
    
    for ingredient_name, amount in cursor.fetchall():
        scaled_amount = amount * multiplier
        cursor.execute('''
            UPDATE ingredient_stock
            SET quantity = quantity - %s
            WHERE ingredient_name = %s
        ''', (scaled_amount, ingredient_name))
    
    # increase frozen stock
    cursor.execute('''
        UPDATE cookie_stock
        SET quantity = quantity + %s
        WHERE flavour = %s
    ''', (portions, flavour))
    
    conn.commit()
    conn.close()
    print(f"Logged {portions} portions of {flavour}. Ingredients deducted.")

def log_order_delivered(order_id, delivery_cost_actual=0):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT flavour, quantity FROM order_items
        WHERE order_id = %s
    ''', (order_id,))

    items = cursor.fetchall()

    for flavour, quantity in items:
        cursor.execute('''
            UPDATE cookie_stock
            SET quantity = quantity - %s,
                reserved = reserved - %s
            WHERE flavour = %s
        ''', (quantity, quantity, flavour))

    # revenue is gross (already includes delivery_fee_charged from creation) and is NOT
    # touched here. delivery_cost_actual (real Porter cost) only reduces profit/margin —
    # this keeps revenue, delivery fee collected, and delivery cost paid as three
    # independent, summable line items for reporting (no double counting).
    cursor.execute('SELECT revenue, profit FROM orders WHERE id = %s', (order_id,))
    revenue, profit = cursor.fetchone()
    revenue = float(revenue or 0)
    profit = float(profit or 0) - delivery_cost_actual
    margin = round(profit / revenue * 100, 1) if revenue > 0 else 0

    cursor.execute('''
        UPDATE orders SET status = 'delivered', delivery_cost_actual = %s,
            profit = %s, margin = %s
        WHERE id = %s
    ''', (delivery_cost_actual, profit, margin, order_id))

    deduct_packaging_for_order(order_id)

    conn.commit()
    conn.close()
    from cashflow import add_transaction
    if revenue:
        add_transaction('income', 'order', revenue, f'Order #{order_id} delivered')
    if delivery_cost_actual:
        add_transaction('expense', 'delivery', delivery_cost_actual, f'Porter cost for order #{order_id}')
    print(f"Order #{order_id} marked as delivered. Stock updated.")

def check_low_stock():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT flavour, quantity, reserved, low_stock_threshold,
               (quantity - reserved) as available
        FROM cookie_stock
        WHERE (quantity - reserved) <= low_stock_threshold
    ''')
    
    low = cursor.fetchall()
    conn.close()
    return low

def check_low_ingredients():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ingredient_name, quantity, low_stock_threshold
        FROM ingredient_stock
        WHERE quantity <= low_stock_threshold
    ''')
    
    low = cursor.fetchall()
    conn.close()
    return low

if __name__ == '__main__':
    print("Testing stock module...")
    
    log_dough_made('the_brownie_slapp', 12)
    
    print("\nCookie stock after making dough:")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT flavour, quantity FROM cookie_stock')
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
    conn.close()
    
    print("\nLow stock alerts:")
    low = check_low_stock()
    if low:
        for flavour, qty, threshold in low:
            print(f"  {flavour}: {qty} portions (threshold: {threshold})")
    else:
        print("  All good!")

def check_stock_for_order(items):
    conn = get_connection()
    cursor = conn.cursor()
    
    warnings = []
    
    for flavour, quantity_needed in items.items():
        cursor.execute('''
            SELECT quantity - reserved as available
            FROM cookie_stock
            WHERE flavour = %s
        ''', (flavour,))
        
        result = cursor.fetchone()
        available = result[0] if result else 0
        
        if available < quantity_needed:
            warnings.append({
                'flavour': flavour,
                'needed': quantity_needed,
                'available': available,
                'shortage': quantity_needed - available
            })
    
    conn.close()
    return warnings

def check_low_packaging():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT box_name, stock, low_stock_threshold
        FROM packaging
        WHERE stock <= low_stock_threshold
    ''')
    
    low = cursor.fetchall()
    conn.close()
    return low

def deduct_packaging_for_order(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT SUM(quantity) FROM order_items WHERE order_id = %s', (order_id,))
    total_cookies = cursor.fetchone()[0]
    
    cursor.execute('SELECT box_name, capacity, id FROM packaging WHERE stock > 0 AND is_active = 1 ORDER BY capacity DESC')
    boxes = cursor.fetchall()
    
    # greedy algorithm — use largest boxes first
    allocation = {}
    remaining = total_cookies
    
    for box_name, capacity, box_id in boxes:
        if remaining <= 0:
            break
        count = remaining // capacity
        if count > 0:
            allocation[box_id] = (box_name, count, capacity)
            remaining -= count * capacity
    
    # if cookies still remaining, use smallest box for the rest
    if remaining > 0:
        smallest = boxes[-1]
        box_id = smallest[2]
        if box_id in allocation:
            allocation[box_id] = (allocation[box_id][0], allocation[box_id][1] + 1, allocation[box_id][2])
        else:
            allocation[box_id] = (smallest[0], 1, smallest[1])
    
    # deduct stock
    for box_id, (box_name, count, capacity) in allocation.items():
        cursor.execute('UPDATE packaging SET stock = stock - %s WHERE id = %s', (count, box_id))
    
    conn.commit()
    conn.close()
    
    return allocation

def set_ingredient_stock(ingredient_name, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE ingredient_stock
        SET quantity = %s
        WHERE ingredient_name = %s
    ''', (quantity, ingredient_name))
    
    conn.commit()
    conn.close()
    print(f"Updated {ingredient_name} stock to {quantity}")

def add_ingredient_stock(ingredient_name, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE ingredient_stock
        SET quantity = quantity + %s
        WHERE ingredient_name = %s
    ''', (quantity, ingredient_name))
    
    conn.commit()
    conn.close()
    print(f"Added {quantity} to {ingredient_name} stock")

def reserve_stock(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT flavour, quantity FROM order_items
        WHERE order_id = %s
    ''', (order_id,))
    
    items = cursor.fetchall()
    
    for flavour, quantity in items:
        cursor.execute('''
            UPDATE cookie_stock
            SET reserved = reserved + %s
            WHERE flavour = %s
        ''', (quantity, flavour))
    
    conn.commit()
    conn.close()

def release_reservation(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT flavour, quantity FROM order_items
        WHERE order_id = %s
    ''', (order_id,))
    
    items = cursor.fetchall()
    
    for flavour, quantity in items:
        cursor.execute('''
            UPDATE cookie_stock
            SET reserved = reserved - %s
            WHERE flavour = %s
        ''', (quantity, flavour))
    
    conn.commit()
    conn.close()    

def set_cookie_stock(flavour, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE cookie_stock
        SET quantity = %s
        WHERE flavour = %s
    ''', (quantity, flavour))
    
    conn.commit()
    conn.close()
    print(f"Updated {flavour} stock to {quantity}")

def add_cookie_stock(flavour, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE cookie_stock
        SET quantity = quantity + %s
        WHERE flavour = %s
    ''', (quantity, flavour))
    
    conn.commit()
    conn.close()
    print(f"Added {quantity} to {flavour} stock")